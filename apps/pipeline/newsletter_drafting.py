"""Land a monthly newsletter draft — Plan 09's write path.

Mirrors ``apps.pipeline.report_publishing``'s shape (auto-create the index if
missing, build the page, save it) with the one deliberate difference Plan 09
requires: this module calls ``save_revision()`` and never ``.publish()``.
There is no publish permission anywhere in this code path (Plan 07's
"AI/automation code holds no publish permission"), and on any drafting
failure the correct behaviour is **no draft at all** — the opposite of
``report_publishing.publish_daily_report``, which must ship its numbers
regardless of the AI call's outcome (see CLAUDE.md invariant #4's exception
for that one narrow case, which explicitly does not extend here).

Every run — success or failure — produces exactly one
``NewsletterDraftRun`` audit row, so a failed run is always visible to an
Administrator even though nothing is emailed or alerted (Plan 09's "failure
visibility" decision, PR #17).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.utils.html import escape

from apps.core.models import HomePage, NewsletterIndexPage, NewsletterPage
from apps.pipeline import ai
from apps.pipeline.models import NewsletterDraftRun

NEWSLETTER_INDEX_TITLE = "Newsletters"
NEWSLETTER_INDEX_SLUG = "newsletters"


@dataclass(frozen=True)
class NewsletterPhotoInput:
    """One photo to attach to the drafted issue.

    ``consent_confirmed`` must already be ``True`` by the time this reaches
    :func:`draft_monthly_newsletter` — enforced by its caller (the management
    command), which only ever builds one of these from an existing,
    consent-gated ``GalleryImage`` or from a direct upload the operator has
    explicitly confirmed consent for (Plan 06's convention, extended to
    direct uploads per the maintainer's PR #17 decision).
    """

    image: object  # wagtailimages.Image
    caption: str = ""
    alt_text: str = ""
    consent_confirmed: bool = False


def _get_or_create_newsletter_index() -> NewsletterIndexPage:
    """The single ``NewsletterIndexPage``, created once under Home.

    Same idiom as ``report_publishing._get_or_create_report_index`` (Plan
    08): fetch if it exists (normally seeded by ``seed_initial_content``),
    otherwise create it live so a first-ever draft doesn't depend on a
    maintainer having clicked it into existence beforehand.
    """
    index = NewsletterIndexPage.objects.first()
    if index is not None:
        return index

    home = HomePage.objects.first()
    if home is None:
        raise RuntimeError(
            "No HomePage exists yet — cannot auto-create the Newsletters "
            "index. Run `seed_initial_content` first."
        )
    index = NewsletterIndexPage(
        title=NEWSLETTER_INDEX_TITLE, slug=NEWSLETTER_INDEX_SLUG, live=True
    )
    home.add_child(instance=index)
    index.save_revision().publish()
    return index


def _build_newsletter_body(
    prose: str, photos: list[NewsletterPhotoInput]
) -> list[tuple[str, object]]:
    """Assemble the ``NewsletterPage.body`` StreamField value.

    ``prose`` is split on blank lines into separate ``paragraph`` blocks
    (Plan 06's ``RichTextBlock``) and HTML-escaped before wrapping — this is
    model-generated text, not an admin's own trusted markup. Photos reuse
    Plan 04/06's ``ConsentedImageBlock`` shape.
    """
    paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
    body: list[tuple[str, object]] = [
        ("paragraph", f"<p>{escape(paragraph)}</p>") for paragraph in paragraphs
    ]
    for photo in photos:
        body.append(
            (
                "photo",
                {
                    "image": photo.image,
                    "alt_text": photo.alt_text,
                    "caption": photo.caption,
                    "consent_confirmed": photo.consent_confirmed,
                },
            )
        )
    return body


def draft_monthly_newsletter(
    month: datetime.date,
    *,
    notes_text: str = "",
    photos: list[NewsletterPhotoInput] | None = None,
    triggered_by=None,
    client=None,
) -> NewsletterDraftRun:
    """Run one monthly-newsletter drafting attempt; always returns an audit row.

    On success: creates an **unpublished** ``NewsletterPage`` revision under
    ``NewsletterIndexPage`` (``save_revision()``, no ``.publish()`` call
    anywhere in this path) and returns a ``NewsletterDraftRun`` with
    ``status=STATUS_SUCCEEDED`` referencing it.

    On failure — the AI call fails, times out, or fails its sanity check —
    creates **no** ``NewsletterPage`` at all and returns a
    ``NewsletterDraftRun`` with ``status=STATUS_FAILED``. This is the
    opposite of Plan 08's daily page: there is no deterministic content
    riding alongside the AI prose here that needs to ship unconditionally, so
    "run again later" is the correct behaviour, never a fallback publish.
    """
    photos = photos or []
    if any(not photo.consent_confirmed for photo in photos):
        raise ValueError(
            "Every photo attached to a newsletter draft must already have "
            "consent_confirmed=True (brand-guidelines.md §5) — the caller "
            "must enforce this before calling draft_monthly_newsletter."
        )

    month = month.replace(day=1)
    body_text = ai.draft_monthly_newsletter_body(
        month,
        notes_text=notes_text,
        photo_captions=[photo.caption for photo in photos],
        client=client,
    )

    if body_text is None:
        return NewsletterDraftRun.objects.create(
            month=month,
            status=NewsletterDraftRun.STATUS_FAILED,
            error_message=(
                "The AI drafting call failed, timed out, or returned an "
                f"empty/unusable draft for {month:%Y-%m}. No newsletter "
                "draft was created. Re-run the management command once "
                "ready to try again."
            ),
            triggered_by=triggered_by,
        )

    index = _get_or_create_newsletter_index()
    page = NewsletterPage(
        title=f"Newsletter — {month:%B %Y}",
        slug=f"newsletter-{month:%Y-%m}",
        issue_date=month,
        summary="",
        body=_build_newsletter_body(body_text, photos),
        live=False,
    )
    index.add_child(instance=page)
    page.save_revision()

    return NewsletterDraftRun.objects.create(
        month=month,
        status=NewsletterDraftRun.STATUS_SUCCEEDED,
        newsletter_page=page,
        triggered_by=triggered_by,
    )
