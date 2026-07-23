# Plan 12 — Generic report stats & flexible key figures

_Status: Drafted · Depends on: 06 Newsletters, Camp Reports & Gallery · Triggered by: attempting to publish a one-off "Inauguration Report" and finding the current model can't represent it (2026-07-23)_

## Goal

Generalize the Camp Reports archive from "medical camp reports with a fixed
Paediatrics/General/Welfare patient split" into a genuinely generic report
type: any one-off event (a medical camp, an inauguration, an anniversary) can
publish its own arbitrary set of headline numbers, plus optionally attach a
source document (a PDF report) as a first-class download — not just a link
buried in prose.

## Background — why now

Trying to publish a real "Inauguration Report" PDF surfaced three compounding
problems in `CampReportPage` (`apps/core/models.py:697`):

1. **The patient split is hardcoded and camp-specific.** `patients_children`
   / `patients_general` / `patients_welfare` model a clinical-department
   breakdown (Paediatrics vs. General Medicine vs. Welfare/free-of-cost),
   assumed mutually exclusive so their sum is the derived total
   (`total_patients_served`, `:759-761`). The maintainer's real numbers for
   both the camp *and* the inauguration event answer different questions —
   sex (female/male), age band, Zakat-beneficiary status — which overlap
   (a child can also be a Zakat beneficiary), so they don't partition into
   three exclusive buckets. The maintainer confirmed camps only actually
   need **female/male** counts going forward, not the department split.
2. **The stat band always renders.** `camp_report_page.html:22` includes
   `stat_band.html` unconditionally — unlike every other section on the page
   (services/narrative/credits/photos all check for content first). Leaving
   the three fields at their `default=0` doesn't omit the section, it
   actively displays "0 Children / 0 General / 0 Welfare" next to prose
   describing real numbers.
3. **No document-attachment field exists.** A report PDF can only be linked
   inline inside the rich-text `narrative` field (via the editor's Document
   link tool) — there's no dedicated chooser/field, so it can never be a
   first-class "Download the full report (PDF)" button.

Underneath all three: an inauguration is not a medical camp. Forcing it
through `CampReportPage` is *why* every field fights back. The maintainer's
explicit ask (2026-07-23): make the report functionality "as generic as
possible... not just camps."

## Scope

**In scope**
- A reusable flexible key-figure block (label + value pairs, patterned after
  the existing `ImpactStatBlock`, `apps/core/blocks.py:19-35`) that any
  report can populate with whatever numbers actually apply to it.
- Generalizing `CampReportPage` to use that block for its headline stats,
  replacing the fixed `patients_children`/`patients_general`/`patients_welfare`
  fields (no live data exists yet for any published camp report — this is a
  clean field swap, not a migration-with-backfill problem).
- A document chooser field so a report can attach a source PDF as a
  first-class download, rendered as a clearly-labelled link/button — not
  just reachable via a manually inserted rich-text link.
- Fixing the template bug: guard the stat band (and the new document link)
  behind `{% if %}`, matching every other section's convention.
- Confirming/updating [docs/content-operations.md](../../docs/content-operations.md)'s
  worked example once the model shape changes.

**Out of scope**
- `pipeline.CampUploadReportPage` (`apps/pipeline/models.py:571`) — the
  auto-published counterpart fed from a parsed `.xls` export's
  `DailyAggregate`. Its numbers are pipeline-computed and must stay
  deterministic per CLAUDE.md invariant #3 ("numbers are deterministic... the
  AI writes prose only"); a human-editable flexible key-figure block is the
  wrong shape for a value that's supposed to come only from parsed data.
  Untouched by this plan.
- Renaming/restructuring the page tree beyond field-level changes (see open
  question D2 below) — if the maintainer wants the archive itself renamed off
  "Camp Reports," that's a separate, larger content-migration + URL-redirect
  concern, not bundled into this plan by default.
