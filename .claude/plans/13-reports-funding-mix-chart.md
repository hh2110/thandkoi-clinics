# Plan 13 — Reports index: funding-mix trend chart

**One-line:** show a rolling 30-day Zakat-vs-Regular funding-mix chart on the
`/reports/` archive index page, so a visitor can see the clinic's funding
story at a glance instead of only a paginated list of individual days.

## Background — why now

The maintainer asked for "some aggregating graphs" of the daily clinic data
on the report pages. Explored live during a design pass (2026-07-24):
`DailyAggregate` already stores one row per `clinic_date` with a unique
constraint (`apps/pipeline/models.py:298-304`), so day-over-day history is
directly queryable with no schema change. Design iterated through several
rounds before landing here — chart placement moved from the individual
`DailyReportPage` to the `ReportIndexPage` archive (a single day's page has
no use for a multi-day trend); the window narrowed from "full archive" to a
rolling 30 days; the palette went through three revisions (a chart-tuned
teal/coral pair → an invented yellow/blue pair, rejected as off-brand → the
final Teal + Ink Faint pairing, which turned out to already be the
guideline's own prescribed answer). Department/diagnosis-category
breakdowns (already computed in `category_counts` but never rendered) were
explicitly ruled out of scope for this pass.

Three published Artifact mockups carry the full design trail and were
checked against the live production page and real Neon data before this
plan was written:
- Reports-index placement + palette: https://claude.ai/code/artifact/77f01566-3c9a-42e7-8bab-fe2857e73e39
- Confirms no chart on the daily report page: https://claude.ai/code/artifact/52b4e4db-6aff-4097-90dd-702f75c853d6
- Brand-compliant color options comparison: https://claude.ai/code/artifact/9be74440-df74-4677-90d6-841464dec462

## Goal & scope

**Goal:** one new section on `/reports/`, above the existing "Daily reports"
card grid, showing a stacked bar chart of Zakat vs. Regular visits per day
over the last 30 days.

**In scope**
- `ReportIndexPage.get_context` gains a `funding_mix` context value: the
  `DailyAggregate` rows with `clinic_date` in the last 30 days, ascending,
  with per-bar geometry precomputed in Python (not in the template or in
  client JS).
- A new template partial in `report_index_page.html`, above the existing
  "Daily reports" section, rendering the chart as **server-rendered inline
  SVG** — bars, gridlines, axis labels, and a `<details>` "view as table"
  fallback all render fully without JavaScript.
- A new `static/js/funding-mix-chart.js`: pure progressive enhancement,
  adds the hover tooltip only (mirrors `circle-of-care.js`'s pattern
  exactly — the chart must be fully legible with this script disabled).
- A new `static/css/report-index.css`, scoped to a single wrapper class
  (mirrors `daily-report.css`'s `.dr` scoping), linked directly in
  `templates/base.html` alongside the other page-scoped stylesheets.
- i18n: all new copy (`Funding mix`, `Zakat`, `Regular`, `View as table`)
  wrapped in `{% translate %}`, matching `report_index_page.html`'s existing
  pattern.
- Tests: the 30-day filter query, and a template-render smoke test
  confirming the new section appears with correct figures for a small
  fixture set of `DailyAggregate` rows.

**Out of scope (parked, deliberately)**
- **Any chart on the individual `DailyReportPage`.** Explicitly ruled out
  by the maintainer after an earlier iteration added a volume-trend chart
  there — the daily report page stays exactly as it is in production today.
- **Department/diagnosis-category breakdowns as charts.** Maintainer:
  "no need to think about department and diagnosis for now." The data is
  already computed (`DailyAggregate.category_counts`) and can be revisited
  later without any pipeline change.
- **A configurable or user-adjustable window.** Fixed at 30 days server-side;
  no UI control to change it.
- **Any new JS charting library.** Hand-written SVG only, per the "one
  Python codebase, minimal JS" stack constraint (`CLAUDE.md`) — there is
  zero charting library anywhere in this repo today and this plan doesn't
  introduce one.

## Decisions

- **Rolling 30-day window, not the full archive.** `DailyAggregate.objects
  .filter(clinic_date__gte=today - timedelta(days=30))` — a fixed-size query
  regardless of how large the archive grows, rather than an ever-growing
  "all reports to date" chart. Of the 38 total reports as of 2026-07-24, 14
  fall in the current window.
- **Palette: `--color-teal-brand` for Zakat, `--color-ink-faint` for
  Regular** — both existing tokens, zero new hex added. This is the
  "emphasis" chart form (one hue + a de-emphasis gray), not a two-hue
  categorical pairing. It directly follows an existing rule already in
  `docs/brand-guidelines.md` §2 (accessibility section): *"'Free / Zakat
  beneficiary' badges use Teal, not a new colour."* Two other options (a
  two-shade teal ramp; Teal + Coral Deep) were validated and rejected — see
  the color-options mockup linked above for the comparison and the
  colorblind-safety validator output behind each.
- **Server-rendered SVG, not client-built.** Bar coordinates/paths are
  computed in `get_context` and passed to the template as plain data;
  `funding-mix-chart.js` only wires up hover — this mirrors
  `circle-of-care.js`'s documented pattern ("the section renders fully
  without this script... this only adds the reveal") rather than the
  client-side-JS-builds-the-SVG approach used in the throwaway mockups.
- **New dedicated `report-index.css` and `funding-mix-chart.js` files,
  linked directly in `base.html`.** `{% block extra_css %}` / `{% block
  extra_js %}` exist in `base.html` but are unused by every other page in
  the codebase — every page-scoped asset so far is its own file linked
  sitewide in document order (`daily-report.css`, `circle-of-care.js`).
  Matching that instead of being the first page to use the unused block
  hooks.

## Precedent map (Stage 7)

- **Query + context shape** — mirrors `ReportIndexPage.get_reports()`
  (`apps/pipeline/models.py:370-376`) and its use in `get_context`
  (`:378-389`): a plain queryset method, called from `get_context`, assigned
  to a context key.
- **Field names** — confirmed directly in code, not assumed: `zakat
  _beneficiary_patients` → "Zakat" and `paying_patients` → "Regular" in
  `DailyReportPage.headline_stats` (`apps/pipeline/models.py:481-488`) — the
  exact same fields and labels this chart reuses.
- **CSS file-per-page-type + `<link>` in `base.html`** — mirrors the
  `daily-report.css` precedent comment at `templates/base.html:86-90` almost
  verbatim (scoped class, `tokens.css`-only, sitewide link since no
  page-scoped CSS block exists in this base).
- **JS progressive-enhancement pattern** — mirrors `static/js/circle-of-
  care.js:1-78` structure exactly: IIFE, idempotent init guarded by a
  `dataset` flag, `data-*` attribute wiring, init on `DOMContentLoaded` (or
  immediately if already parsed), re-init on `htmx:afterSwap`.
- **i18n** — mirrors `report_index_page.html`'s existing `{% translate
  "Daily reports" %}` and `{% blocktranslate count %}` usage (confirmed at
  the top of that template, which already `{% load i18n %}`).
- **Chart marks/spacing** — no in-repo precedent for a bar/SVG chart
  specifically (greenfield); grounded against the `dataviz` skill's mark
  spec (≤24px bar thickness, 4px rounded top / square baseline, 2px surface
  gap between stacked segments, hairline recessive gridlines) rather than a
  guess, and against the colorblind-safety validator script for the
  palette (see Decisions).

## Feature flag (Stage 6)

No runtime flag. This is a purely additive, read-only display change on a
public archive page with no partial-rollout risk — every visitor sees the
same chart the moment it deploys, same as every other page addition in this
pre-launch site's history (matches Plan 12's same call for its two tracks).

## Release plan (Stage 10)

- **How it ships:** one branch, one PR, normal flow — `code-review-tc` clean,
  draft PR, maintainer takes it out of draft.
- **Gating check:** load the live `/reports/` page after deploy, confirm the
  chart renders with real figures matching the admin/database, in both light
  and dark mode, with and without JS (disable JS in devtools and confirm the
  chart and table fallback still render — the point of the progressive-
  enhancement approach).
- **Rollback:** additive-only, no schema or data change — redeploying the
  previous release tag removes the section cleanly.
- **Who's informed:** maintainer only (solo project, no other stakeholders
  for a display-only change).

## Tasks

- [ ] Add a `get_funding_mix(self)` method (or equivalent) to
      `ReportIndexPage`, querying `DailyAggregate` for the last 30 days,
      ascending by `clinic_date`, returning precomputed per-bar geometry
      (position, stacked-segment heights, rounded/square path data) plus the
      raw figures for the table fallback and tooltip text.
- [ ] Wire it into `get_context`, add to the template above the "Daily
      reports" section.
- [ ] `report_index_page.html`: new section — chart title, caption, legend
      (Zakat / Regular, using the final palette), inline SVG, `<details>`
      table-view fallback. All `{% translate %}`-wrapped.
- [ ] `static/css/report-index.css`: scoped styles for the new section,
      reading only `tokens.css` custom properties (no new hex). Link it in
      `templates/base.html` next to `daily-report.css`.
- [ ] `static/js/funding-mix-chart.js`: hover tooltip only, following
      `circle-of-care.js`'s exact structural pattern. Link it in
      `templates/base.html` next to `circle-of-care.js`, `defer`.
- [ ] Tests: 30-day filter boundary (a row exactly 30 days old is included;
      31 days old is excluded), and a render smoke test for the new section
      with a small fixture set.
- [ ] Run `code-review-tc`; fix or answer findings.
- [ ] Verify against the real app: run the dev server, load `/reports/` in
      a real browser, light + dark screenshots, confirm figures match the
      database directly (not hand-computed "expected" values).
- [ ] Draft PR, label `enhancement`.
- [ ] Flip this plan's roadmap row to ✅ Done.

## Acceptance criteria

- `/reports/` shows the new chart above the daily-reports card grid, real
  figures matching `DailyAggregate`, in both themes.
- The chart and its table fallback render correctly with JavaScript
  disabled; the hover tooltip is the only thing JS adds.
- No new hex color introduced; the two colors used already exist in
  `tokens.css` and are traceable to `docs/brand-guidelines.md`.
- The daily `DailyReportPage` template is untouched by this plan.
- Tests cover the 30-day window boundary and pass in CI.
