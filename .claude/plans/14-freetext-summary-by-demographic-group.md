# Plan 14 — Freetext summary split by demographic group

**One-line:** replace the daily report's single ~50-word free-text summary
with three shorter summaries — male adults, female adults, children — each
capped at 30 words, so a reader can see themes per patient category instead
of one blended paragraph.

## Background — why now

Maintainer ask, 2026-07-24: doctor's notes should be summarised separately
for male adults, female adults, and children, 20 words each (revised same
day to 30 words each, before implementation), with "child" defined as
under 14.

## Decisions (maintainer, 2026-07-24)

1. **Age cutoff.** `DeidentifiedVisit.age_band` only ever stores one of four
   fixed bands (`0-5`, `6-18`, `19-55`, `56+`, `unknown`) — exact age is
   never persisted (Plan 11 Track B12, deliberate). A precise "under 14"
   cutoff would require re-banding (its own scoped migration, deferred).
   **Decision: approximate** — bands `0-5` + `6-18` together are "children"
   for this feature, `19-55` + `56+` are "adults". The child bucket
   therefore runs to 18, not 13.
2. **Storage.** Three separate `DailyReportPage` fields
   (`freetext_summary_male_adults` / `_female_adults` / `_children`) rather
   than one field holding structured/delimited text — each stays
   independently Wagtail-editable and independently testable, matching how
   `summary_sentence`/`empty_columns_flag` are already separate fields.
3. **Layout.** A three-column grid (`.dr__notes-grid`) on desktop,
   collapsing to a single column under the page's existing 40rem
   breakpoint, reusing the `.dr__card`/`.dr__card-title` tokens already used
   by the Breakdown section.
4. **Adults with unknown/other sex.** Not folded into either male or female
   bucket (would misrepresent them) and not given a fourth bucket (out of
   scope of the ask). Their free-text entries are simply not summarised by
   this feature — documented in `apps.pipeline.freetext._group_for_visit`,
   not silently dropped.

## Privacy-invariant note (CLAUDE.md invariant #2)

The existing B8 free-text-summary call's payload docstring stated "no age
band, sex, location, or any identifying field" ever crosses into the model
call. This plan **deliberately widens that** — `age_band`/`sex` are now used
to bucket entries into three groups before the payload is built, and the
bucket the entries came from is now visible to the model (as which JSON key
they're under). This is a category label, not new PHI: `age_band`/`sex` are
already de-identified fields used elsewhere (aggregates, this same page's
"Breakdown" section); no exact age, name, or other identifier is added.
CLAUDE.md invariant #2 is updated with a dated note recording this widening
per its own instruction ("widening this exception further is a decision to
make deliberately again").

## Precedent map

- **Grouped JSON response, defensive parsing on the way in:**
  `_EMPTY_COLUMNS_FLAG_SYSTEM_PROMPT` / `draft_empty_columns_flag` (B9)
  already ask the model for structured JSON instead of prose, and
  `apps.pipeline.models._parse_empty_columns_flag` already shows the
  "falls back to empty on anything not a clean JSON shape" pattern this
  plan's `freetext.parse_freetext_summary_by_group` mirrors.
- **Per-visit demographic fields already read elsewhere:**
  `DailyReportPage.get_context`'s `gender_rows`/`age_bands` (models.py:647-682)
  is the existing precedent for reading `age_band`/`sex` off aggregated
  data for this same page — this plan is the first time those fields reach
  an AI payload, not the first time they're read at all.
- **Preserve-prior-value-on-falsy-result:** `publish_daily_report`'s existing
  `if new_freetext_summary: page.freetext_summary = new_freetext_summary`
  guard is applied per-field, independently, to each of the three new
  fields (a category with zero visits that day should not blank out
  whatever the field held from the last day it did have entries — matching
  the existing single-field behaviour exactly, just three times over).

## Feature flag

None — same reasoning as every other Plan-11-era daily-report change: this
call already auto-publishes with no review step (CLAUDE.md invariant #4's
narrow exception), and there is no partial-slice-reaching-users risk since
it's a same-page redesign of an existing auto-generated field, not new
user-facing surface area.

## Release plan

Ships the same way every daily-report AI-drafted field already ships: no
separate rollout — the next `publish_daily_report` call (real ingest or
republish) populates the three new fields; a failed/empty AI call leaves
the section blank (template wraps each card in its own `{% if %}`), same
auto-publish-numbers-regardless contract as before. No new access/audience —
same public daily report page. Historical pages keep no free-text summary
under the old single field (removed, not migrated forward) until
re-ingested; this is a cosmetic-only loss (the underlying source data is
untouched) considered acceptable for a pre-existing AI paraphrase field.
