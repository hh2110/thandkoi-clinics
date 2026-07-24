"""Plan 11 Track B8/B9 — free-text column definitions and per-date collation.

**Grounding note (maintainer decision, 2026-07-23 — see
``.claude/plans/11-stakeholder-feedback-2026-07.md``, Track B).** Plan 08's
original de-identification scope covered only *diagnosis*, mapped to a fixed
category, raw text never persisted (``DeidentifiedVisit.diagnosis_category``).
The seven columns below looked like a CLAUDE.md invariant #2 conflict (never
send patient data to a model) for the same reason. The maintainer confirmed
the clinic software's data-entry UI does not allow a patient identifier to be
entered into these fields in the first place — they are structurally free of
identifiers by construction, not by a scrub step this codebase builds. That
resolution is scoped to *these seven columns only*; a new free-text column
added later needs the same question asked explicitly, not assumed by analogy.

This module holds the shared column list plus the pure functions used by
``apps.pipeline.report_publishing`` to build the deterministic inputs for
B8's summary call and B9's empty-column flag call (``apps.pipeline.ai``) —
both then hold a fixed prompt over a value this module already computed in
Python, mirroring invariant #3's "numbers computed in Python, AI writes prose
only" for the daily-summary-sentence call.

**Grounding note (maintainer decision, 2026-07-24 — Plan 14, see
``.claude/plans/14-freetext-summary-by-demographic-group.md``).** B8's
summary is now split into three per-category summaries (male adults, female
adults, children) instead of one blended paragraph — see
:func:`collect_freetext_entries_by_group` and :func:`_group_for_visit`. The
child/adult cutoff the maintainer asked for is "under 14", but
``DeidentifiedVisit.age_band`` only ever stores one of four fixed bands
(never an exact age — see that field's own 2026-07-23 rebanding decision
comment), and ``6-18`` straddles the 14-year line. Maintainer decision:
approximate — bands ``0-5``/``6-18`` together are "children", ``19-55``/
``56+`` are "adults" (the child bucket therefore runs to 18, not 13). A
precise 14-year cutoff would need its own re-banding migration, deferred.
Adults whose ``sex`` is ``SEX_OTHER_UNKNOWN`` are not folded into either
adult bucket (would misrepresent them) and are not given a fourth bucket
(out of scope of the ask) — their free-text entries are simply not
summarised by this feature, same treatment as an ``AGE_BAND_UNKNOWN`` visit.
This is CLAUDE.md invariant #2's exception widened again (2026-07-24): the
payload now also carries which of these three categories each entry came
from, derived from ``age_band``/``sex`` — see CLAUDE.md's invariant #2 for
why that's still within bounds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from apps.pipeline.models import DeidentifiedVisit

#: The three demographic buckets B8 now summarises separately (Plan 14).
#: Order matches how they should read in the prompt/response and the
#: template — adults first (grouped by sex), then children.
GROUP_MALE_ADULTS = "male_adults"
GROUP_FEMALE_ADULTS = "female_adults"
GROUP_CHILDREN = "children"

FREETEXT_SUMMARY_GROUPS: tuple[str, ...] = (
    GROUP_MALE_ADULTS,
    GROUP_FEMALE_ADULTS,
    GROUP_CHILDREN,
)

#: See this module's Plan 14 grounding note above for why these two bands
#: are treated as "children" (an approximation of "under 14").
_CHILD_AGE_BANDS = frozenset(
    {DeidentifiedVisit.AGE_BAND_0_5, DeidentifiedVisit.AGE_BAND_6_18}
)
_ADULT_AGE_BANDS = frozenset(
    {DeidentifiedVisit.AGE_BAND_19_55, DeidentifiedVisit.AGE_BAND_56_PLUS}
)

#: ``(field_name, human_label)`` — the seven free-text columns named in Plan
#: 11 Track B8 ("Presenting Complaints, Investigation, Provisional
#: Diagnosis, Prescribed Medicine, Doctor's/Nurse's/Dietitian's Notes, Diet &
#: Drug Compliance, Plan"). ``clinical_notes`` covers the "Doctor's/Nurse's/
#: Dietitian's Notes" item as one combined field — see
#: ``apps.pipeline.parser_tkc_daily_v1`` for how per-role notes are combined
#: into it.
FREETEXT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("presenting_complaints", "Presenting Complaints"),
    ("investigation", "Investigation"),
    ("provisional_diagnosis_text", "Provisional Diagnosis"),
    ("prescribed_medicine", "Prescribed Medicine"),
    ("clinical_notes", "Doctor's / Nurse's / Dietitian's Notes"),
    ("diet_and_drug_compliance", "Diet & Drug Compliance"),
    ("plan_notes", "Plan"),
)

FREETEXT_COLUMN_LABELS: dict[str, str] = dict(FREETEXT_COLUMNS)


def collect_freetext_entries(
    visits: Iterable[DeidentifiedVisit],
) -> dict[str, list[str]]:
    """Non-blank values per free-text column, across ``visits``.

    Sorted (not insertion order) so the result — and everything built from it,
    including the B8 AI payload — is deterministic regardless of the order
    ``visits`` was queried in, mirroring ``apps.pipeline.ingest._counter``'s
    same reasoning for category counts.
    """
    visits = list(visits)
    collected: dict[str, list[str]] = {}
    for field_name, _label in FREETEXT_COLUMNS:
        values = sorted(
            value.strip()
            for visit in visits
            if (value := getattr(visit, field_name)) and value.strip()
        )
        collected[field_name] = values
    return collected


def _group_for_visit(visit: DeidentifiedVisit) -> str | None:
    """Which of :data:`FREETEXT_SUMMARY_GROUPS` ``visit`` belongs to, if any.

    ``None`` for an ``AGE_BAND_UNKNOWN`` visit, or an adult visit whose
    ``sex`` is ``SEX_OTHER_UNKNOWN`` — see this module's Plan 14 grounding
    note above for why those are excluded rather than guessed at or given a
    fourth bucket. A caller collecting entries "by group" simply never sees
    these visits' free text in any bucket.
    """
    if visit.age_band in _CHILD_AGE_BANDS:
        return GROUP_CHILDREN
    if visit.age_band in _ADULT_AGE_BANDS:
        if visit.sex == DeidentifiedVisit.SEX_MALE:
            return GROUP_MALE_ADULTS
        if visit.sex == DeidentifiedVisit.SEX_FEMALE:
            return GROUP_FEMALE_ADULTS
    return None


def collect_freetext_entries_by_group(
    visits: Iterable[DeidentifiedVisit],
) -> dict[str, dict[str, list[str]]]:
    """:func:`collect_freetext_entries`, bucketed into the three B8 groups.

    Each group's entries are collected independently via
    :func:`collect_freetext_entries`, so they keep the same sorted,
    deterministic shape. A group with no matching visits that day gets the
    same all-empty-lists shape :func:`collect_freetext_entries` returns for
    an empty ``visits`` — there is nothing to summarise, not an error.
    """
    visits = list(visits)
    return {
        group: collect_freetext_entries(
            visit for visit in visits if _group_for_visit(visit) == group
        )
        for group in FREETEXT_SUMMARY_GROUPS
    }


def parse_freetext_summary_by_group(raw: str) -> dict[str, str]:
    """Parse the B8 group-summary AI response into ``{group: text}``.

    ``raw`` is expected to be the JSON object
    ``_FREETEXT_SUMMARY_SYSTEM_PROMPT`` asks for (see ``apps.pipeline.ai``) —
    one key per :data:`FREETEXT_SUMMARY_GROUPS`, each a short string. Mirrors
    ``apps.pipeline.models._parse_empty_columns_flag``'s defensive shape:
    anything that isn't a clean match (blank, not JSON, not an object, an
    unexpected key, a non-string value) is dropped rather than raised —
    ``apps.pipeline.report_publishing.publish_daily_report`` treats a
    missing/blank group exactly like a failed call for that group alone
    (leaves the corresponding field untouched on a re-ingest, blank on a new
    page), never as a reason to reject the whole response.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        group: value.strip()
        for group, value in parsed.items()
        if group in FREETEXT_SUMMARY_GROUPS and isinstance(value, str) and value.strip()
    }


