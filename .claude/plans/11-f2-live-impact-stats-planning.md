# Plan 11, Track F2 — live "impact so far" home-page stats: Stage 2 planning

**Status:** planning doc per Stage 2/Stage 4 ("supporting docs" category) — settles
the approach before any code is written. Not a task file; F2 still needs Stage 6
slicing into a real numbered plan once this is read and confirmed. No code
changed, no migration written, in this doc.

Answers Track F2's own "Follow-up action" note in
[11-stakeholder-feedback-2026-07.md](11-stakeholder-feedback-2026-07.md) (lines
456-461): does a per-row date column already exist to group on, and how should
`DailyAggregate` be queried per-`report_kind` without a full-table-scan concern.

## What already exists to build on (precedent map, Stage 7)

- **The exact output shape already has two live-computed precedents in this
  repo** — neither is hand-typed, though only one reads `DailyAggregate`:
  - `DailyReportPage.headline_stats` (`apps/pipeline/models.py:491-510`) returns
    `[{"value": str(...), "label": _("...")}, ...]` computed straight from
    `self.aggregate` (a `DailyAggregate` row), explicitly documented as "read
    live from `aggregate`, never copied onto this page." **This is the
    precedent for reading `DailyAggregate` into this exact shape.**
  - `CampReportPage.get_context()` (`apps/core/models.py:763-773`) builds the
    same `{value, label}` shape as `patient_stats` — but from *that page's own*
    `patients_children`/`patients_general`/`patients_welfare` fields (plain
    `Page` fields an admin fills in per camp report, Plan 06), **not** from
    `DailyAggregate`. Correction while grounding this doc: `CampReportPage`
    (Plan 06, a hand-authored page per camp) and `DailyAggregate` rows with
    `report_kind="camp"` (Plan 11 C3, pipeline-ingested camp uploads) are two
    separate data paths that happen to share the word "camp" — F2 aggregates
    the latter, never the former. `CampReportPage.get_context()` is only cited
    here as a second precedent that `stat_band.html` already renders
    *computed*, non-StreamField dicts — not as evidence it reads
    `DailyAggregate`.
  - Both feed `templates/partials/sections/stat_band.html`, which only cares
    about the `{value, label}` shape — it has no idea whether the caller is a
    StreamField block, a page's own fields, or a `DailyAggregate` computation.
    **This means F2 needs no new partial and no new block type** — it needs a
    new context variable of the same shape, plumbed the same way.
- **`ImpactStatsBlock`/`ImpactStatBlock`** (`apps/core/blocks.py:79-104` /
  `19-35`) is the *hand-typed* path — StreamField-authored, admin types the
  string value and bumps `as_of` by hand. Its own docstring already names this
  moment: "Live computation from `DailyAggregate` rows is a separate future
  idea (Plan 11 candidate Track F, not built here)."
- **The home page's own "compute in `get_context`, render unconditionally
  beneath the StreamField body" pattern already exists twice** —
  `get_latest_report()` / `get_latest_newsletter()` (`apps/core/models.py:101-139`),
  each wired into `get_context()` and rendered via an unconditional
  `{% if %}` block in `home_page.html:25-31`, entirely separate from the
  StreamField `body` loop above them (`home_page.html:20-23`).
- **`compute_monthly_rollup()`** (`apps/pipeline/monthly_rollup.py:106-133`) is
  the existing cross-day summing precedent, but it sums in Python after
  pulling every matching row into memory (`rows = list(DailyAggregate.objects
  .filter(...))`, then `sum(getattr(row, name) for row in rows)`) — fine at
  one calendar month's row count, not the pattern to copy for an ever-growing
  all-time query (see "Query approach" below).
- **`DailyAggregate`'s indexing** (`apps/pipeline/models.py:292-337`):
  `clinic_date` has `db_index=True`; the natural key is a `UniqueConstraint`
  on `(clinic_date, report_kind)`. There is no standalone index on
  `report_kind`, and none is needed (see "Do we need a new index" below).

## Decisions settled by this doc

### 1. Data layer: a new module, DB-side aggregation, not a Python loop

New function `compute_alltime_impact_stats()` in a new module
`apps/pipeline/impact_stats.py` (not added to `monthly_rollup.py` — that
module's name, docstring, and every existing caller are scoped to *calendar-
month* rollups; an all-time total is a different unit of aggregation and
deserves its own small module rather than overloading that one).

