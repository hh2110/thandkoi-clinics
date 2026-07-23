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

This module holds the shared column list plus two pure functions used by
``apps.pipeline.report_publishing`` to build the deterministic inputs for
B8's summary call and B9's empty-column flag call (``apps.pipeline.ai``) —
both then hold a fixed prompt over a value this module already computed in
Python, mirroring invariant #3's "numbers computed in Python, AI writes prose
only" for the daily-summary-sentence call.
"""

from __future__ import annotations

from collections.abc import Iterable

from apps.pipeline.models import DeidentifiedVisit

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
