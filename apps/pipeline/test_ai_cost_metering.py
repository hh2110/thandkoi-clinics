"""Plan 11 C2 — Anthropic API cost metering, surfaced in the admin panel.

Mirrors ``apps/pipeline/test_newsletter.py``'s shape (Plan 09): plain,
deterministic Python assertions, never a live model call — the real
Anthropic client is impossible to construct here (see the autouse
``_forbid_real_anthropic`` guard in the project ``conftest.py``).

Three things are covered:

* ``ai_pricing.compute_cost_usd`` — the cost-calculation math itself.
* Each of the five real call sites in ``apps.pipeline.ai`` writes an
  ``AiCallLog`` row after a successful call — including
  ``draft_freetext_summary``/``draft_empty_columns_flag`` (B8/B9), found
  unmetered and fixed as a Plan 11 C2 follow-up.
* The admin listing (registered in ``apps.pipeline.wagtail_hooks``) renders
  for an Administrator, including the summed running total.

Every test below asserts on an exact ``AiCallLog`` row/count (``.get()``,
``len(...)``, a running-total string), so this file needs a clean table at
the start of each test — see ``_clean_ai_call_log`` below for why that isn't
automatic.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

from apps.pipeline import ai
from apps.pipeline.aggregation import ClinicAggregate
from apps.pipeline.ai_pricing import PRICING_PER_MILLION_TOKENS, compute_cost_usd
from apps.pipeline.factories import AiCallLogFactory, DailyAggregateFactory
from apps.pipeline.models import AiCallLog

JULY = datetime.date(2026, 7, 1)


@pytest.fixture(autouse=True)
def _clean_ai_call_log(db):
    """Start every test in this file with an empty ``AiCallLog`` table.

    ``apps.pipeline.report_publishing.publish_daily_report`` (exercised by
    many tests elsewhere, e.g. ``apps/pipeline/tests.py``) runs its three AI
    drafting calls concurrently via ``ThreadPoolExecutor``. Each thread gets
    its own DB connection, so its ``AiCallLog.record(...)`` write is *not*
    part of the calling test's transaction and is never rolled back by
    pytest-django's ``db`` fixture — it lands in the real test database and
    stays there for every test that runs afterward, in any file. This file's
    tests assert on an exact row (``AiCallLog.objects.get()``) or an exact
    running total, so a row leaked in from an unrelated earlier test
    produces ``MultipleObjectsReturned`` or a wrong total — not a fault in
    the assertion, just a dirty starting table. Clearing here, rather than
    changing the (deliberately concurrent, see ``report_publishing.py``)
    production code or converting every threaded test elsewhere to
    ``transactional_db``, keeps the fix scoped to the tests that actually
    depend on an exact count.
    """
    AiCallLog.objects.all().delete()


def _stub_client(text: str, input_tokens: int, output_tokens: int):
    """A minimal Anthropic-client stand-in shared by every test below.

    Shaped to satisfy all three real call sites: ``draft_newsletter_prose``
    and ``draft_daily_summary_sentence`` only read ``.content[0].text`` and
    (per Plan 11 C2) ``.usage``; ``draft_monthly_newsletter_body`` also reads
    ``.stop_reason``, so this returns an immediate ``end_turn`` — a one-turn
    conversation with no tool calls, sufficient to exercise its success path.
    """

    def _create(**kwargs):
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=input_tokens, output_tokens=output_tokens
            ),
        )

    return SimpleNamespace(messages=SimpleNamespace(create=_create))


# --- Cost calculation math ---------------------------------------------------


def test_every_live_model_constant_has_a_pricing_entry():
    """Found by code-review-tc: compute_cost_usd silently returns $0 for an
    unrecognized model (by design, so an unrecognized model never crashes the
    call it's logging) — but nothing previously caught a live model constant
    drifting out of sync with PRICING_PER_MILLION_TOKENS, which would zero
    out AI spend logging with no test or runtime signal. This guards it."""
    live_models = {
        ai.DRAFTING_MODEL,
        ai.DAILY_SUMMARY_MODEL,
        ai.MONTHLY_NEWSLETTER_MODEL,
    }
    assert live_models <= PRICING_PER_MILLION_TOKENS.keys()


def test_compute_cost_usd_matches_published_per_million_token_rates():
    """1,000,000 input + 1,000,000 output tokens must cost exactly the
    published per-model rate — the simplest possible cross-check of the
    math against ``PRICING_PER_MILLION_TOKENS`` itself."""
    for model, (input_rate, output_rate) in PRICING_PER_MILLION_TOKENS.items():
        cost = compute_cost_usd(model, 1_000_000, 1_000_000)
        assert cost == input_rate + output_rate


def test_compute_cost_usd_scales_linearly_with_token_counts():
    input_rate, output_rate = PRICING_PER_MILLION_TOKENS["claude-haiku-4-5"]
    cost = compute_cost_usd("claude-haiku-4-5", 2_000, 500)
    expected = (Decimal(2_000) * input_rate + Decimal(500) * output_rate) / Decimal(
        "1000000"
    )
    assert cost == expected
    assert cost > 0


def test_compute_cost_usd_returns_zero_for_an_unrecognized_model():
    """An unknown/renamed model must never raise — just under-report as $0,
    visibly, rather than crash the call it's meant to be logging."""
    assert compute_cost_usd("some-future-model", 1000, 1000) == Decimal("0")


def test_ai_call_log_record_does_not_truncate_a_small_call_to_zero(db):
    """Found by code-review-tc: cost_usd used to be DecimalField(decimal_places=4),
    silently rounding a small/cheap call (well within a single request's normal
    token counts) down to $0.0000 and undercounting the admin's running total.
    """
    log = AiCallLog.record(
        call_site=AiCallLog.CALL_SITE_DAILY_SUMMARY,
        model="claude-haiku-4-5",
        input_tokens=10,
        output_tokens=5,
    )
    input_rate, output_rate = PRICING_PER_MILLION_TOKENS["claude-haiku-4-5"]
    expected = (Decimal(10) * input_rate + Decimal(5) * output_rate) / Decimal(
        "1000000"
    )
    assert expected == Decimal("0.000035")
    assert log.cost_usd == expected
    assert log.cost_usd != Decimal("0")
    assert AiCallLog.objects.get(pk=log.pk).cost_usd == expected


def test_ai_call_log_record_computes_and_persists_cost(db):
    log = AiCallLog.record(
        call_site=AiCallLog.CALL_SITE_DAILY_SUMMARY,
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=200,
    )
    input_rate, output_rate = PRICING_PER_MILLION_TOKENS["claude-haiku-4-5"]
    expected = (Decimal(1000) * input_rate + Decimal(200) * output_rate) / Decimal(
        "1000000"
    )
    assert log.cost_usd == expected
    assert AiCallLog.objects.get(pk=log.pk).cost_usd == expected


# --- Logging happens at each of the three real call sites -------------------


def test_draft_newsletter_prose_logs_an_ai_call(db):
    aggregate = ClinicAggregate(total_patients=5, by_gender={"female": 5})
    client = _stub_client("Some prose.", input_tokens=300, output_tokens=60)

    ai.draft_newsletter_prose(aggregate, client)

    log = AiCallLog.objects.get()
    assert log.call_site == AiCallLog.CALL_SITE_NEWSLETTER_PROSE
    assert log.model == ai.DRAFTING_MODEL
    assert log.input_tokens == 300
    assert log.output_tokens == 60
    assert log.cost_usd == compute_cost_usd(ai.DRAFTING_MODEL, 300, 60)


def test_draft_daily_summary_sentence_logs_an_ai_call(db):
    aggregate = DailyAggregateFactory(clinic_date=JULY, total_visits=4)
    client = _stub_client("Today the clinic saw 4 visits.", 150, 30)

    sentence = ai.draft_daily_summary_sentence(aggregate, client)

    assert sentence
    log = AiCallLog.objects.get()
    assert log.call_site == AiCallLog.CALL_SITE_DAILY_SUMMARY
    assert log.model == ai.DAILY_SUMMARY_MODEL
    assert log.input_tokens == 150
    assert log.output_tokens == 30
    assert log.cost_usd == compute_cost_usd(ai.DAILY_SUMMARY_MODEL, 150, 30)


def test_draft_daily_summary_sentence_still_logs_when_the_text_fails_sanity_check(db):
    """A response that comes back but fails the length sanity check still
    burned tokens — it must still be logged, even though the caller falls
    back to no sentence (see the ``draft_daily_summary_sentence`` docstring's
    Plan 11 C2 note on this choice)."""
    aggregate = DailyAggregateFactory(clinic_date=JULY, total_visits=4)
    too_long_text = "x" * (ai.MAX_DAILY_SUMMARY_LENGTH + 1)
    client = _stub_client(too_long_text, 200, 500)

    sentence = ai.draft_daily_summary_sentence(aggregate, client)

    assert sentence is None
    log = AiCallLog.objects.get()
    assert log.input_tokens == 200
    assert log.output_tokens == 500


def test_draft_daily_summary_sentence_logs_nothing_when_the_client_raises(db):
    """No response ever came back, so there is nothing to log — this must
    not be confused with the "response but bad text" case above."""

    def _raise(**kwargs):
        raise TimeoutError("simulated AI timeout")

    raising_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))
    aggregate = DailyAggregateFactory(clinic_date=JULY, total_visits=4)

    assert ai.draft_daily_summary_sentence(aggregate, raising_client) is None
    assert not AiCallLog.objects.exists()