Query shape — one grouped, DB-side aggregate, not a Python `sum()` over
loaded rows:

```python
from django.db.models import Sum

rows = (
    DailyAggregate.objects
    .values("report_kind")
    .annotate(
        total_visits=Sum("total_visits"),
        zakat_beneficiary_patients=Sum("zakat_beneficiary_patients"),
    )
)
```

This is one round trip, grouped by `report_kind` in Postgres itself — it
directly answers the plan's open question about querying "per-`report_kind`
... without a per-request full-table scan": the database does the summing,
Django never materializes per-row objects at all (unlike
`compute_monthly_rollup`'s `list(...)`).

### 2. No new index needed now

`Sum()` over a `PositiveIntegerField` is a sequential scan regardless of
index — indexes speed up row *selection*, not column *aggregation* across
all rows. This clinic produces at most one `DailyAggregate` row per calendar
day per `report_kind`; even at 10 years of daily uploads that's ~3,650 rows,
trivial for Postgres to sum. Revisit only if row count grows by orders of
magnitude beyond a single physical clinic's plausible scale — not
speculatively.

### 3. No caching needed now, for the same scale reason

A sub-millisecond aggregate on every home-page request is not a performance
concern at this traffic/data scale. Note as a future candidate (e.g. Django's
per-view cache, or a cached property refreshed on `DailyAggregate` save) only
if either row count or home-page traffic grows enough to matter — not now.

### 4. Which figures to show, and how clinic/camp stay separate

Per Track F2's maintainer decision (11-stakeholder-feedback-2026-07.md:448-451):
keep camp and clinic numbers distinguishable, never folded into one combined
total. Concretely, `get_live_impact_stats()` returns one `{value, label}` pair
per `(metric, report_kind)` combination actually present with a nonzero row
count — mirroring `stat_band.html`'s existing 3-column convention
(`DailyReportPage.headline_stats` and `CampReportPage.patient_stats` both show
exactly 3 stats today):

- `{{ clinic total_visits }}` → label "Clinic patients (all time)"
- `{{ camp total_visits }}` → label "Camp patients (all time)"
- `{{ clinic + camp zakat_beneficiary_patients, summed }}` → label "Zakat
  beneficiaries (all time)" — this one figure *is* a cross-`report_kind` sum,
  deliberately: Zakat-funded care is the clinic's core mission framing
  regardless of venue, unlike patient counts which the maintainer specifically
  wants split by venue.

This set is a proposed default, easy to change at the task-slicing stage
(Stage 6) — it's a labeling/selection choice, not an architecture decision,
so it doesn't block confirming the rest of this doc.

### 4a. Historical offset for the camp figure (maintainer decision, 2026-07-23)

The very first camp predates this pipeline entirely — it has no
`DailyReportPage`/`DailyAggregate` row, and per the maintainer it never will
(no report will be entered for it retroactively). Without correction, the
"Camp patients (all time)" figure would silently under-count by however many
patients that first camp actually served, for as long as the site exists.

**Decision:** `compute_alltime_impact_stats()` adds a fixed historical offset
of **187** on top of whatever `DailyAggregate` rows with `report_kind="camp"`
sum to, applied only to the camp `total_visits` total:

```python
CAMP_PATIENTS_PRE_PIPELINE_OFFSET = 187  # the first camp, never digitized — see decision note

camp_total_visits = CAMP_PATIENTS_PRE_PIPELINE_OFFSET + Sum(...)  # report_kind="camp" rows only
```

- **A named module-level constant, not a Wagtail-editable setting.** This is a
  one-time historical correction for a fact that cannot recur (there is only
  ever one "first camp" from before the pipeline existed) — an admin-editable
  field would be unused surface area for a number that should essentially
  never change, not house style being followed. If more pre-pipeline camps
  turn out to be un-recorded later, that's a new decision to make explicitly
  then, not a case for building configurability now.
- **Scoped to the camp total only — not the Zakat-beneficiary figure.** The
  maintainer's ask was specifically about the camp patient count; whether
  those 187 patients were Zakat beneficiaries is unknown to this doc. Folding
  an unverified split into the Zakat figure would be inventing a number
  invariant #3 doesn't allow, whereas leaving the Zakat total exactly as
  computed from real rows is honest about what's actually known — it just
  slightly under-states the Zakat total by however many of those 187 would
  have qualified. **Open question for the maintainer:** if the split for that
  first camp is known (e.g. "all 187 were Zakat beneficiaries"), say so and
  this doc will add a second offset constant for the Zakat sum too.
- Documented in the module's docstring the same way this repo documents every
  other magic number (e.g. `ImpactStatBlock`'s "Real figures are entered by
  hand for now" note, `DailyAggregate`'s `report_kind` docstring) — why it
  exists, its exact value, and that changing it needs a matching decision
  recorded here, not a silent edit.

### 5. StreamField `ImpactStatsBlock` — left alone

No change to `ImpactStatsBlock`/`ImpactStatBlock`. The live stats become a
**new, separate, unconditionally-rendered section**, following the exact
`get_latest_report()`/`get_latest_newsletter()` teaser pattern already in
`home_page.html` — not a replacement of the StreamField block, and not a
"seed the block's value automatically" hybrid (that would make an
admin-editable field silently overwritten by code, which is worse than either
pure option). If the maintainer decides at Stage 6 that the hand-typed block
should be retired from the home page entirely now that a live section exists,
that's a one-line follow-up (delete the block from `HomePage.body`'s block
list) — but it is not required for F2 to ship, and doesn't change any of the
data-layer decisions above.

### 6. Wiring — mirrors `get_latest_report()` exactly

- `HomePage.get_live_impact_stats()` — new method next to
  `get_latest_report()`/`get_latest_newsletter()` (`apps/core/models.py`),
  calling `compute_alltime_impact_stats()` and shaping the result into the
  `[{"value":, "label":}]` list `stat_band.html` expects (same stringification
  convention as `DailyReportPage.headline_stats`: `str(count)`, translated
  labels via `_(...)`).
- Wired into `get_context()` alongside the other two.
- `home_page.html` gets one more unconditional include, same shape as the
  existing two teasers:
  ```
  {% include "partials/sections/stat_band.html" with stats=live_impact_stats caption=_("Our impact so far") %}
  ```
  `stat_band.html` already has an empty-state ("Figures coming soon.") for
  zero stats, so this degrades gracefully before any `DailyAggregate` rows
  exist — no conditional guard needed in the template, matching that
  partial's existing contract rather than re-implementing it.

## Feature flag (Stage 6 convention)

None — per Plan 11's repo-wide convention (pre-launch site, no existing users
a partial slice could reach; recorded once per plan so the omission stays a
deliberate choice, not an oversight).

