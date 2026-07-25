# Handoff: Clinic Dashboard, Daily-Report Revenue, and Dashboard Entry Points

## Overview

Three related pieces of work for the Thandkoi Clinics Wagtail/Django site
(`thandkoi-clinics`):

1. **New page — Clinic Dashboard.** An aggregate view across daily reports for
   a user-chosen date range (no maximum range), with KPIs, a footfall chart,
   revenue by service split Regular/Zakat, funding split, gender, age bands
   and reporting gaps.
2. **Daily report page — add a "Revenue" section.** Registration,
   Consultation, Pharmacy, Laboratory, Ultrasound, each split Regular / Zakat
   / Total, showing amount and quantity, plus a totals row and a split bar.
3. **Two entry points to the dashboard** — approved options **1a** (Reports
   page) and **1c** (Home page impact bar). The other two options in the
   entry-points file (1b, 1d) were **not** chosen; ignore them.

## About the design files

The `.dc.html` files in this bundle are **design references created in HTML** —
prototypes that show intended look, structure and behaviour. They are **not**
production code to copy. The task is to recreate them inside this repo's
existing environment: Django + Wagtail templates, the token-based CSS in
`static/css/` (`tokens.css`, `layout.css`, `report-index.css`,
`daily-report.css`), `{% translate %}` for all user-facing copy, and
server-rendered SVG/HTML as the existing footfall chart already does.

Open a `.dc.html` file directly in a browser to see it run; `support.js` and
`fonts/` are included so they work offline. Numbers in the prototypes are
**invented sample data** generated deterministically from each date — treat
them as shape, not truth.

## Fidelity

**High fidelity.** Colours, type, spacing and interaction are final and come
from `static/css/tokens.css`. Recreate pixel-faithfully using existing tokens
and CSS conventions — do not introduce new colour values, new fonts, or a
CSS-in-JS/utility framework. Every colour below maps to an existing token; use
the token, not the hex.

---

# Work item 1 — Clinic Dashboard page

**Design file:** `Clinic Dashboard.dc.html`

## Purpose

Let a reader (donor, trustee, staff) see totals across a chosen period rather
than one day at a time: how many patients, what share were Zakat, what the
clinic's service revenue was, and where reporting gaps are.

## Data — what exists and what must be added

Existing (`apps/pipeline/models.py`):

- `DailyAggregate.clinic_date` (unique natural key)
- `total_visits`, `male_patients`, `female_patients`,
  `other_or_unknown_sex_patients`
- `zakat_beneficiary_patients`, `paying_patients`,
  `unknown_payment_type_patients`
- `category_counts` JSON — already carries `by_age_band`

**Revenue does not exist yet — and is not a prerequisite.** `DailyAggregate`
carries no fee or expenditure data (this is noted in `apps/core/models.py` as
the reason `zakat_avg_spend` is hand-typed). Build all three work items so
they **ship today without revenue and light up automatically when revenue
arrives** — see "Revenue-optional behaviour" below. Every revenue surface is
gated on data being present, never on a feature flag or a second release.

When revenue is added, the recommended shape is one new JSON column so no
migration is needed per service:

```python
service_revenue = models.JSONField(
    default=dict, blank=True,
    help_text="Per-service revenue for this clinic-date: "
              '{"consultation": {"regular": {"qty": 3, "amount": 750}, '
              '"zakat": {"qty": 4, "amount": 1000}}, ...}',
)
```

Services, in this display order: **Registration, Consultation, Pharmacy,
Laboratory, Ultrasound**. Amounts are PKR integers. `qty` is the number of
that service delivered (not the number of patients) — a patient can have
several. Populate it in `apps.pipeline.ingest.recompute_daily_aggregate`
alongside the existing counts, and extend `recompute_daily_aggregates`.

Confirm with the clinic whether the source register actually records per-line
charges before designing the ingest side; if it only records a per-visit
total, collapse the table to one "Total charged" row rather than inventing a
split.

## Revenue-optional behaviour

Treat revenue as a nullable extra everywhere. One helper decides it:

```python
has_revenue = any(row.service_revenue for row in rows_in_range)
```

(before the field exists, that is simply `False` — a module-level
`has_revenue = False` constant is an acceptable first cut, provided the
templates already branch on it.)