def test_draft_daily_summary_sentence_survives_a_logging_failure(db, monkeypatch):
    """Found by code-review-tc: ``_log_ai_call`` used to run inside the same
    ``except Exception`` that governs the whole Anthropic call, so a DB error
    while writing the audit-log row silently discarded an already-successful,
    already-billed sentence. A logging failure must never do that."""
    aggregate = DailyAggregateFactory(clinic_date=JULY, total_visits=4)
    client = _stub_client("Today the clinic saw 4 visits.", 150, 30)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(AiCallLog, "record", _raise)

    sentence = ai.draft_daily_summary_sentence(aggregate, client)

    assert sentence == "Today the clinic saw 4 visits."
    assert not AiCallLog.objects.exists()


# --- B8/B9: free-text summary + empty-columns flag (found unmetered) -------
#
# draft_freetext_summary/draft_empty_columns_flag shipped (Plan 11 B8/B9)
# before cost metering (C2) existed, and neither branch wired the other in —
# these two real call sites went unlogged until this was found and fixed.
# Same four-test shape as the daily-summary sentence above.


def test_draft_freetext_summary_logs_an_ai_call(db):
    columns = {"presenting_complaints": ["fever", "cough"]}
    client = _stub_client("Common themes: fever and cough.", 180, 40)

    summary = ai.draft_freetext_summary(JULY, columns, client)

    assert summary
    log = AiCallLog.objects.get()
    assert log.call_site == AiCallLog.CALL_SITE_FREETEXT_SUMMARY
    assert log.model == ai.FREETEXT_SUMMARY_MODEL
    assert log.input_tokens == 180
    assert log.output_tokens == 40
    assert log.cost_usd == compute_cost_usd(ai.FREETEXT_SUMMARY_MODEL, 180, 40)