## Release plan (Stage 10, lite)

- **Ships as:** a normal draft PR — implement, `code-review-tc` loop, `gh pr
  create --draft`, merge once green. Single home page, no phased rollout
  needed (low blast radius, easily revertable).
- **Access:** live to all site visitors immediately on merge — no gating,
  this is public-facing figures, not PHI.
- **Informed:** maintainer only (personal-scale site); no other stakeholders.
- **Rollback trigger:** if the computed figures look wrong on the live site,
  revert the PR — the StreamField `ImpactStatsBlock` (untouched by this work)
  remains available as a fallback hand-typed section if the maintainer wants
  to temporarily restore manual figures while a bug is fixed.

## Relationship to F1 (multi-day camp upload)

None of the above depends on F1. F2's query works today against however many
`DailyAggregate` rows already exist from the current one-file-one-day upload
flow; F1 only changes how quickly future rows accumulate, not whether F2's
aggregation is correct. They can be built and shipped in either order.

## Open items deferred to Stage 6 task-slicing

- Final figure/label selection (section 4 above) — a content decision, not
  architectural.
- Whether to retire `ImpactStatsBlock` from the home page once the live
  section ships (section 5) — maintainer's call, not required for F2.
- Exact caption/eyebrow copy for the new section.
- Whether the 187-patient historical camp offset (section 4a) also has a
  known Zakat/regular split — currently applied only to the camp total.

## Reference material

- [11-stakeholder-feedback-2026-07.md](11-stakeholder-feedback-2026-07.md) —
  Track F's original framing and maintainer decisions (lines 421-461).
- [11-e1-e2-research-2026-07.md](11-e1-e2-research-2026-07.md) — sibling
  Stage 2/4 planning doc this one's structure mirrors.
- `apps/pipeline/monthly_rollup.py`, `apps/pipeline/models.py:275-360`,
  `apps/core/models.py:43-143`, `templates/partials/sections/stat_band.html`,
  `templates/blocks/impact_stats_block.html`, `apps/core/blocks.py:19-104` —
  every file cited in the precedent map above.