| Surface | `has_revenue = False` | `has_revenue = True` |
|---|---|---|
| Dashboard KPI row | **3 cards** — Patients seen, Zakat visits, Regular visits — in `repeat(3, 1fr)` | **4 cards**, the fourth being Total revenue (PKR), in `repeat(4, 1fr)` |
| Dashboard "Revenue by service" card | Card omitted entirely. The section becomes a single row: Funding split and Gender sit **side by side** in `repeat(2, 1fr)` at full width instead of stacking in the 1fr side column | Table left (1.75fr), Funding split + Gender stacked right (1fr) |
| Daily report Revenue section | Section omitted entirely (no empty table, no zero row) | Full section incl. split bar |
| Home impact band (1c) | Unchanged — the link tile does not depend on revenue | Unchanged |
| Reports page (1a) | Unchanged | Unchanged |

Partial data is the normal case once ingest starts: a range can contain some
dates with `service_revenue` and some without. Then **show the table**, sum
only the dates that have it, and add a line under the table at `.82rem`
`--color-text-faint`: `Revenue recorded for 12 of 22 reporting days.`
Patient counts are never affected by missing revenue.

So the delivery order is: ship work item 1 (minus the revenue table) and work
item 3 now; the revenue table and work item 2 appear on their own the day the
first `service_revenue` row lands. No template change needed at that point.

## Aggregation

All figures are sums over `DailyAggregate` rows whose `clinic_date` falls in
`[start, end]`. Days with no row are "not reported" and are excluded from
every total (they are **not** zeros). One query, `.filter(clinic_date__range=)`
with `.aggregate(Sum(...))` for the named columns, plus a Python pass for the
JSON fields.

## Layout

Page shell: `--color-bg`, centred column, `max-width: 1180px`,
padding `2.75rem 2.5rem 4rem`, sections stacked with `2rem` gap.

### 1. Header

- Eyebrow "Thandkoi Clinics" — Archivo 700, `.78rem`, uppercase,
  `letter-spacing:.14em`, `--color-accent`.
- `<h1>` "Clinic dashboard" — Archivo 800, `2.5rem`, `line-height:1`,
  `letter-spacing:-.01em`, `--color-text`.
- Range summary line, `1rem`, `--color-text-soft`, format:
  `26 Jun 2026 – 25 Jul 2026 · 30 days · 22 reporting days`
  (pluralise "day"/"days" and "reporting day"/"reporting days").
- Right side, stacked and right-aligned:
  - **Preset pill group** — surface background, 1px `--color-border-default`,
    `border-radius:999px`, `4px` padding, `.35rem` gap. Buttons: Public Sans
    600, `.82rem`, padding `.35rem .85rem`, radius 999px. Selected =
    `--color-brand` background, white text; unselected = transparent,
    `--color-text-soft`. Presets: **7 days, 14 days, 30 days, 90 days,
    1 year** (all ending today). A preset is shown selected when the current
    range length equals it.
  - **From / To date inputs** — surface card, 1px border, `radius:10px`,
    padding `.55rem .8rem`. Field labels "From"/"To" are Archivo 700,
    `.65rem`, uppercase, `letter-spacing:.1em`, `--color-text-faint`.
    Inputs are borderless and transparent, `.92rem`. `max` = today.
- Header has a `1px` bottom border `--color-border-default`,
  `padding-bottom:1.75rem`.

**Range rules:** no maximum. If `To` is set earlier than `From`, collapse
`To` to `From`. Server-side, cap only for safety (e.g. reject > 5 years) and
validate/parse both dates, falling back to the default 30-day window.

### 2. KPI row

4 equal cards, `1rem` gap. Card: `--color-surface`, 1px
`--color-border-default`, `radius:12px`, padding `1.35rem 1.5rem`.

- Value — Archivo 800, `2.1rem`, `line-height:1`, `--color-stat-value`,
  `font-variant-numeric:tabular-nums`, thousands separators.
- Label — `.88rem`, 600, `--color-text-soft`, margin-top `.55rem`.
- Sub-line — `.8rem`, `--color-text-faint`.

