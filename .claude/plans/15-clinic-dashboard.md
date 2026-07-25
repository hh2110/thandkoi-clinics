# Plan 15 — Clinic dashboard (range view) + dashboard entry points

**One-line:** a new `/reports/dashboard/` page that totals the daily reports
across a reader-chosen date range — KPIs, a bucketed footfall chart, funding
split, gender, age bands and reporting gaps — plus the two approved entry
points that lead to it.

## Background — why now

The site currently exposes clinic data one day at a time (`DailyReportPage`)
plus a rolling 30-day chart on the reports index (Plan 13). A donor or
trustee cannot answer "how many patients in the last quarter, and what share
were Zakat?" without adding up pages by hand.

The maintainer supplied a pre-built design handoff bundle
(`~/Downloads/dashboard.zip`, 2026-07-25) — same pattern as the Plan 11
D11/D13 handoffs. It is high-fidelity: three `.dc.html` prototypes, eight
screenshots, and a 500-line spec covering layout, tokens, copy and
interaction. The bundle is committed for provenance at
[`docs/design/clinic-dashboard-handoff.md`](../../docs/design/clinic-dashboard-handoff.md)
with the prototypes under [`docs/design/prototypes/`](../../docs/design/prototypes/)
and screenshots under [`docs/design/clinic-dashboard/`](../../docs/design/clinic-dashboard/),
following the existing `docs/design/` convention.

The handoff describes **three work items**:

1. **Clinic Dashboard page** — the range aggregate view.
2. **Revenue section on the daily report page** — per-service revenue split
   Regular/Zakat.
3. **Two entry points** — 1a (link in the reports-index footfall card head)
   and 1c (fourth tile in the Home impact band). Options 1b and 1d in the
   prototype were **not** chosen and are ignored.

Crucially, the handoff itself sequences this: **revenue data does not exist**
in `DailyAggregate` (which is why `zakat_avg_spend` on the home band is
hand-typed, `apps/core/models.py`). Work items 1 and 3 ship now without it;
work item 2 and the dashboard's revenue surfaces light up later when a
`service_revenue` column exists. This plan is therefore **Phase 1 only** —
Phase 2 is scoped at the bottom and parked pending one maintainer answer
(Q1).

Grounded against the real code before drafting (2026-07-25): `DailyAggregate`
fields, `ReportIndexPage.get_funding_mix` and its slot/gap logic,
`DailyReportPage.get_context`'s gender/age-band shape,
`partials/sections/stat_band.html`'s three consumers, `tokens.css`, and the
i18n setup. That pass turned up three places where the handoff's stated
assumptions do not match the repo — see D3, D4 and D8.

## Goal & scope

**Goal:** one new page at `/reports/dashboard/` (locale-prefixed, see D1)
showing period totals for any reader-chosen range, reachable from the reports
index and the home page.

### In scope (Phase 1 — ships without revenue data)

- **`ClinicDashboardPage`** — a Wagtail page under `ReportIndexPage` (D1),
  reading `start`/`end` query params, defaulting to the last 30 days.
- **Range aggregation module** (`apps/pipeline/dashboard.py`): param
  parsing/clamping, DB-side sums, age bands and funding/gender splits from
  `category_counts`, reporting-gap detection, and the `has_revenue` gate
  (D6).
- **Bucketed footfall chart** — day / week / month grain by range size (D3),
  server-rendered SVG reusing Plan 13's geometry (D2), with the `role="img"`
  + `aria-label` and `<details>` "View as table" fallback the existing chart
  already has.
- **`static/css/dashboard.css`** — page-scoped, mirroring `daily-report.css`
  / `report-index.css` conventions, tokens only, no new colour values (D4).
- **Revenue branches present but inert** — KPI count (3 vs 4 cards), the
  revenue card, and the side-column layout switch all written against
  `has_revenue`, so Phase 2 needs no template work.
- **Entry point 1a** — `Open the dashboard →` link in
  `.ri-funding-mix__head` on the reports index.
- **Entry point 1c** — fourth link tile in the Home impact band, added to
  `stat_band.html` as an **opt-in** extra so its two other consumers are
  untouched (D7).
- **No-JS baseline** — presets are links, the date form has a visible Apply
  (D9).