def empty_columns_from_entries(entries: dict[str, list[str]]) -> dict[str, bool]:
    """``True`` for a column with zero non-blank entries in ``entries``.

    ``entries`` is the dict :func:`collect_freetext_entries` already built —
    callers that need both B8's entries and B9's empty-flags (e.g.
    ``apps.pipeline.report_publishing.publish_daily_report``) should call
    that once and pass its result here, rather than re-collecting from
    ``visits`` a second time (found by code-review-tc: the two used to run
    the same per-visit strip/filter/sort pass twice over).
    """
    return {name: len(values) == 0 for name, values in entries.items()}


def compute_empty_columns(visits: Iterable[DeidentifiedVisit]) -> dict[str, bool]:
    """``True`` for a column with zero non-blank entries across ``visits``.

    This is the deterministic "number" behind B9 (CLAUDE.md invariant #3):
    the boolean fact is computed here, in Python, from already-de-identified
    rows; the AI call in ``apps.pipeline.ai`` is only ever handed this dict
    and asked to phrase it, never to decide it. A date with no visits at all
    counts every column as empty — there is nothing to have filled in.

    Convenience wrapper over :func:`empty_columns_from_entries` for callers
    that only need the flags, not the entries themselves (e.g. tests).
    """
    return empty_columns_from_entries(collect_freetext_entries(visits))