def test_draft_freetext_summary_still_logs_when_the_text_fails_sanity_check(db):
    """Same guarantee as the daily-summary case: tokens were spent even if
    the response fails the length sanity check afterwards."""
    columns = {"presenting_complaints": ["fever"]}
    too_long_text = "x" * (ai.MAX_FREETEXT_SUMMARY_LENGTH + 1)
    client = _stub_client(too_long_text, 220, 600)

    summary = ai.draft_freetext_summary(JULY, columns, client)

    assert summary is None
    log = AiCallLog.objects.get()
    assert log.input_tokens == 220
    assert log.output_tokens == 600


def test_draft_freetext_summary_logs_nothing_when_the_client_raises(db):
    def _raise(**kwargs):
        raise TimeoutError("simulated AI timeout")

    raising_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))
    columns = {"presenting_complaints": ["fever"]}

    assert ai.draft_freetext_summary(JULY, columns, raising_client) is None
    assert not AiCallLog.objects.exists()


def test_draft_freetext_summary_survives_a_logging_failure(db, monkeypatch):
    columns = {"presenting_complaints": ["fever"]}
    client = _stub_client("Common themes: fever.", 180, 40)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(AiCallLog, "record", _raise)

    summary = ai.draft_freetext_summary(JULY, columns, client)

    assert summary == "Common themes: fever."
    assert not AiCallLog.objects.exists()


def test_draft_empty_columns_flag_logs_an_ai_call(db):
    empty_columns = {"investigation": True, "presenting_complaints": False}
    client = _stub_client('["Investigation"]', 90, 15)

    flag = ai.draft_empty_columns_flag(JULY, empty_columns, client)

    assert flag
    log = AiCallLog.objects.get()
    assert log.call_site == AiCallLog.CALL_SITE_EMPTY_COLUMNS_FLAG
    assert log.model == ai.EMPTY_COLUMNS_FLAG_MODEL
    assert log.input_tokens == 90
    assert log.output_tokens == 15
    assert log.cost_usd == compute_cost_usd(ai.EMPTY_COLUMNS_FLAG_MODEL, 90, 15)


def test_draft_empty_columns_flag_still_logs_when_the_text_fails_sanity_check(db):
    empty_columns = {"investigation": True}
    too_long_text = "x" * (ai.MAX_EMPTY_COLUMNS_FLAG_LENGTH + 1)
    client = _stub_client(too_long_text, 100, 200)

    flag = ai.draft_empty_columns_flag(JULY, empty_columns, client)

    assert flag is None
    log = AiCallLog.objects.get()
    assert log.input_tokens == 100
    assert log.output_tokens == 200


