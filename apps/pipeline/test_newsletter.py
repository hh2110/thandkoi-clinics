"""Plan 09 — the monthly-newsletter drafting flow and its guardrails.

Mirrors ``apps/pipeline/tests.py``'s guardrail-test shape (Plan 08): plain,
deterministic Python assertions about what our code *sends* and *does* —
never a live model call, never a judgement of prose quality. Each maps to an
acceptance criterion in ``.claude/plans/09-ai-monthly-newsletter.md``:

* ``test_draft_monthly_newsletter_body_tool_result_matches_...``
  → the numbers guardrail: every figure the model is handed traces back to a
  real ``DailyAggregate``-derived computation.
* ``test_*_never_quer*_deidentified_visit`` → the tools never reach row-level
  data (the de-identification boundary sits upstream of ``ai``).
* ``test_draft_monthly_newsletter_creates_no_page_and_records_failed_run_*``
  → failure handling: no draft, ever, on a failed/timed-out AI call.
* ``test_newsletter_page_cannot_be_published_by_automation_*`` → invariant
  #4's general rule: this code path holds no publish permission.

The real Anthropic client is impossible to construct here — see the autouse
``_forbid_real_anthropic`` guard in the project ``conftest.py``.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.factories import (
    GalleryImageFactory,
    GalleryPageFactory,
    HomePageFactory,
    NewsletterIndexPageFactory,
    NewsletterPageFactory,
)
from apps.core.models import NewsletterIndexPage, NewsletterPage
from apps.pipeline import ai, newsletter_tools
from apps.pipeline.ai import PATIENT_IDENTIFYING_COLUMNS
from apps.pipeline.factories import DailyAggregateFactory
from apps.pipeline.models import NewsletterDraftRun
from apps.pipeline.monthly_rollup import (
    compute_month_over_month_trend,
    compute_monthly_rollup,
)
from apps.pipeline.newsletter_drafting import (
    NewsletterPhotoInput,
    draft_monthly_newsletter,
)

JULY = datetime.date(2026, 7, 1)
JUNE = datetime.date(2026, 6, 1)


class _ToolUseMessages:
    """Stub of ``client.messages`` scripting one tool-use round trip.

    First call returns a ``tool_use`` response requesting the given tools;
    the next call returns an ``end_turn`` response with the final text.
    Records every call's kwargs so a guardrail test can inspect exactly what
    was sent to (and received back from) the "model".
    """

    def __init__(self, tool_calls: list[tuple[str, dict]], final_text: str) -> None:
        self._tool_calls = tool_calls
        self._final_text = final_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            content = [
                SimpleNamespace(
                    type="tool_use", id=f"tool_{i}", name=name, input=tool_input
                )
                for i, (name, tool_input) in enumerate(self._tool_calls)
            ]
            return SimpleNamespace(stop_reason="tool_use", content=content)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=self._final_text)],
        )


class _ToolUseClient:
    """Canned Anthropic client stand-in that scripts a tool-use round trip."""

    def __init__(self, tool_calls: list[tuple[str, dict]], final_text: str) -> None:
        self.messages = _ToolUseMessages(tool_calls, final_text)

    @property
    def calls(self) -> list[dict]:
        return self.messages.calls


def _raising_client(exc: Exception | None = None):
    def _raise(**kwargs):
        raise (exc or TimeoutError("simulated AI timeout"))

    return SimpleNamespace(messages=SimpleNamespace(create=_raise))


# --- Monthly rollup: pure aggregation over DailyAggregate -------------------


def test_compute_monthly_rollup_sums_dailyaggregates_for_the_calendar_month(db):
    DailyAggregateFactory(
        clinic_date=datetime.date(2026, 7, 1),
        total_visits=10,
        male_patients=4,
        female_patients=6,
        category_counts={"by_department": {"General Medicine": 10}},
    )
    DailyAggregateFactory(
        clinic_date=datetime.date(2026, 7, 15),
        total_visits=5,
        male_patients=2,
        female_patients=3,
        category_counts={
            "by_department": {"General Medicine": 3, "Cardiology": 2},
        },
    )
    # A different month — must not be included.
    DailyAggregateFactory(clinic_date=datetime.date(2026, 8, 1), total_visits=999)

    rollup = compute_monthly_rollup(JULY)

    assert rollup.day_count == 2
    assert rollup.total_visits == 15
    assert rollup.male_patients == 6
    assert rollup.female_patients == 9
    assert rollup.category_counts["by_department"] == {
        "General Medicine": 13,
        "Cardiology": 2,
    }


def test_compute_monthly_rollup_normalises_any_day_to_the_first_of_month(db):
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 20), total_visits=7)

    assert compute_monthly_rollup(datetime.date(2026, 7, 20)).total_visits == 7
    assert compute_monthly_rollup(datetime.date(2026, 7, 1)).total_visits == 7


def test_compute_month_over_month_trend_compares_consecutive_calendar_months(db):
    DailyAggregateFactory(clinic_date=datetime.date(2026, 6, 10), total_visits=10)
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 10), total_visits=15)

    trend = compute_month_over_month_trend(JULY)

    assert trend["month"]["month"] == "2026-07"
    assert trend["previous_month"]["month"] == "2026-06"
    assert trend["total_visits_delta"] == 5


# --- Tool functions: thin, independently-testable wrappers ------------------


def test_get_month_stats_matches_compute_monthly_rollup(db):
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 3), total_visits=4)

    assert (
        newsletter_tools.get_month_stats(JULY) == compute_monthly_rollup(JULY).as_dict()
    )


def test_get_trend_vs_last_month_matches_compute_month_over_month_trend(db):
    DailyAggregateFactory(clinic_date=datetime.date(2026, 6, 3), total_visits=4)
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 3), total_visits=6)

    assert newsletter_tools.get_trend_vs_last_month(
        JULY
    ) == compute_month_over_month_trend(JULY)


def test_get_previous_newsletter_returns_most_recent_published_issue(db):
    home = HomePageFactory()
    index = NewsletterIndexPageFactory(parent=home)
    NewsletterPageFactory(
        parent=index, issue_date=datetime.date(2026, 5, 1), summary="May issue"
    )
    NewsletterPageFactory(
        parent=index, issue_date=JUNE, summary="June issue", title="June"
    )
    # An unpublished draft must never be picked, even though it's the latest.
    NewsletterPageFactory(
        parent=index, issue_date=JULY, summary="Unpublished July draft", live=False
    )

    result = newsletter_tools.get_previous_newsletter()

    assert result == {
        "issue_date": "2026-06-01",
        "title": "June",
        "summary": "June issue",
    }


def test_get_previous_newsletter_returns_none_when_no_published_issue_exists(db):
    home = HomePageFactory()
    index = NewsletterIndexPageFactory(parent=home)
    NewsletterPageFactory(parent=index, issue_date=JULY, live=False)

    assert newsletter_tools.get_previous_newsletter() is None


def test_newsletter_tools_never_query_deidentified_visit(db):
    """The de-identification boundary: no tool this plan exposes can reach
    row-level data — only DailyAggregate (Plan 08's derived cache) and
    published NewsletterPage rows."""
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 5))
    home = HomePageFactory()
    NewsletterIndexPageFactory(parent=home)

    with CaptureQueriesContext(connection) as ctx:
        newsletter_tools.get_month_stats(JULY)
        newsletter_tools.get_trend_vs_last_month(JULY)
        newsletter_tools.get_previous_newsletter()

    assert not any(
        "deidentifiedvisit" in query["sql"].lower() for query in ctx.captured_queries
    )


# --- The drafting call: one-shot prompt with tooling ------------------------


def test_draft_monthly_newsletter_body_tool_result_matches_deterministic_rollup(db):
    """The numbers guardrail: whatever the "model" is handed back as a tool
    result is byte-for-byte what an independent DailyAggregate query
    computes — never a hand-typed or model-invented figure."""
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 5), total_visits=12)
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 20), total_visits=8)
    expected = compute_monthly_rollup(JULY).as_dict()

    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})],
        final_text="This month, the clinic saw 20 patients across two open days.",
    )

    text = ai.draft_monthly_newsletter_body(JULY, client=client)

    assert text == "This month, the clinic saw 20 patients across two open days."
    assert len(client.calls) == 2  # initial prompt, then the tool-result continuation
    tool_result_message = client.calls[1]["messages"][-1]
    tool_result_content = tool_result_message["content"][0]["content"]
    assert json.loads(tool_result_content) == expected


def test_draft_monthly_newsletter_body_payload_never_carries_an_identifying_column(db):
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 5), total_visits=12)
    client = _ToolUseClient(
        tool_calls=[
            ("get_month_stats", {"month": "2026-07"}),
            ("get_trend_vs_last_month", {"month": "2026-07"}),
            ("get_previous_newsletter", {}),
        ],
        final_text="A good month for the clinic.",
    )

    ai.draft_monthly_newsletter_body(
        JULY, notes_text="Quiet month, one new volunteer.", client=client
    )

    # Scoped to the `messages` payload (the actual prompt/notes/tool-result
    # data) rather than the whole call kwargs — the static `tools` schema is
    # our own authored code, not patient-derived. The bare "name" entry in
    # PATIENT_IDENTIFYING_COLUMNS is excluded here: tool-use messages
    # structurally carry each *tool's* name (e.g. "get_month_stats") in a
    # "name" field/attribute, which would otherwise collide with a check
    # meant to catch a *patient's* name — a false positive specific to this
    # plan's tool-use shape, which Plan 08's non-tool-use payloads never hit.
    sent = json.dumps([call["messages"] for call in client.calls], default=str).lower()
    for column in PATIENT_IDENTIFYING_COLUMNS - {"name"}:
        assert column not in sent


def test_draft_monthly_newsletter_body_returns_none_when_client_raises(db):
    assert ai.draft_monthly_newsletter_body(JULY, client=_raising_client()) is None


def test_draft_monthly_newsletter_body_returns_none_on_empty_final_text(db):
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})], final_text=""
    )
    assert ai.draft_monthly_newsletter_body(JULY, client=client) is None


def test_draft_monthly_newsletter_body_returns_none_when_tool_loop_never_ends(db):
    """A model that only ever calls tools, never producing a final answer,
    must not spin the request forever."""

    class _AlwaysToolUse:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="tool_0",
                        name="get_month_stats",
                        input={"month": "2026-07"},
                    )
                ],
            )

    client = SimpleNamespace(messages=_AlwaysToolUse())
    assert ai.draft_monthly_newsletter_body(JULY, client=client) is None
    assert len(client.messages.calls) == ai.MAX_NEWSLETTER_TOOL_TURNS


def test_draft_monthly_newsletter_body_returns_none_on_a_non_end_turn_stop_reason(db):
    """A truncated (``max_tokens``) or refused response must never become the
    drafted text — only a clean ``end_turn`` completion is trusted."""

    class _TruncatedMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                stop_reason="max_tokens",
                content=[SimpleNamespace(type="text", text="This month, the clinic")],
            )

    client = SimpleNamespace(messages=_TruncatedMessages())
    assert ai.draft_monthly_newsletter_body(JULY, client=client) is None


# --- draft_monthly_newsletter: the write path + failure handling -----------


def test_draft_monthly_newsletter_records_failed_run_with_no_page_when_ai_call_fails(
    db,
):
    run = draft_monthly_newsletter(JULY, client=_raising_client())

    assert run.status == NewsletterDraftRun.STATUS_FAILED
    assert run.newsletter_page is None
    assert "2026-07" in run.error_message
    assert not NewsletterPage.objects.exists()


def test_draft_monthly_newsletter_creates_unpublished_draft_and_records_succeeded_run(
    db,
):
    home = HomePageFactory()
    DailyAggregateFactory(clinic_date=datetime.date(2026, 7, 5), total_visits=12)
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})],
        final_text="This month, the clinic saw 12 patients across one open day.",
    )

    run = draft_monthly_newsletter(
        JULY, notes_text="A quiet month.", client=client, triggered_by=None
    )

    assert run.status == NewsletterDraftRun.STATUS_SUCCEEDED
    page = run.newsletter_page
    assert page is not None
    assert page.live is False
    assert page.issue_date == JULY

    index = NewsletterIndexPage.objects.get()
    assert page.get_parent().pk == index.pk
    assert index.get_parent().pk == home.pk


def test_draft_monthly_newsletter_body_streamfield_contains_the_drafted_prose(db):
    HomePageFactory()
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})],
        final_text="Paragraph one.\n\nParagraph two.",
    )

    run = draft_monthly_newsletter(JULY, client=client)

    rendered = "".join(str(block.value) for block in run.newsletter_page.body)
    assert "Paragraph one." in rendered
    assert "Paragraph two." in rendered


def test_draft_monthly_newsletter_includes_consented_photos_in_the_body(db):
    from wagtail.images.tests.utils import Image, get_test_image_file

    home = HomePageFactory()
    gallery_page = GalleryPageFactory(parent=home)
    image = Image.objects.create(title="Camp day", file=get_test_image_file())
    gallery_image = GalleryImageFactory(
        page=gallery_page,
        image=image,
        caption="Camp day handout",
        consent_confirmed=True,
    )
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})],
        final_text="A wonderful camp day this month.",
    )

    run = draft_monthly_newsletter(
        JULY,
        photos=[
            NewsletterPhotoInput(
                image=gallery_image.image,
                caption=gallery_image.caption,
                alt_text=gallery_image.alt_text,
                consent_confirmed=True,
            )
        ],
        client=client,
    )

    photo_blocks = [
        block for block in run.newsletter_page.body if block.block_type == "photo"
    ]
    assert len(photo_blocks) == 1
    assert photo_blocks[0].value["caption"] == "Camp day handout"
    assert photo_blocks[0].value["consent_confirmed"] is True


def test_draft_monthly_newsletter_rejects_photos_without_confirmed_consent(db):
    from wagtail.images.tests.utils import Image, get_test_image_file

    HomePageFactory()
    image = Image.objects.create(title="Unconsented", file=get_test_image_file())

    with pytest.raises(ValueError, match="consent_confirmed"):
        draft_monthly_newsletter(
            JULY,
            photos=[NewsletterPhotoInput(image=image, consent_confirmed=False)],
            client=_ToolUseClient(tool_calls=[], final_text="text"),
        )

    assert not NewsletterPage.objects.exists()


# --- Draft-visibility + permission tests ------------------------------------


def test_draft_monthly_newsletter_draft_is_invisible_until_published(db):
    home = HomePageFactory()
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})], final_text="Some prose."
    )

    run = draft_monthly_newsletter(JULY, client=client)
    page = run.newsletter_page
    index = NewsletterIndexPage.objects.get()

    assert page not in list(index.get_newsletters())
    assert home.get_latest_newsletter() is None

    page.save_revision().publish()
    page.refresh_from_db()
    assert page in list(index.get_newsletters())
    assert home.get_latest_newsletter().pk == page.pk


def test_newsletter_page_cannot_be_published_by_automation_only_administrator(
    db, django_user_model
):
    """Invariant #4's general rule, for this plan specifically: the drafting
    code path (save_revision only) never grants publish permission — the
    same structural gate Plan 07 built for any AI-authored page."""
    HomePageFactory()
    client = _ToolUseClient(
        tool_calls=[("get_month_stats", {"month": "2026-07"})], final_text="Some prose."
    )
    run = draft_monthly_newsletter(JULY, client=client)
    page = run.newsletter_page

    administrator = django_user_model.objects.create_user(
        username="administrator-nl",
        password="x",  # noqa: S106
    )
    administrator.groups.add(Group.objects.get(name="Administrator"))
    automation = django_user_model.objects.create_user(
        username="automation-nl",
        password="x",  # noqa: S106
    )

    assert page.permissions_for_user(administrator).can_publish() is True
    assert page.permissions_for_user(automation).can_publish() is False
    assert page.live is False


# --- The management command trigger -----------------------------------------


def test_management_command_creates_a_draft_via_gallery_image_pick(
    db, monkeypatch, tmp_path
):
    from wagtail.images.tests.utils import Image, get_test_image_file

    home = HomePageFactory()
    gallery_page = GalleryPageFactory(parent=home)
    image = Image.objects.create(title="Camp day", file=get_test_image_file())
    gallery_image = GalleryImageFactory(
        page=gallery_page,
        image=image,
        caption="Camp day handout",
        consent_confirmed=True,
    )

    # The command never accepts a test client (a real run always uses the
    # real Anthropic client); monkeypatch the drafting call itself so this
    # test proves the command's CLI wiring end-to-end without touching the
    # forbidden real-client guard.
    monkeypatch.setattr(
        ai, "draft_monthly_newsletter_body", lambda *a, **k: "A wonderful month."
    )

    notes_path = tmp_path / "notes.md"
    notes_path.write_text("A quiet month, one new volunteer.")

    call_command(
        "draft_monthly_newsletter",
        "--month",
        "2026-07",
        "--notes",
        str(notes_path),
        "--gallery-image",
        str(gallery_image.pk),
    )

    run = NewsletterDraftRun.objects.get()
    assert run.status == NewsletterDraftRun.STATUS_SUCCEEDED
    photo_blocks = [
        block for block in run.newsletter_page.body if block.block_type == "photo"
    ]
    assert photo_blocks[0].value["caption"] == "Camp day handout"


def test_management_command_requires_confirm_consent_for_direct_photo_upload(
    db, tmp_path
):
    HomePageFactory()
    photo_path = tmp_path / "new.jpg"
    photo_path.write_bytes(b"not a real image, never read for this failure path")

    with pytest.raises(CommandError, match="confirm-consent"):
        call_command(
            "draft_monthly_newsletter",
            "--month",
            "2026-07",
            "--photo",
            f"{photo_path}:A caption",
        )

    assert not NewsletterDraftRun.objects.exists()


def test_management_command_uploads_no_photos_if_any_path_is_missing(db, tmp_path):
    """All --photo paths are validated up front — a later bad path must not
    leave an orphaned Image row behind from an earlier, valid one."""
    from wagtail.images.models import Image

    HomePageFactory()
    good_photo = tmp_path / "good.jpg"
    good_photo.write_bytes(b"pretend image bytes")

    with pytest.raises(CommandError, match="not found"):
        call_command(
            "draft_monthly_newsletter",
            "--month",
            "2026-07",
            "--photo",
            f"{good_photo}:Good photo",
            "--photo",
            f"{tmp_path / 'missing.jpg'}:Missing photo",
            "--confirm-consent",
        )

    assert not Image.objects.exists()
    assert not NewsletterDraftRun.objects.exists()


def test_management_command_safely_reports_failure_under_the_real_client_guard(db):
    """With no client override, the command hits the same autouse conftest
    guard as every other AI call in this codebase — it must degrade to "no
    draft created", never crash and never bypass the guard."""
    HomePageFactory()

    call_command("draft_monthly_newsletter", "--month", "2026-07")

    run = NewsletterDraftRun.objects.get()
    assert run.status == NewsletterDraftRun.STATUS_FAILED
    assert not NewsletterPage.objects.exists()


def test_management_command_rejects_an_invalid_month(db):
    with pytest.raises(CommandError, match="YYYY-MM"):
        call_command("draft_monthly_newsletter", "--month", "not-a-month")


# --- The audit trail's admin visibility (Plan 09's "failure visibility") ---


def test_administrator_can_view_the_newsletter_draft_run_snippet_listing(
    client, db, django_user_model
):
    """The acceptance criterion itself, exercised as a real request: a failed
    run must be visible to an Administrator somewhere in the admin console —
    not just grantable in principle via the migration."""
    from apps.pipeline.factories import NewsletterDraftRunFactory

    run = NewsletterDraftRunFactory(status=NewsletterDraftRun.STATUS_FAILED)
    administrator = django_user_model.objects.create_user(
        username="administrator-audit",
        password="x",  # noqa: S106
    )
    administrator.groups.add(Group.objects.get(name="Administrator"))
    client.force_login(administrator)

    response = client.get("/admin/snippets/pipeline/newsletterdraftrun/")

    assert response.status_code == 200
    assert run.get_status_display().encode() in response.content


def test_non_administrator_cannot_view_the_newsletter_draft_run_snippet_listing(
    client, db, django_user_model
):
    from django.contrib.auth.models import Permission

    other = django_user_model.objects.create_user(
        username="no-perm-audit", password="x"
    )  # noqa: S106
    other.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtailadmin", codename="access_admin"
        )
    )
    client.force_login(other)

    response = client.get("/admin/snippets/pipeline/newsletterdraftrun/")

    assert response.status_code == 302
