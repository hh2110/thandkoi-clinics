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

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from apps.core.models import HomePage
from apps.pipeline import ai, freetext
from apps.pipeline.models import (
    DailyAggregate,
    DailyReportPage,
    DeidentifiedVisit,
    ReportIndexPage,
)

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

    Plan 11 Track B8/B9: this also (re)generates the free-text summary and
    empty-columns-flag from this date's ``DeidentifiedVisit`` rows and
    auto-publishes them alongside the numbers, same as ``summary_sentence``
    above — CLAUDE.md invariant #4's exception, widened 2026-07-23
    (maintainer decision) to cover these two as well.

    If a re-ingest's call fails (transient API error/timeout), the existing
    page's field is left untouched rather than overwritten with an empty
    string — otherwise a transient failure on a later re-upload would
    silently blank an already-public summary/flag with no record anything
    changed (found by code-review-tc, when this was still a review-gated
    draft — the same protection matters even more now that these values
    reach the public page directly). A brand new page has nothing to
    preserve, so it falls back to ``""`` as before.

    The three drafting calls are independent of each other and run
    concurrently (found by code-review-tc: they used to run sequentially,
    tripling this function's worst-case latency inside the synchronous
    upload request that calls it).
    """
    aggregate = DailyAggregate.objects.get(clinic_date=clinic_date)

    visits = list(DeidentifiedVisit.objects.filter(visit_date=clinic_date))
    freetext_columns = freetext.collect_freetext_entries(visits)
    empty_columns = freetext.empty_columns_from_entries(freetext_columns)

    with ThreadPoolExecutor(max_workers=3) as executor:
        summary_future = executor.submit(
            ai.draft_daily_summary_sentence, aggregate, client
        )
        freetext_future = executor.submit(
            ai.draft_freetext_summary, clinic_date, freetext_columns, client
        )
        empty_future = executor.submit(
            ai.draft_empty_columns_flag, clinic_date, empty_columns, client
        )
        summary_sentence = summary_future.result() or ""
        new_freetext_summary = freetext_future.result()
        new_empty_columns_flag = empty_future.result()

    index = _get_or_create_report_index()
    page = DailyReportPage.objects.filter(report_date=clinic_date).first()
    if page is None:
        page = DailyReportPage(
            title=f"Daily report — {clinic_date.isoformat()}",
            slug=clinic_date.isoformat(),
            report_date=clinic_date,
            aggregate=aggregate,
            summary_sentence=summary_sentence,
            freetext_summary=new_freetext_summary or "",
            empty_columns_flag=new_empty_columns_flag or "",
            live=False,
        )
        index.add_child(instance=page)
    else:
        page.aggregate = aggregate
        page.summary_sentence = summary_sentence
        if new_freetext_summary:
            page.freetext_summary = new_freetext_summary
        if new_empty_columns_flag:
            page.empty_columns_flag = new_empty_columns_flag

    revision = page.save_revision()
    revision.publish()
    return page