def test_draft_empty_columns_flag_logs_nothing_when_the_client_raises(db):
    def _raise(**kwargs):
        raise TimeoutError("simulated AI timeout")

    raising_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))
    empty_columns = {"investigation": True}

    assert ai.draft_empty_columns_flag(JULY, empty_columns, raising_client) is None
    assert not AiCallLog.objects.exists()


def test_draft_empty_columns_flag_survives_a_logging_failure(db, monkeypatch):
    empty_columns = {"investigation": True}
    client = _stub_client('["Investigation"]', 90, 15)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(AiCallLog, "record", _raise)

    flag = ai.draft_empty_columns_flag(JULY, empty_columns, client)

    assert flag == '["Investigation"]'
    assert not AiCallLog.objects.exists()


def test_draft_monthly_newsletter_body_survives_a_logging_failure(db, monkeypatch):
    """Same guarantee as the daily-summary case above, for the newsletter's
    multi-turn tool loop."""
    client = _stub_client("A wonderful month for the clinic.", 400, 120)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(AiCallLog, "record", _raise)

    text = ai.draft_monthly_newsletter_body(JULY, client=client)

    assert text == "A wonderful month for the clinic."
    assert not AiCallLog.objects.exists()


def test_draft_monthly_newsletter_body_logs_an_ai_call(db):
    client = _stub_client("A wonderful month for the clinic.", 400, 120)

    text = ai.draft_monthly_newsletter_body(JULY, client=client)

    assert text == "A wonderful month for the clinic."
    log = AiCallLog.objects.get()
    assert log.call_site == AiCallLog.CALL_SITE_MONTHLY_NEWSLETTER
    assert log.model == ai.MONTHLY_NEWSLETTER_MODEL
    assert log.input_tokens == 400
    assert log.output_tokens == 120
    assert log.cost_usd == compute_cost_usd(ai.MONTHLY_NEWSLETTER_MODEL, 400, 120)


def test_draft_monthly_newsletter_body_logs_one_row_per_tool_turn(db):
    """Every ``messages.create`` call in the tool-use loop is a real, billed
    Anthropic call — a multi-turn draft must log one row per turn, not just
    the final answer."""

    class _TwoTurnMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
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
                    usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                )
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="Final answer.")],
                usage=SimpleNamespace(input_tokens=250, output_tokens=80),
            )

    client = SimpleNamespace(messages=_TwoTurnMessages())

    text = ai.draft_monthly_newsletter_body(JULY, client=client)

    assert text == "Final answer."
    logs = list(AiCallLog.objects.order_by("created_at"))
    assert len(logs) == 2
    assert [(log.input_tokens, log.output_tokens) for log in logs] == [
        (100, 20),
        (250, 80),
    ]
    assert all(log.call_site == AiCallLog.CALL_SITE_MONTHLY_NEWSLETTER for log in logs)


def test_draft_monthly_newsletter_body_logs_nothing_when_the_client_raises(db):
    def _raise(**kwargs):
        raise TimeoutError("simulated AI timeout")

    raising_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))

    assert ai.draft_monthly_newsletter_body(JULY, client=raising_client) is None
    assert not AiCallLog.objects.exists()


# --- Admin visibility --------------------------------------------------------


def test_administrator_can_view_the_ai_call_log_listing_with_running_total(
    client, db, django_user_model
):
    """The acceptance criterion itself: cost is visible to an Administrator
    in the admin console, including a summed running total across rows —
    not just grantable in principle via the migration."""
    AiCallLogFactory(
        call_site=AiCallLog.CALL_SITE_DAILY_SUMMARY,
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=Decimal("0.0020"),
    )
    AiCallLogFactory(
        call_site=AiCallLog.CALL_SITE_MONTHLY_NEWSLETTER,
        model="claude-sonnet-5",
        input_tokens=2000,
        output_tokens=500,
        cost_usd=Decimal("0.0090"),
    )
    administrator = django_user_model.objects.create_user(
        username="administrator-ai-cost",
        password="x",  # noqa: S106
    )
    administrator.groups.add(Group.objects.get(name="Administrator"))
    client.force_login(administrator)

    response = client.get("/admin/snippets/pipeline/aicalllog/")

    assert response.status_code == 200
    assert b"claude-haiku-4-5" in response.content
    assert b"claude-sonnet-5" in response.content
    # 0.0020 + 0.0090 == 0.0110 -- the running total this view computes.
    assert b"0.0110" in response.content


def test_non_administrator_cannot_view_the_ai_call_log_listing(
    client, db, django_user_model
):
    from django.contrib.auth.models import Permission

    other = django_user_model.objects.create_user(
        username="no-perm-ai-cost", password="x"
    )  # noqa: S106
    other.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtailadmin", codename="access_admin"
        )
    )
    client.force_login(other)

    response = client.get("/admin/snippets/pipeline/aicalllog/")

    assert response.status_code == 302