- Bilingual (Urdu) key-figure labels — same blanket exclusion as every other
  content plan (see [plans README](README.md#out-of-scope-for-now)).

## Proposed decisions (confirm before building)

- **D1. One unified type, not a new "event report" type.** Generalize
  `CampReportPage` in place rather than adding a second, parallel
  "InstitutionalReportPage." Grounds directly in the maintainer's "as generic
  as possible" instruction — one flexible model beats two rigid ones.
  *Recommend: confirm.*
- **D2. Archive naming stays as-is for this plan.** `CampReportIndexPage`
  keeps its current `verbose_name`, seeded title "Camp Reports," and slug
  `camp-reports` (`apps/core/management/commands/seed_initial_content.py:57`)
  for now, even though it will house non-camp reports too. Reason: the site
  already has a distinct, separately-named `pipeline.ReportIndexPage`
  (`apps/pipeline/models.py:364`) as the nav's "Reports" hub, which teases
  both "Daily reports" and "Camp reports" as its two sections
  (`pipeline/templates/pipeline/report_index_page.html:21,43`). Renaming
  `CampReportIndexPage` to something generic risks colliding with or
  confusing that existing "Reports" name. *This is a real open question, not
  a settled decision — flag if you'd rather rename now (e.g. to "Community
  Reports") and take on the nav-copy + URL-redirect work as part of this
  plan instead of deferring it.*
- **D3. Key-figure values are free text, not strictly numeric** — matching
  `ImpactStatBlock`'s existing convention (`value = blocks.CharBlock`), so a
  figure like "245 (64%)" can be entered as-is without the model forcing a
  bare integer. Trade-off: no cross-report aggregation of these values is
  possible later without re-parsing free text — acceptable since these are
  authored per-report narrative figures, not aggregate-pipeline numbers
  (that's what `DailyAggregate`/Plan 08 is for). *Recommend: confirm.*
- **D4. Existing empty archive means no backfill/migration-data concern** —
  confirmed via production query this session: zero `CampReportPage`
  instances exist yet (`CampReportPage.objects.count() == 0` under the
  "Camp Reports" index). The field swap is a straight schema migration, no
  data-loss risk to reason about.

## Proposed model changes

- New `apps/core/blocks.py` block, e.g. `KeyFigureBlock(blocks.StructBlock)`
  — `label` (`CharBlock`), `value` (`CharBlock`), mirroring `ImpactStatBlock`
  exactly (same field shapes, different name/context so `ImpactStatsBlock`'s
  home-page usage is untouched).
- `CampReportPage.key_figures = StreamField([("figure", KeyFigureBlock())], blank=True)`
  replacing `patients_children`/`patients_general`/`patients_welfare`
  (and removing the now-meaningless `total_patients_served` property, or
  redefining it as N/A — see task file once this plan is sliced).
- `CampReportPage.report_document = models.ForeignKey("wagtaildocs.Document", ...)`
  (nullable, `on_delete=models.SET_NULL`) with a `FieldPanel` using Wagtail's
  document chooser — mirroring the standard Wagtail docs-chooser precedent
  (no in-repo precedent exists yet for a document FK on a page; this is the
  first, grounded directly against Wagtail's own documented
  `DocumentChooserPanel`/`FieldPanel` idiom rather than invented).
- Template changes: `camp_report_page.html` gets the key-figures section and
  a document-download link, both `{% if %}`-guarded like every other section.

## Precedent map

| Element | Mirrors |
|---|---|
| `KeyFigureBlock` | `ImpactStatBlock` (`apps/core/blocks.py:19-35`) — same label/value StructBlock shape |
| Document chooser field | Wagtail's own `FieldPanel` + document-chooser widget idiom (no existing in-repo precedent — first use) |
| `{% if %}`-guarded template sections | Every other `camp_report_page.html` section (services/narrative/credits/photos) already does this; the stat band was the one outlier being fixed |
| Plan structure/sections | Plan 06 (`06-newsletters-camps-gallery.md`) — same content-type plan shape |

## Feature flag

No flag — same rationale as every plan in this repo (pre-launch site, no
existing users a partial slice could reach; Wagtail's own draft/publish gate
does the real work). `CampReportPage` has zero live instances today, so there
is no in-flight content to disrupt either.

## Task checklist (code — this plan's PR)

- [ ] `KeyFigureBlock` in `apps/core/blocks.py`.
- [ ] Migration: drop `patients_children`/`patients_general`/`patients_welfare`,
      add `key_figures` StreamField + `report_document` FK on `CampReportPage`.
- [ ] Update `content_panels` (remove the `MultiFieldPanel` patient-count
      group, add `FieldPanel("key_figures")` and the document chooser panel).
- [ ] Update `get_context`/`total_patients_served` usage — decide whether to
      drop the derived-total property entirely or repurpose it (task-file
      decision, not pre-decided here).
- [ ] Update `camp_report_page.html`: render `key_figures` via (a new or
      adapted) stat-band partial, `{% if %}`-guarded; add a guarded
      "Download the full report" link when `report_document` is set.
- [ ] Update [docs/content-operations.md](../../docs/content-operations.md)'s
      worked example to the new field shape.
- [ ] Tests: model field presence, template renders nothing when
      `key_figures`/`report_document` are empty, renders correctly when set.

## Acceptance criteria

- A `CampReportPage` with only `key_figures` set (e.g. "Total patients: 384",
  "Female patients: 260", "Children 0–17: 174", "Zakat beneficiaries: 245")
  and a `report_document` attached renders: the figures as a stat band, a
  clear download link to the PDF, and **no** leftover Paediatrics/General/
  Welfare fields anywhere in admin or template.
- A `CampReportPage` with no figures set at all renders no empty/zeroed stat
  band — matching every other optional section's behaviour.
- `pipeline.CampUploadReportPage` is completely unaffected — its fields,
  template, and tests are untouched by this plan.

## Parked, deliberately

- **Renaming the Camp Reports archive to a fully generic name** (D2) —
  parked pending the maintainer's call on whether the naming collision risk
  with `pipeline.ReportIndexPage` is worth resolving now vs. later.
- **Cross-report aggregation of key figures** — e.g. summing "female
  patients" across all camp reports for a home-page stat — out of scope
  here; revisit only if a future plan (à la Track F's live "impact so far"
  aggregation, Plan 11) needs it, and only for the pipeline-driven
  `DailyAggregate` numbers, not this free-text block.

## Release plan

- **How it ships:** normal PR flow (branch → code-review-tc → draft PR →
  maintainer merges), no flag, no phased rollout — schema change with zero
  live data to migrate.
- **Who gets access:** the maintainer only; no other users of this content
  type yet.
- **Who is informed:** N/A — solo project, no downstream stakeholders for a
  schema change with no live content affected.
- **Gating check:** migration applies cleanly against the current production
  schema (zero `CampReportPage` rows, confirmed above) and the acceptance
  criteria above pass.
- **Rollback trigger:** if the migration or template change breaks the
  (currently empty) Camp Reports archive page in production, roll back via
  `scripts/release.sh --ref <previous-tag>` per [docs/deploying.md](../../docs/deploying.md).

## Next step after this plan lands

Once merged, actually publish the Inauguration Report (the task that
triggered this plan) via the agent-driven SSH path documented in
[docs/content-operations.md](../../docs/content-operations.md), using the
new `key_figures` block for the real numbers already gathered (384 total,
260 female, 174 children 0–17, 245 Zakat beneficiaries) and `report_document`
pointing at the already-uploaded `Inauguration report` document (id `1`).