- **Tests** — range parsing/clamping, bucketing boundaries, empty range, gap
  detection, both entry-point links, the no-revenue layout, and that the
  newsletter/editorial stat bands are unchanged.
- **Dark-theme and responsive verification with live screenshots**, both
  themes, per the dark-mode trap recorded in memory (a token that "should"
  flip sometimes doesn't).

### Out of scope (parked, deliberately)

- **Work item 2 (daily-report Revenue section) and every revenue surface's
  real data** — Phase 2, below. Blocked on Q1, not on effort.
- **Urdu `.po` catalogue.** All new copy is wrapped in `{% translate %}` per
  repo convention, but the repo has **zero** `.po` files today (D8), so
  "Urdu translations required" from the handoff cannot be satisfied inside
  this plan without starting the site-wide catalogue. That is its own plan.
- **Computing the home band's `zakat_avg_spend` live** — the handoff itself
  marks this out of scope; it also depends on revenue data.
- **Department / diagnosis-category breakdowns** — already in
  `category_counts`, still deliberately unrendered (Plan 13's decision
  stands).
- **Nav entry for the dashboard** — reachable via 1a/1c only (Q2 default).
- **Caching / new indexes.** One range query per page view at one row per
  calendar day; the existing sequential scan is trivial at this scale (same
  reasoning as `apps/pipeline/impact_stats.py`).

## Decisions

**D1 — The dashboard is a Wagtail page, not a Django view or a routable
route.** `ClinicDashboardPage` becomes an allowed child of `ReportIndexPage`
(`subpage_types` gains it), slug `dashboard`, mirroring the
index-plus-child pattern every other section already uses. Rejected:
`RoutablePageMixin` (would add `wagtail.contrib.routable_page` to
`INSTALLED_APPS` — a pattern this repo uses nowhere) and a plain Django view
(would need hand-wiring into `i18n_patterns` ahead of Wagtail's catch-all,
and would sit outside the page tree that everything else lives in).
Consequence: the page must exist in the tree. It gets there the same way the
Reports index itself does — a `_get_or_create_clinic_dashboard()` helper
mirroring `apps/pipeline/report_publishing.py`'s
`_get_or_create_report_index` ("fetch if it exists, otherwise create it live
… so the first ever ingest doesn't depend on a maintainer having clicked it
into existence in `/admin/`"), called from a data migration so production
needs **no manual content-ops SSH step**.
**The real URL is `/en/reports/dashboard/`, not `/reports/dashboard/`** —
`config/urls.py` wraps Wagtail's catch-all in `i18n_patterns(...,
prefix_default_language=True)`, so the unprefixed path in the handoff does
not exist on this site. Query-param state (`?start=&end=`) is unchanged.

**D2 — The chart is server-rendered SVG with geometry computed in Python,
not the prototype's flex/div bars.** The prototype builds bars from nested
divs with percentage heights; the repo's own chart (Plan 13,
`ReportIndexPage.get_funding_mix`) computes paths, gridlines and tick
positions in Python and emits inline SVG, so it renders fully without JS.
Precedent wins. The geometry is **extracted into a shared module** rather
than copy-pasted (task 15.1), because the dashboard needs the same
stacked-bar, gap-slot and label-thinning logic with a different window and a
bucket grain.

**D3 — Bucketing is driven by the number of chart slots (Mon–Sat days in
range), not by "reporting days".** The handoff's table keys the grain off
reporting days, but the thing that overflows the card is the number of
**bars**, and a slot is reserved for every Mon–Sat date whether or not it
reported (that gap is the signal — Plan 13's rule, PR #124). A range with 30
reporting days spread over 400 calendar days would keep day-grain under the
handoff's wording and render ~340 slots. Thresholds are otherwise as
specified: ≤ 90 slots → one bar per day; 91–400 → one bar per week starting
Monday; > 400 → one bar per calendar month. Sundays never get a slot unless
they have a row.

**D4 — Bar tracks reuse `--color-border-default`; no `--color-track` token is
added.** The handoff's token table claims every colour maps to an existing
token, but `--color-track` does not exist in `tokens.css`. Its stated values
(light `#e6eded`, dark `--color-border`) are the dark-mode value of
`--color-border-default` exactly, and 3 hex points off it in light
(`#e0e7e8`) — invisible in practice. `daily-report.css`'s `.dr__bar-track`
already uses `--color-border-default` for exactly this purpose. Reusing it
keeps the no-new-colour-values rule the handoff itself sets.

**D5 — Percentages are of `total_visits`, and the unknown buckets are shown
by omission, not by a fourth category.** `DailyAggregate` carries
`other_or_unknown_sex_patients`, `unknown_payment_type_patients` and an
`unknown` age band; the design shows Female/Male, Zakat/Regular and four age
bands only. So: every "% of all visits" divides by `total_visits`, which
means Zakat% + Regular% (and the four age-band percentages) can legitimately
sum to less than 100 when unknowns exist. That is honest and matches
`DailyReportPage.get_context`, which already drops the same buckets from its
gender bars. Counts stay authoritative and are always rendered next to the
bars.

**D6 — Revenue is gated on data, not on a feature flag.** `has_revenue` is a
helper in `apps/pipeline/dashboard.py` that returns `False` today with a
docstring pointing at Phase 2, and becomes
`any(row.service_revenue for row in rows)` when the column exists. Every
revenue surface branches on it in the template from day one. No runtime flag
(see the Feature flag section).

**D7 — Entry point 1c extends the shared `stat_band.html` opt-in.**
`partials/sections/stat_band.html` has three consumers: the Home live impact
band, `NewsletterStatBandBlock`, and the editorial `ImpactStatsBlock`. The
link tile is therefore driven by optional `link_url` / `link_label` context —
absent for the other two, so their markup and grid are unchanged. A test
asserts that.

**D8 — `{% translate %}` yes, Urdu catalogue no.** `LOCALE_PATHS` is
configured but the repo contains **zero** `.po` files, so no UI string on the
site is actually translated yet. New copy follows the existing convention
(every string wrapped) and the handoff's exact strings are used verbatim;
producing the Urdu catalogue is a separate, site-wide piece of work, not
something this plan can honestly claim.

**D9 — No-JS first.** Preset pills are `<a>` links to the same URL with
computed `start`/`end`. The From/To inputs sit in a GET form with a visible
"Apply" submit. An optional ~10-line progressive enhancement may auto-submit
on `change`, mirroring `funding-mix-chart.js`'s documented pattern ("the
section renders fully without this script; this only adds…"). The page must
be fully usable with JS off.

**D10 — Range handling.** Default: last 30 days ending today. `end` earlier
than `start` collapses `end` to `start`. Unparseable or missing params fall
back to the default silently (no error page). Server-side safety cap: a range
longer than 5 years falls back to the default. Empty range renders zeros and
"No data" — no NaN, no crash, no empty-state exception. Aggregation is one
`.filter(clinic_date__range=(start, end))` with `.aggregate(Sum(...))` for the
named columns plus a Python pass over `category_counts`.

**D11 — Every number in the prototypes is invented sample data.** Nothing
from them is hardcoded; all figures are computed from `DailyAggregate`
(invariant #3's spirit — deterministic numbers, computed in Python).

**D12 — Privacy: no new surface.** The dashboard reads only
`DailyAggregate`, which is de-identified counts by construction. **No AI call
anywhere in this plan** — no summary sentence, no narrative. The reporting-gap
chips list dates only. Nothing here touches invariants #1–#5.

## Open questions for the maintainer

- **Q1 (blocks Phase 2 only).** Does the clinic's source register actually
  record **per-line charges** — Registration / Consultation / Pharmacy /
  Laboratory / Ultrasound, each with a quantity and an amount, split
  Regular/Zakat — or only a **per-visit total**? The handoff flags this
  explicitly: if it is a per-visit total, the table collapses to a single
  "Total charged" row rather than inventing a split. Phase 1 is unaffected.
- **Q2 (default assumed).** Should the dashboard appear in the primary nav?
  **Assumed no** — reachable from the reports index (1a) and home (1c), as
  the handoff's entry-point work item implies. Easy to flip later.
- **Q3 (default assumed).** Public or staff-only? **Assumed public**, same as
  the daily reports it aggregates — its audience in the handoff is "donor,
  trustee, staff" and it exposes nothing the daily pages don't.

## Precedent map (Stage 7)

| Element | Mirrors |
|---|---|
| Page type + `subpage_types` under an index | `ReportIndexPage` / `DailyReportPage`, `apps/pipeline/models.py` |
| Range aggregation module | `apps/pipeline/impact_stats.py` (single DB-side `Sum()` aggregate, own small module, dataclass return) |
| Stacked-bar SVG geometry, gap slots, label thinning | `ReportIndexPage.get_funding_mix` / `_funding_mix_slot_dates` / `_funding_mix_bar` (Plan 13, PR #122/#124) |
| Chart accessibility (`role="img"`, `aria-label`, `<details>` table) | `report_index_page.html` lines 38–90 |
| Page-scoped stylesheet, single wrapper class | `static/css/daily-report.css` (`.dr` scope), `report-index.css` (`.ri` scope) |
| Gender rows / age-band rows shape | `DailyReportPage.get_context` (`gender_rows`, `age_bands`) |
| Bar track colour | `.dr__bar-track` → `--color-border-default` |
| Optional context on a shared partial | `stat_band.html`'s existing optional `updated_caption` / `section_modifier` |
| Progressive-enhancement JS | `static/js/funding-mix-chart.js`, `circle-of-care.js` |
| Creating a singleton page in the tree | `_get_or_create_report_index` in `apps/pipeline/report_publishing.py` (get-or-create, live, under Home), and `seed_core_content`'s `_get` idiom it mirrors |
| Design provenance in-repo | `docs/design/README.md` + `docs/design/prototypes/*.dc.html` |

Gaps with no in-repo precedent, and how they are grounded instead:

- **Week/month bucketing of clinic dates** — no existing code buckets beyond
  per-day. Grounded on the handoff's explicit table, refined by D3; the
  boundary cases (90/91, 400/401) get their own tests.
- **Preset pill group + date-range form** — no date-range control exists on
  the site. Grounded on the handoff's spec and on plain HTML `<a>`/GET-form
  semantics (D9), not invented interaction.

## Feature flag (Stage 6)

**No runtime flag**, consistent with every plan in this repo. The natural
gates do the work here:

- Nothing on the site links to the dashboard until task 15.4 lands, so a
  half-finished page cannot reach a reader through any existing journey
  (it is reachable by URL, like any unlinked page — acceptable given Q3's
  public default and that it exposes nothing the daily reports don't).
- Every revenue surface is gated on `has_revenue` (D6), which is data
  presence, not configuration — the handoff's own design, and strictly better
  than a flag because it needs no second release and cannot drift out of sync
  with the data.

## Release plan (Stage 10)

- **How it ships.** Four PRs (below), each merged only after a clean
  `code-review-tc` pass and green CI, then deployed by the existing
  human-triggered `workflow_dispatch` release (`.github/workflows/deploy.yml`)
  against a dated tag. The dashboard page creates itself on deploy via the
  data migration (D1), but nothing links to it until task 15.4 ships — that
  ordering, not a flag or a manual step, is the staging point.
- **Gating check per phase.** (1) 15.3 deployed — the page exists and is
  correct at its URL, but no existing page links to it; walk the URL by hand
  in both themes and check a 7-day, a 90-day, a 1-year and an empty range.
  (2) 15.4 deployed — entry points live; verify from home and `/reports/`
  that both links appear and land on the dashboard.
- **Access.** Public once linked (Q3). No new permissions.
- **Informed.** Maintainer only; no downstream operators or customers.
- **Rollback trigger.** Any wrong figure, a crash on a range boundary, or a
  layout break in dark mode → unlink the entry points (a content edit, no
  deploy) as the fast lever; re-deploy the previous dated tag if the fault is
  in code.

## Tasks

One task = one PR, sequenced. Every PR: tests + lint green, `code-review-tc`
loop clean **before** `gh pr create`, opened as draft, labelled by
Conventional-Commit type.

- [ ] **15.1 — Extract the footfall-chart geometry** (`refactor`/`chore`).
      Move `get_funding_mix`'s geometry into `apps/pipeline/footfall_chart.py`
      taking (rows, start, end, grain) and returning the same dict.
      `ReportIndexPage.get_funding_mix` becomes a thin caller. **No behaviour
      change** — Plan 13's existing tests must pass untouched, which is the
      acceptance test for this PR.
- [ ] **15.2 — Range aggregation module** (`feat`). New
      `apps/pipeline/dashboard.py`: param parse/clamp (D10), DB-side sums,
      funding/gender/age-band rows (D5), reporting-gap dates, slot count and
      grain selection (D3), `has_revenue` stub (D6). Unit tests including the
      90/91 and 400/401 boundaries, the empty range, `end < start`, the 5-year
      cap, and gap detection across a Sunday. No UI in this PR.
- [ ] **15.3 — `ClinicDashboardPage` + template + CSS** (`feat`). Model,
      schema migration, `subpage_types` update, the get-or-create helper plus
      the data migration that calls it (D1), template composing
      header/presets/date form, KPI row, chart (via 15.1), funding split,
      gender, age bands, reporting gaps; `static/css/dashboard.css`; revenue
      branches present and inert. Tests: renders with 3 KPI cards and no
      revenue card, side cards two-up, `View as table` fallback lists every
      bucket, no-JS form works.
- [ ] **15.4 — Entry points 1a + 1c** (`feat`). Reports-index link in
      `.ri-funding-mix__head`; opt-in link tile in `stat_band.html` wired from
      the Home impact band (D7). Tests: both links present and pointing at the
      dashboard URL; newsletter and editorial stat bands render unchanged.
- [ ] **Verification, carried in each PR's test plan** (not a separate PR):
      real-browser screenshots of the dashboard and both entry points in
      **light and dark** at 1280px and tablet width, taken after the change —
      per the dark-mode trap (a token that reads correct in source can still
      fail to flip) and the broken-`resize_window` note (use the iframe
      harness, not the tool).
- [ ] **Roadmap index** — flip this plan's row to ✅ Done when 15.4 merges,
      in the same pass (Stage 9).

## Acceptance criteria

1. `/en/reports/dashboard/` renders with no query params, showing the last
   30 days: header line reads e.g. `26 Jun 2026 – 25 Jul 2026 · 30 days ·
   22 reporting days`, with correct pluralisation.
2. Preset links (7/14/30/90 days, 1 year) and the From/To form all work with
   **JavaScript disabled**; the preset matching the current range length
   renders selected.
3. Three KPI cards (Patients seen, Zakat visits, Regular visits) in
   `repeat(3, 1fr)`; **no** revenue card, **no** empty revenue table; Funding
   split and Gender sit side-by-side full width.
4. Figures equal the sum of the `DailyAggregate` rows in range; days with no
   row are excluded from totals, never counted as zero.
5. Chart grain switches at the D3 boundaries; Sundays get no slot; a
   Mon–Sat day with no row shows a visible gap; the caption states the grain;
   `role="img"` + `aria-label` present and `View as table` lists every bucket
   with Date/Zakat/Regular/Total.
6. Reporting-gap chips list every Mon–Sat date in range with no row, capped
   at 12 with a `+N more` chip, or the single `None — every open day
   reported` chip.
7. An empty range, a one-day range, a 5-year range and garbage params each
   render a sane page — no NaN, no 500.
8. Entry point 1a appears in the reports-index footfall card head; entry
   point 1c appears as the fourth tile in the Home impact band; the newsletter
   and editorial stat bands render unchanged.
9. Light **and** dark screenshots of the real rendered page at 1280px and
   tablet width are attached to the PRs, taken after the change.
10. No new colour values, fonts, or CSS frameworks; every colour is an
    existing token (D4).

---

## Phase 2 — parked until Q1 is answered

Not part of this plan's PRs; captured here so nothing is lost. Expected to
need **no template work** if Phase 1 lands correctly.

- [ ] Add `service_revenue` JSON column to `DailyAggregate` + migration
      (shape in the handoff: `{"consultation": {"regular": {"qty", "amount"},
      "zakat": {...}}, ...}`; PKR integers; `qty` counts services, not
      patients).
- [ ] Populate it in `apps.pipeline.ingest.recompute_daily_aggregate` and the
      `recompute_daily_aggregates` command — **after** confirming the source
      register's shape (Q1); if it only carries a per-visit total, collapse to
      one "Total charged" row rather than inventing a split.
- [ ] Confirm the gated surfaces light up on their own: the 4th KPI card,
      the "Revenue by service" card, the 1.75fr/1fr side-column layout, and
      the daily-report Revenue section with its split bar.
- [ ] Add the partial-data line under the table
      (`Revenue recorded for 12 of 22 reporting days.`).
- [ ] Compute the Home band's `zakat_avg_spend` live instead of hand-typing.