| Card | Value | Sub-line |
|---|---|---|
| Patients seen | Σ `total_visits` | `9.5 per reporting day` (1 dp) or "No data" |
| Zakat visits | Σ `zakat_beneficiary_patients` | `74% of all visits` |
| Regular visits | Σ `paying_patients` | `26% of all visits` |
| Total revenue (PKR) | Σ all service revenue | `1,405 per patient` or "No data" |

The fourth card renders **only** when revenue data exists for the range; with
three cards the grid is `repeat(3, 1fr)`. See "Revenue-optional behaviour".

### 3. Patient footfall chart

Card: surface, 1px border, `radius:14px`, padding `1.75rem 1.9rem`.

- Title "Patient footfall" — Archivo 800, `1.25rem`.
- Legend right-aligned: Zakat = `--color-brand` swatch, Regular =
  `--color-text-faint` swatch; 11px squares, `radius:2px`, label `.88rem`
  `--color-text-soft`.
- Plot area is **240px tall**. Y tick labels sit in a left column of the same
  height, `column-reverse` + `space-between`, `.78rem`,
  `--color-text-faint`; the column is `calc(240px + .78rem)` tall with
  `margin:-.39rem 0` so labels centre on their gridlines.
- Gridlines are 1px `--color-border-default` divs, absolutely positioned
  **inside** the 240px plot box (`inset:0`, `column-reverse`,
  `space-between`) — they must not extend into the label row, or bars stop
  landing on their lines.
- Bars: one flex column per bucket, `flex:1; min-width:0`, gap `2px`
  (`1px` when more than 60 bars). The bar itself is `width:100%`,
  `max-width:20px`, `height: total / yMax * 100%`, `radius:2px 2px 0 0`,
  `overflow:hidden`, and stacks Regular (`--color-text-faint`) above Zakat
  (`--color-brand`) as percentage-height children.
- Date labels are a **separate row below** the plot (`margin-top:.5rem`, same
  gap), one `flex:1` centred span per bucket, `.72rem`,
  `--color-text-faint`, `white-space:nowrap`; only every
  `ceil(bucketCount / 8)`-th is filled.
- Y scale: `yMax = ceil(peak / step) * step` where step is
  2 / 5 / 10 / 20 / 50 / 100 / 200 as the peak passes
  10 / 20 / 40 / 80 / 200 / 400.

**Bucketing (important).** Bar count must stay bounded or long ranges overflow
the card:

| Reporting days in range | Grain | Label format |
|---|---|---|
| ≤ 90 | one bar per day | `24 Jul` (`24 Jul 26` if the range spans > 300 days) |
| 91–400 | one bar per week, weeks starting Monday | `20 Jul` |
| > 400 | one bar per calendar month | `Jul 26` |

Sundays are excluded entirely (no column). A Monday–Saturday date with no
`DailyAggregate` row keeps its slot but renders no bar — that gap is the
signal.

Caption below the chart, `.85rem`, `--color-text-faint`, max 70ch, states the
grain then the existing sentence:
`One bar per week, starting Monday. Sundays are omitted — the clinic is
closed. A gap marks a Monday–Saturday day with nothing reported, including
holidays.`

Match the existing chart's accessibility: `role="img"` + `aria-label`, and a
`<details>` "View as table" fallback listing each bucket (Date, Zakat,
Regular, Total) — as `report_index_page.html` already does.

### 4. Revenue by service (left, 1.75fr) + side column (1fr)

Table card: surface, 1px border, `radius:14px`, `overflow:hidden`.

- Head row: title "Revenue by service" (Archivo 800, `1.25rem`) and
  `PKR · quantity in brackets` (`.82rem`, `--color-text-faint`).
- **Every row — header, data, total — must use the same grid:**
  `grid-template-columns: minmax(0,1.4fr) repeat(3, minmax(0,1fr))`,
  `gap:.75rem`, padding `.9rem 1.5rem`. The `minmax(0,…)` is required: with
  plain `1fr`, wide figures blow the tracks out by a different amount in each
  row and the columns stop lining up. Inner amount+qty wrappers need
  `min-width:0`.
- Column heads: Archivo 700, `.7rem`, uppercase, `letter-spacing:.1em`,
  `--color-text-faint`; Service left, the other three right-aligned.
