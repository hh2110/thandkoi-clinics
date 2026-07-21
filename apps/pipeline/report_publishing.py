"""Auto-create and auto-publish the daily report page for a clinic-date.

Maintainer decision (PR #15): one published ``DailyReportPage`` per
clinic-date, archivable under a single ``ReportIndexPage``, auto-published
straight to production — no draft step, since the parser producing its
numbers is committed and code-reviewed (unlike Plan 09's newsletter
narrative, which still requires a human to review and publish). This is the
one narrow, explicit exception to CLAUDE.md invariant #4 (2026-07-19) — see
``apps.pipeline.ai``'s Plan 08 section for the three properties that make it
safe, and ``.claude/plans/08-data-pipeline.md`` "The AI summary sentence".

Every figure the published page shows is read live from ``DailyAggregate``
(never copied onto the page) — the only thing this module writes onto the
page itself is the one AI-written summary sentence, and even that falls back
to an empty string rather than blocking publish.
"""

from __future__ import annotations

from datetime import date

from apps.core.models import HomePage
from apps.pipeline import ai
from apps.pipeline.models import DailyAggregate, DailyReportPage, ReportIndexPage

REPORT_INDEX_TITLE = "Reports"
REPORT_INDEX_SLUG = "reports"


def _get_or_create_report_index() -> ReportIndexPage:
    """The single ``ReportIndexPage``, created once under the site's Home page.

    Mirrors ``seed_core_content``'s ``_get`` idiom (Plan 04) for a singleton
    page: fetch if it exists, otherwise create it live under Home so the
    first ever ingest doesn't depend on a maintainer having clicked it into
    existence in ``/admin/`` beforehand. The slug matches the one the nav
    partial already links to (``/reports/``, wired ahead of this plan).
    """
    index = ReportIndexPage.objects.first()
    if index is not None:
        return index

    home = HomePage.objects.first()
    if home is None:
        raise RuntimeError(
            "No HomePage exists yet — cannot auto-create the Reports index. "
            "Run `seed_initial_content` first."
        )
    index = ReportIndexPage(title=REPORT_INDEX_TITLE, slug=REPORT_INDEX_SLUG, live=True)
    home.add_child(instance=index)
    index.save_revision().publish()
    return index


def publish_daily_report(clinic_date: date, *, client=None) -> DailyReportPage:
    """Create/update and auto-publish the daily report page for ``clinic_date``.

    ``client`` is dependency-injected the same way as every other Anthropic
    call in this codebase (Plan 02's convention) — ``None`` in production
    (the real client is built lazily inside
    :func:`apps.pipeline.ai.draft_daily_summary_sentence`), an explicit mock
    in tests. Whatever ``client`` returns (including nothing, on failure)
    never blocks this function from publishing the deterministic numbers.
    """
    aggregate = DailyAggregate.objects.get(clinic_date=clinic_date)
    summary_sentence = ai.draft_daily_summary_sentence(aggregate, client) or ""

    index = _get_or_create_report_index()
    page = DailyReportPage.objects.filter(report_date=clinic_date).first()
    if page is None:
        page = DailyReportPage(
            title=f"Daily report — {clinic_date.isoformat()}",
            slug=clinic_date.isoformat(),
            report_date=clinic_date,
            aggregate=aggregate,
            summary_sentence=summary_sentence,
            live=False,
        )
        index.add_child(instance=page)
    else:
        page.aggregate = aggregate
        page.summary_sentence = summary_sentence

    revision = page.save_revision()
    revision.publish()
    return page
