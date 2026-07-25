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


#: Maps each :data:`apps.pipeline.freetext.FREETEXT_SUMMARY_GROUPS` key onto
#: its ``DailyReportPage`` field name (Plan 14, 2026-07-24) — the one place
#: that wiring lives, so the per-field preserve-on-falsy loop below and any
#: future caller share a single source of truth for the mapping.
_FREETEXT_SUMMARY_GROUP_FIELDS = {
    freetext.GROUP_MALE_ADULTS: "freetext_summary_male_adults",
    freetext.GROUP_FEMALE_ADULTS: "freetext_summary_female_adults",
    freetext.GROUP_CHILDREN: "freetext_summary_children",
}


def _resolve_group_summary(
    group: str,
    *,
    freetext_groups: dict[str, dict[str, list[str]]],
    group_visit_counts: dict[str, int],
    new_by_group: dict[str, str],
) -> str | None:
    """Decide one group's summary field value: a string to write, or ``None``.

    Returns:

    * ``""`` — *positively* blank this field, deterministically, regardless of
      what the model returned. This is the case when the group is below the
      Plan 15 Track C3 visit floor (:data:`freetext.MIN_GROUP_VISITS_TO_SUMMARISE`)
      or collected no free-text entries at all today. A correction that
      removes a group's visits (or all its free text) must clear the stale
      PHI-derived prose that a prior upload published (Track B2), rather than
      leave it stranded next to a now-zero count.
    * the fresh model value — when the group is eligible (at/above the floor
      *and* has entries) and the model returned a usable summary for it.
    * ``None`` — *preserve* whatever the field already holds. Reserved
      strictly for the genuine-call-failure case: an eligible group whose
      model call failed, timed out, or returned nothing usable for this key
      alone. Preserving here keeps a transient failure on a corrective
      re-upload from silently blanking an already-public summary (Track B1/B2's
      preserve-on-falsy rule, now applied only where it belongs). A brand-new
      page has nothing to preserve, so its caller coerces ``None`` to ``""``.
    """
    below_floor = group_visit_counts[group] < freetext.MIN_GROUP_VISITS_TO_SUMMARISE
    if below_floor or not freetext.group_has_freetext_entries(freetext_groups[group]):
        return ""
    return new_by_group.get(group) or None


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
    (maintainer decision) to cover these two as well. Plan 14 (2026-07-24)
    splits the free-text summary into three per-category fields (see
    ``_FREETEXT_SUMMARY_GROUP_FIELDS``) instead of one — B9's empty-columns
    flag is unaffected and still runs over every visit regardless of group.

    If a re-ingest's call fails (transient API error/timeout), the existing
    page's field is left untouched rather than overwritten with an empty
    string — otherwise a transient failure on a later re-upload would
    silently blank an already-public summary/flag with no record anything
    changed (found by code-review-tc, when this was still a review-gated
    draft — the same protection matters even more now that these values
    reach the public page directly). A brand new page has nothing to
    preserve, so it falls back to ``""`` as before. Plan 14 applies this
    same preserve-on-falsy rule *per category* — a category with zero
    matching visits today (so nothing for the model to summarise, or a
    genuinely failed/malformed response for that key alone) leaves that
    one field untouched rather than blanking it, independently of whether
    the other two categories got a fresh value this round.

    The three drafting calls are independent of each other and run
    concurrently (found by code-review-tc: they used to run sequentially,
    tripling this function's worst-case latency inside the synchronous
    upload request that calls it).
    """
    aggregate = DailyAggregate.objects.get(clinic_date=clinic_date)

    visits = list(DeidentifiedVisit.objects.filter(visit_date=clinic_date))
    freetext_groups = freetext.collect_freetext_entries_by_group(visits)
    # Plan 15 Track C3: a demographic group with fewer than
    # ``MIN_GROUP_VISITS_TO_SUMMARISE`` visits that day is below the
    # k-anonymity small-cell floor — never summarise it. Enforced in Python,
    # not left to the prompt: a sub-floor group is dropped from the payload
    # entirely (``payload_groups`` below substitutes an empty shape for it, so
    # its free text is never even sent to the model) and its summary field is
    # blanked deterministically further down.
    group_visit_counts = freetext.count_visits_by_group(visits)
    payload_groups = {
        group: (
            entries
            if group_visit_counts[group] >= freetext.MIN_GROUP_VISITS_TO_SUMMARISE
            else freetext.empty_group_entries()
        )
        for group, entries in freetext_groups.items()
    }
    # Deliberately a second pass over `visits` (not
    # `freetext.empty_columns_from_entries` over `freetext_groups`), even
    # though the two used to share one pass before Plan 14 (see
    # `empty_columns_from_entries`'s own docstring on why that sharing
    # mattered). B9's "was this column empty today" must stay true across
    # *every* visit, but `freetext_groups` only covers the three in-scope
    # demographic buckets — an unknown-age-band visit or an unknown-sex
    # adult's entries are deliberately excluded from every group (Plan 14
    # grounding note), so building B9's input from `freetext_groups` would
    # silently narrow "empty" to "empty across the categorised visits",
    # wrongly flagging a column as empty when its only content came from an
    # excluded visit.
    empty_columns = freetext.compute_empty_columns(visits)

    with ThreadPoolExecutor(max_workers=3) as executor:
        summary_future = executor.submit(
            ai.draft_daily_summary_sentence, aggregate, client
        )
        freetext_future = executor.submit(
            ai.draft_freetext_summary, clinic_date, payload_groups, client
        )
        empty_future = executor.submit(
            ai.draft_empty_columns_flag, clinic_date, empty_columns, client
        )
        summary_sentence = summary_future.result() or ""
        new_freetext_summary_by_group = freetext.parse_freetext_summary_by_group(
            freetext_future.result() or ""
        )
        new_empty_columns_flag = empty_future.result()

    def resolve(group: str) -> str | None:
        return _resolve_group_summary(
            group,
            freetext_groups=freetext_groups,
            group_visit_counts=group_visit_counts,
            new_by_group=new_freetext_summary_by_group,
        )

    index = _get_or_create_report_index()
    page = DailyReportPage.objects.filter(report_date=clinic_date).first()
    if page is None:
        page = DailyReportPage(
            title=clinic_date.isoformat(),
            slug=clinic_date.isoformat(),
            report_date=clinic_date,
            aggregate=aggregate,
            summary_sentence=summary_sentence,
            empty_columns_flag=new_empty_columns_flag or "",
            live=False,
            # A brand-new page has nothing to preserve, so a "preserve"
            # (``None``) resolution and a deterministic blank both mean "".
            **{
                field_name: resolve(group) or ""
                for group, field_name in _FREETEXT_SUMMARY_GROUP_FIELDS.items()
            },
        )
        index.add_child(instance=page)
    else:
        page.aggregate = aggregate
        # Plan 15 Track B1: only overwrite an already-public sentence when the
        # fresh call produced one — a transient Haiku failure on a corrective
        # re-upload must not silently blank it (same preserve-on-falsy rule
        # the free-text/empty-columns fields already had).
        if summary_sentence:
            page.summary_sentence = summary_sentence
        for group, field_name in _FREETEXT_SUMMARY_GROUP_FIELDS.items():
            resolved = resolve(group)
            # ``None`` means "preserve the existing field" (a genuine
            # per-group call failure); a string — including "" — is a
            # deterministic decision to overwrite (Track B2/C3).
            if resolved is not None:
                setattr(page, field_name, resolved)
        if new_empty_columns_flag:
            page.empty_columns_flag = new_empty_columns_flag

    revision = page.save_revision()
    revision.publish()
    return page