- Data rows, bottom border `--color-border-default`:
  - Service name — `.95rem`, 600, `--color-text`.
  - Regular / Zakat — `.95rem`, `--color-text-soft`, then the quantity in
    brackets at `.74rem`, `--color-text-faint`, `white-space:nowrap`,
    `.3rem` gap. Example: `13,500 (54)`.
  - Total — Archivo 700, `1rem`, `--color-text`, plus bracketed quantity.
  - All numerals `font-variant-numeric: tabular-nums`.
- Total row: background `--color-track` (light `#e6eded`, dark
  `--color-border`), padding `1.15rem 1.5rem`. Label "Total" Archivo 800
  `.95rem`; Regular/Zakat Archivo 700 `1rem` `--color-text-soft`; grand total
  Archivo 800 `1.3rem` `--color-stat-value`.

Side column, two cards, `1.25rem` gap, each surface / 1px border /
`radius:14px` / padding `1.6rem 1.7rem`:

- **Funding split** — 12px stacked bar, `radius:999px`, track
  `--color-track`; Zakat segment `--color-brand`, Regular
  `--color-text-faint`, widths = share of visits. Below it two rows: swatch +
  label left, count right (Archivo 700, `.95rem`).
- **Gender** — Female then Male; label `.92rem` `--color-text-soft` left,
  count Archivo 700 right, then a 6px `radius:999px` track with a fill
  proportional to the larger of the two (Female `--color-brand`, Male
  `--color-text-faint`).

### 5. Age bands

Full-width card, 4 equal columns, `1.25rem` gap. Bands **0–5, 6–18, 19–55,
56+** (read from `category_counts["by_age_band"]`). Each: label `.9rem`
`--color-text-soft` left / count Archivo 800 `1.4rem` `--color-stat-value`
right; 8px track with `--color-brand` fill scaled to the largest band;
`{n}% of visits` beneath at `.8rem` `--color-text-faint`.

### 6. Reporting gaps

Surface card with a 3px left border in `--color-accent`, `radius:10px`,
padding `1.1rem 1.4rem`. Eyebrow "Reporting gaps in this range" (Archivo 700,
`.7rem`, uppercase, `letter-spacing:.1em`, `--color-text-faint`). Then chips:
`.82rem`, `--color-text-soft`, background `--color-track`, `radius:6px`,
padding `.22rem .6rem`, `.4rem` gap — one per Monday–Saturday date in range
with no aggregate row. Show at most 12 and append a `+N more` chip. If there
are none, show a single chip: `None — every open day reported`.

## Interactions & state

Server-rendered, no client framework. State is the URL:
`/reports/dashboard/?start=YYYY-MM-DD&end=YYYY-MM-DD`.

- Preset buttons are links to that URL with computed dates (progressive
  enhancement: JS may swap them client-side, but they must work without JS).
- Date inputs submit their form on `change`; a visible "Apply" submit button
  must exist for keyboard/no-JS users.
- Default when no params: last 30 days ending today.
- Invalid/missing params fall back to the default silently.
- Empty range (no reporting days): KPIs show `0` and "No data", chart shows
  an empty plot with axis, tables show zeros. No NaN, no crash.

## Dark theme

Every colour is a token, so dark mode should need no extra work — but check
the chart: the Regular segment (`--color-text-faint`, `#9ea0a1` dark) against
`--color-surface` `#0d4f5c`, and gridlines `--color-border` `#195a67`.

---

# Work item 2 — Revenue section on the daily report page

**Design file:** `Daily Report Redesign.dc.html` (the "Revenue" section between
"Breakdown" and "Today's notes, summarised"). The rest of that file documents
the existing daily-report page and is unchanged.

Same table as the dashboard's "Revenue by service", scoped to one clinic-date,
plus:

- Section heading is the small style — Archivo 800, `1.05rem`, uppercase,
  `letter-spacing:.08em`, `--color-text-faint` — with `All figures in PKR`
  right-aligned at `.82rem`.
- Below the total row, inside the same card, a **split bar**: 10px,
  `radius:999px`, track `--color-track`; Regular in `--color-stat-value`,
  Zakat in `--color-text-faint`, widths = share of total revenue. Legend
  under it: `Regular 39%` / `Zakat 61%`, `.85rem`, 9px `radius:2px`
  swatches.
- Rows follow the daily-report card padding (`1.5rem` horizontal), same
  `minmax(0,…)` grid rule as above.
