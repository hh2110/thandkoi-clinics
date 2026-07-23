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

from apps.core.models import CampReportIndexPage, HomePage
from apps.pipeline import ai, freetext
from apps.pipeline.models import (
    CampUploadReportPage,
    DailyAggregate,
    DailyReportPage,
    DeidentifiedVisit,
    IngestRun,
    ReportIndexPage,
)

REPORT_INDEX_TITLE = "Reports"
REPORT_INDEX_SLUG = "reports"

CAMP_REPORT_INDEX_TITLE = "Camp Reports"
CAMP_REPORT_INDEX_SLUG = "camp-reports"


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


def _get_or_create_camp_report_index() -> CampReportIndexPage:
    """The single ``CampReportIndexPage`` (Plan 06), created if it doesn't
    exist yet — same idiom as :func:`_get_or_create_report_index`, and the
    same title/slug ``seed_initial_content`` already uses, so this is a no-op
    once that command (or a maintainer, by hand) has created it."""
    index = CampReportIndexPage.objects.first()
    if index is not None:
        return index

    home = HomePage.objects.first()
    if home is None:
        raise RuntimeError(
            "No HomePage exists yet — cannot auto-create the Camp Reports "
            "index. Run `seed_initial_content` first."
        )
    index = CampReportIndexPage(
        title=CAMP_REPORT_INDEX_TITLE, slug=CAMP_REPORT_INDEX_SLUG, live=True
    )
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
    empty-columns-flag *drafts* from this date's ``DeidentifiedVisit`` rows.
    Unlike ``summary_sentence`` above, these two never get auto-approved for
    the public page here — only their ``_draft`` field is written; the
    corresponding ``_approved`` boolean is left exactly as it was (``False``
    for a brand new page, whatever a person last set it to for an existing
    one). See ``DailyReportPage``'s docstring/fields for the full review-gate
    contract this is deliberately not widening past.
    """
    aggregate = DailyAggregate.objects.get(
        clinic_date=clinic_date, report_kind=IngestRun.KIND_DAILY
    )
    summary_sentence = ai.draft_daily_summary_sentence(aggregate, client) or ""

    visits = list(
        DeidentifiedVisit.objects.filter(
            visit_date=clinic_date, ingest_run__report_kind=IngestRun.KIND_DAILY
        )
    )
    freetext_columns = freetext.collect_freetext_entries(visits)
    empty_columns = freetext.compute_empty_columns(visits)
    freetext_summary_draft = (
        ai.draft_freetext_summary(clinic_date, freetext_columns, client) or ""
    )
    empty_columns_flag_draft = (
        ai.draft_empty_columns_flag(clinic_date, empty_columns, client) or ""
    )

    index = _get_or_create_report_index()
    page = DailyReportPage.objects.filter(report_date=clinic_date).first()
    if page is None:
        page = DailyReportPage(
            title=f"Daily report — {clinic_date.isoformat()}",
            slug=clinic_date.isoformat(),
            report_date=clinic_date,
            aggregate=aggregate,
            summary_sentence=summary_sentence,
            freetext_summary_draft=freetext_summary_draft,
            empty_columns_flag_draft=empty_columns_flag_draft,
            live=False,
        )
        index.add_child(instance=page)
    else:
        page.aggregate = aggregate
        page.summary_sentence = summary_sentence
        page.freetext_summary_draft = freetext_summary_draft
        page.empty_columns_flag_draft = empty_columns_flag_draft

    revision = page.save_revision()
    revision.publish()
    return page


def publish_camp_report(clinic_date: date, *, camp_title: str) -> CampUploadReportPage:
    """Create/update and auto-publish the camp report page for ``clinic_date``.

    Mirrors :func:`publish_daily_report`'s auto-publish pattern (maintainer
    decision, PR #15: no draft step, since the parser producing these numbers
    is committed and code-reviewed) — but see ``CampUploadReportPage``'s
    docstring for why this deliberately does **not** call
    :func:`apps.pipeline.ai.draft_daily_summary_sentence` the way the daily
    report does: CLAUDE.md's invariant #4 exception for that call is scoped to
    the daily report specifically, and widening it is a decision left for the
    maintainer to make deliberately, not to assume by analogy. There is
    therefore no ``client`` parameter here — nothing to inject.
    """
    aggregate = DailyAggregate.objects.get(
        clinic_date=clinic_date, report_kind=IngestRun.KIND_CAMP
    )

    index = _get_or_create_camp_report_index()
    page = CampUploadReportPage.objects.filter(camp_date=clinic_date).first()
    if page is None:
        page = CampUploadReportPage(
            title=camp_title,
            # "camp-" prefix, not the bare ISO date: CampReportIndexPage now
            # hosts this auto-published type alongside the manually-authored
            # core.CampReportPage as siblings, and Wagtail enforces slug
            # uniqueness across ALL sibling types under one parent, not just
            # same-type -- an editor naming their manual page's slug after
            # its date (a very natural choice) would otherwise collide with
            # this auto-generated slug and raise an unhandled ValidationError
            # from add_child(), after this date's ingest data has already
            # committed.
            slug=f"camp-{clinic_date.isoformat()}",
            camp_date=clinic_date,
            camp_title=camp_title,
            aggregate=aggregate,
            live=False,
        )
        index.add_child(instance=page)
    else:
        page.title = camp_title
        page.camp_title = camp_title
        page.aggregate = aggregate

    revision = page.save_revision()
    revision.publish()
    return page