- **If a date has no `service_revenue` data, omit the whole section** — no
  heading, no empty table, no zero row. This is the expected state until
  revenue ingest exists, so build the section behind that check from the
  start.

---

# Work item 3 — Entry points (approved: 1a and 1c)

**Design file:** `Dashboard Entry Points.dc.html` — implement **1a** and
**1c** only.

## 1a — Reports page, link in the footfall card header

In `apps/pipeline/templates/pipeline/report_index_page.html`, the
`.ri-funding-mix__head` currently holds only the `<h2>`. Make it a
space-between row and add a link after the title:

- Copy: `Open the dashboard →` (wrap in `{% translate %}`).
- Style: inline-flex, `.95rem`, 600, `--color-brand`, no underline, 1px
  `--color-brand` border, `radius:999px`, padding `.5rem 1rem`,
  `flex:none`.
- Hover: background `--color-brand`, text `--color-on-brand`.
- Focus: the site's standard `--color-focus-ring` outline.
- The caption keeps its existing max-width so the two never collide; on
  narrow viewports the link wraps below the title (`flex-wrap:wrap`,
  `gap:1rem`).

## 1c — Home page, fourth tile in the impact bar

In the home page impact band (`HomePage.impact_stats` + its template), the
stat grid becomes `auto repeat(4, 1fr)` — the three existing stat cards plus
a link tile:

- Same card box as a stat card: `--color-surface`, `radius:12px`, padding
  `1.4rem 1.5rem`, full height, but with a 1px `--color-accent` border.
- Contents, stacked with `.5rem` gap and vertically centred: an arrow glyph
  `→` in Archivo 800, `1.6rem`, `--color-accent`; then
  `See the live dashboard` in Archivo 700, `1rem`, `--color-text`.
- Hover: background lifts to a soft amber tint (light: `#fdf4e6`; dark: use
  `--color-accent-soft-bg`). Whole tile is the link.
- Because the row gains a column, the three stat values stay at `2rem`
  Archivo 800 (down from the current larger size at that width) — check the
  band at 1280px and at tablet, where the grid should drop to two columns
  with the link tile last.

Note: the impact band's third stat (`zakat_avg_spend`) is currently
hand-typed. Once `service_revenue` exists it can be computed live — worth
doing in the same pass, but out of scope for this handoff.

---

## Design tokens

All from `static/css/tokens.css` — use the token, never the hex.

| Token | Light | Dark |
|---|---|---|
| `--color-brand` / teal brand | `#086c7e` | `#086c7e` |
| `--color-brand-hover` / teal bright | `#12879b` | `#12879b` |
| `--color-accent` (amber) | `#ce8a2c` | `#e8b04a` |
| `--color-stat-value` | `#086c7e` | `#a0e0e8` (pale aqua) |
| `--color-text` | `#0e2025` | `#f2f6f6` |
| `--color-text-soft` | `#3e5257` | `#abb4b6` |
| `--color-text-faint` | `#728a8f` | `#9ea0a1` |
| `--color-border-default` | `#e0e7e8` | `#195a67` |
| `--color-bg` | `#f2f6f6` | `#0a3e48` |
| `--color-surface` | `#ffffff` | `#0d4f5c` |
| `--color-accent-soft-bg` | `#e4f4f6` | `#0b4753` |
| track (bar backgrounds) | `#e6eded` | `--color-border` |

**Type.** Archivo 700/800 for headings, numerals and eyebrows; Public Sans
400/600 for body. Scale used here: `2.5rem` h1, `1.25rem` section h2,
`1.1rem` card h2, `1.05rem` uppercase section label, `2.1rem` KPI value,
`1rem` / `.95rem` body, `.88rem`–`.82rem` secondary, `.78rem`–`.7rem`
eyebrows and ticks. All numerals `font-variant-numeric: tabular-nums`.

**Spacing.** Page padding `2.75rem 2.5rem 4rem`; section gap `2rem`; card
padding `1.35rem 1.5rem` (KPI) / `1.6rem 1.7rem` (side cards) /
`1.75rem 1.9rem` (chart) / `.9rem 1.5rem` (table rows); grid gaps `1rem`–
`1.25rem`.

**Radii.** 999px pills and bar tracks · 14px large cards · 12px stat cards ·
10px inset panels · 6px chips · 2px bar tops and swatches.

**Borders/shadows.** 1px `--color-border-default` throughout; no shadows
anywhere (the site's cards are flat).

## Assets

None new. Fonts (`archivo-latin-700-800.woff2`,
`public-sans-latin-400-600.woff2`) are copies of the repo's own files,
included only so the prototypes render offline.

## Copy (exact strings, all need `{% translate %}`)

- `Clinic dashboard` · `Thandkoi Clinics`
- `7 days` · `14 days` · `30 days` · `90 days` · `1 year` · `From` · `To`
- `Patients seen` · `Zakat visits` · `Regular visits` ·
  `Total revenue (PKR)` · `per reporting day` · `% of all visits` ·
  `per patient` · `No data`
- `Patient footfall` · `Zakat` · `Regular` · `View as table`
- `One bar per day the clinic reported data.` /
  `One bar per week, starting Monday.` / `One bar per month.` +
  `Sundays are omitted — the clinic is closed. A gap marks a
  Monday–Saturday day with nothing reported, including holidays.`
- `Revenue by service` · `PKR · quantity in brackets` · `Service` ·
  `Regular` · `Zakat` · `Total` · `Registration` · `Consultation` ·
  `Pharmacy` · `Laboratory` · `Ultrasound`
- `Funding split` · `Zakat patients` · `Regular patients` · `Gender` ·
  `Female` · `Male` · `Age bands` · `% of visits`
- `Reporting gaps in this range` · `None — every open day reported` ·
  `+{n} more`
- `Open the dashboard →` (1a) · `See the live dashboard` (1c)

Urdu translations are required for all of the above — the site ships an Urdu
locale. Numerals stay Latin, as elsewhere on the site.

## Checklist

Phase 1 — ships now, no revenue data required:

- [ ] New `ClinicDashboardPage` (or a plain view under the Reports index) at
      `/reports/dashboard/`, with `start`/`end` query params
- [ ] Range aggregation helper: sums, per-service revenue, age bands, gaps
- [ ] Bucketing helper: day / week / month by reporting-day count
- [ ] Dashboard template + a `dashboard.css` following the existing CSS
      conventions
- [ ] `View as table` fallback + `role="img"`/`aria-label` on the chart
- [ ] `has_revenue` gate wired through both templates (KPI count, revenue
      card, side-column layout, daily-report section) — inactive but present
- [ ] Entry point 1a on the Reports index
- [ ] Entry point 1c in the Home impact band
- [ ] Urdu strings for every new label
- [ ] Dark-theme pass
- [ ] Tests: range parsing/clamping, bucketing boundaries (90/400 days),
      empty range, gap detection, both entry-point links present, and the
      **no-revenue layout** (3 KPI cards, no revenue card, two-up side cards)

Phase 2 — the day revenue data exists, no template work should be needed:

- [ ] Add `service_revenue` (or equivalent) to `DailyAggregate` + migration
- [ ] Populate it in `recompute_daily_aggregate` and the management command
- [ ] Confirm the revenue surfaces appear on their own; add the partial-data
      line (`Revenue recorded for 12 of 22 reporting days.`)
- [ ] Compute the home band's `zakat_avg_spend` live instead of hand-typing

## Files in this bundle

| File | What it is |
|---|---|
| `Clinic Dashboard.dc.html` | Work item 1 — the dashboard, interactive (presets and date inputs work) |
| `Daily Report Redesign.dc.html` | Work item 2 — daily report incl. the new Revenue section |
| `Dashboard Entry Points.dc.html` | Work item 3 — options 1a (approved), 1b, 1c (approved), 1d |
| `screenshots/01–04-clinic-dashboard.png` | The dashboard, top to bottom |
| `screenshots/01–03-daily-report.png` | Daily report incl. the Revenue section (dark theme) |
| `screenshots/entry-point-1a-reports-page.png` | Approved entry point 1a |
| `screenshots/entry-point-1c-home-impact-bar.png` | Approved entry point 1c |
| `support.js`, `fonts/` | Runtime + fonts so the above open offline in a browser |

Note: the prototypes always show the revenue surfaces (they carry sample
revenue). The no-revenue layouts described above have no mock — follow the
table in "Revenue-optional behaviour".
