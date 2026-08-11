# Plan 22 — Revenue ingest (Plan 16 Phase 2)

**Status:** ✅ Done · **Date:** 2026-08-11

Tasks 22.1–22.3 shipped in PR #162. 22.4 is **parked by decision, not
unfinished** — D6 (the per-row `Date` column) and D8 (a live home-band
`zakat_avg_spend`) each carry their own unpark condition below, the same way
Plan 16 was marked Done with its Phase 2 parked.

One-line summary: the clinic software's fee columns have shipped, so ingest
them and light up the revenue surfaces Plan 16 Phase 1 already built and
gated behind `has_revenue`.

## Why now

[Plan 16](16-clinic-dashboard.md) built every revenue surface on the clinic
dashboard — a fourth KPI card, the "Revenue by service" table, the
side-column layout switch — and gated all of them on
`apps.pipeline.dashboard.has_revenue`, which is hardcoded `return False`.
D6 chose to gate on **data, not a runtime feature flag**, precisely so that
Phase 2 would need no template work. D13 recorded the one thing standing in
the way: the clinic software didn't emit fee columns yet.

**It does now.** Plan 16's Phase 2 trigger — "a daily patient export whose
header row shows fee columns" — is met, confirmed on 2026-08-11 against the
6 Aug 2026 export (read header-row-only, per the standing PHI caution).

## What actually changed in the export

The export is the same `Daily Activity Report` on the same `Patient Report`
sheet with the same banner rows. It now carries **34 columns, up from the 27
D13 recorded in July** — seven new ones:

| New column | Purpose |
|---|---|
| `Date` | per-row visit date (see D6 — deliberately not adopted) |
| `Registration Fee (PKR)` | service fee |
| `Consultation Fee (PKR)` | service fee |
| `Lab Fee (PKR)` | service fee |
| `Ultrasound Fee (PKR)` | service fee |
| `Pharmacy Fee (PKR)` | service fee |
| `Total Paid (PKR)` | per-row total (see D5 — a cross-check, not the source) |

The five fee columns map **exactly** onto the five services Plan 16's design
handoff carried as a placeholder list — Registration, Consultation, Pharmacy,
Laboratory, Ultrasound. D13's Q4 ("which services does the export really
carry?") is therefore answered with no design rework needed, and the
handoff's display order stands.

**Verified 2026-08-11:** the current parser accepts the 34-column file
unchanged (93 rows off the 6 Aug export, correct count) and silently drops
every fee cell — there is no revenue field anywhere in `ParsedVisitRow`,
`DeidentifiedVisit` or `DailyAggregate`. So today's uploads work fine and
throw the money away.

## Scope

### In scope

- Parse the five fee columns and carry them through to storage.
- Store revenue **per visit** (D2) and aggregate it per clinic-date.
- Backfill historical dates through the existing recompute command.
- Turn `has_revenue` into the real data check and supply the dashboard's
  `revenue_*` context keys.
- The daily report page's own Revenue section — Plan 16's work item 2, which
  Phase 1 explicitly deferred.
- Reconcile the per-service sum against `Total Paid (PKR)` and warn on drift
  (D5).

### Out of scope

- **Adopting the new per-row `Date` column** — D6.
- **Computing the home band's `zakat_avg_spend` live** — D8. Plan 16's Phase 2
  checklist lists it; it is parked here with an unpark condition rather than
  carried, because it is the highest-visibility surface in the project and
  the fee columns' first non-zero sample was fabricated.
- Expenditure, donations, or any funding source other than the daily patient
  export. D13's "the daily patient export is the only revenue source" stands.
- Any AI call. Nothing in this plan touches a model.

## Decisions

**D1 — The column names are confirmed, header-row-only.** Listed above,
matched case-insensitively via the existing `header_index` idiom, straight
apostrophes and the `(PKR)` suffix included. `header_index` degrades
harmlessly to `None`, so an export predating the software update still parses
with the fee fields left at zero — old and new exports both keep working,
which is what makes the backfill in 22.1 safe to run over July dates.

**D2 — Revenue is stored per visit on `DeidentifiedVisit`, not only on the
aggregate.** Plan 16's Phase 2 checklist left this open. It is not optional:
`DailyAggregate`'s own docstring calls it "a derived cache: always
recomputable from `DeidentifiedVisit` (the canonical store)", and the
`recompute_daily_aggregates` command is documented as safe to re-run. If
revenue lived only on the aggregate, that command would recompute every
historical date's revenue as **zero and wipe it** — turning a documented-safe
maintenance command into a destructive one. So the five fees become five
`PositiveIntegerField`s on `DeidentifiedVisit`.

This stays inside privacy invariant #1: a fee is a de-identified number, and
the invariant explicitly permits "a de-identified row table with direct
identifiers stripped". No new identifier is introduced.

**D3 — Three payment buckets, not two.** The `Status` column yields
`zakat` / `regular` / anything-else, and the existing model already treats
that third case as first-class (`unknown_payment_type_patients`). Revenue
mirrors it: `regular`, `zakat`, **and `unknown`**, with a service's `total`
being the sum of all three.

Bucketing unknown-status money into Regular would be an invention, and
dropping it would make published income silently understate reality. The
dashboard table shows Regular / Zakat / Total columns, so when unknown
revenue is non-zero the Total column correctly exceeds Regular + Zakat; a
conditional footnote line renders in exactly that case so the discrepancy
reads as recorded fact rather than an arithmetic bug. When unknown revenue is
zero — the normal day — nothing extra renders.

**D4 — `qty` is the count of non-zero fee cells.** Carried unchanged from
Plan 16 D14, which settled it with the maintainer: per service, `amount` is
the sum of that fee column over the date's rows and `qty` is the number of
rows where it is non-zero — services delivered, not patients. A service is
the line, not the item (one lab line can cover N tests). The display label
stays "quantity".

**D5 — `Total Paid (PKR)` is a reconciliation check, never the source.** The
per-service table is built from the five fee columns alone. `Total Paid` is
summed independently and compared against that sum per clinic-date; a
mismatch logs a **`WARNING`**, which the Plan 17 observability setup already
forwards to Sentry (`sentry_logs_level` is `WARNING` and above).

It deliberately does **not** fail the ingest. A blocked upload would be a
worse outcome than a flagged one — staff would simply be unable to file the
day — and the numbers remain deterministic either way. This check exists
because these columns have already emitted fabricated values once: the 6 Aug
camp export carried a flat `Registration Fee (PKR)` of 20 across all 93
attendees for an advertised-free camp, which the maintainer confirmed
(2026-08-10) was a bug in the clinic software's report.

**D6 — The new per-row `Date` column is deliberately not adopted.** The
parser keeps reading the date from the `Period:` banner and keeps raising
`ExportParseError` on a multi-day range. Adopting `Date` would unlock
multi-day exports, which sounds free and is not: the one-file-one-day
property is assumed downstream (report publishing, the per-date content hash,
`_ingest_one_date`), and unpicking it is a design change with its own
failure modes, unrelated to revenue.

*Unpark condition:* someone actually needs to upload a multi-day export. Then
it gets its own plan, not a rider on this one.

**D7 — The fee fields join `ParsedVisitRow._canonical_tuple()`, and the
resulting one-time re-classification is correct.** This exactly mirrors the
reasoning already recorded in that method for the Plan 11 B8/B9 free-text
fields, so it is followed rather than re-litigated: excluding the new fields
would mean a genuine re-upload correcting only a fee cell hashes identically
to the uncorrected version and is silently skipped as a duplicate, with
revenue never corrected. Including them means the first re-upload of an
already-ingested date reclassifies `STATUS_REPLACED` once and backfills its
revenue — which is the desired behaviour, since before this change the file
genuinely yielded no revenue to persist. Every subsequent re-upload hashes
identically again.

**D8 — The home band's `zakat_avg_spend` stays hand-typed.** Plan 16's Phase 2
checklist wanted it computed live. Not yet: the home page is the most-read
surface on the site, and the only non-zero sample these columns have ever
produced was fabricated (see D5). A wrong hand-typed figure is a content fix;
a wrong computed figure published automatically to the front page is an
incident.

*Unpark condition:* the maintainer confirms one known-good clinic day whose
fee columns reconcile against what was actually taken, and the D5 warning has
stayed quiet across a stretch of real uploads. Then it is a small change.

**D9 — No feature flag, reaffirming Plan 16 D6.** `has_revenue` becomes
`any(row.service_revenue for row in rows)`. Revenue appears on a date exactly
when that date has revenue data, and dates that predate the software update
keep rendering the three-card layout with no revenue table. This is why the
plan needs no rollout toggle: an export without fee columns is
indistinguishable from today.

**D10 — The daily report's split bar inverts the handoff's colours, on
purpose (2026-08-11, task 22.3).** The handoff specifies "Regular in
`--color-stat-value`, Zakat in `--color-text-faint`". `--color-stat-value`
resolves to `--color-brand`, so that puts **teal on Regular**. But the clinic
dashboard's funding split — already shipped, on the sibling page a reader
reaches from here — does the exact opposite: `--color-brand` for Zakat,
`--color-text-faint` for Regular.

Following the handoff literally would mean teal meaning "Zakat" on one page
and "Regular" on the next, which is a way to make someone misread real money.
Precedent over the handoff line here, and recorded rather than silently
diverged: **Zakat = `--color-brand`, Regular = `--color-text-faint`**,
matching `.dash__stack-seg--*`. A third `unknown` segment
(`--color-text-soft`) renders only when D3's unattributed money exists.

Worth a maintainer glance, since it is a deliberate departure from an
approved design file rather than a gap in it.

## Tasks

One task = one PR, each reviewed clean before the PR opens.

### 22.1 — Ingest the fee columns (no user-visible change)

- [ ] Five fee fields on `ParsedVisitRow` (defaulted, so `parser_clinic_v1`
      needs no change), added to `_canonical_tuple()` per D7.
- [ ] Extend `parser_tkc_daily_v1`'s column map with the six new headers,
      with an integer coercion helper (blank/non-numeric → 0, floats rounded
      — Excel hands back `20.0`, not `20`).
- [ ] Five `PositiveIntegerField`s on `DeidentifiedVisit` + migration (D2).
- [ ] `service_revenue` JSON field on `DailyAggregate` + migration, shaped
      per the handoff and D3.
- [ ] Populate it in `recompute_daily_aggregate`, splitting on the existing
      `Status`-derived `is_zakat_beneficiary`.
- [ ] The D5 reconciliation warning.
- [ ] Tests: parser reads the fees; continuation rows don't corrupt them;
      unknown-status money lands in its own bucket; recompute is
      reproducible; an export with no fee columns still parses to zeros.

`has_revenue` stays `False` through this task, so nothing on the site
changes and the PR can merge on its own.

### 22.2 — Light up the dashboard

- [ ] `has_revenue` becomes the real check (D9).
- [ ] Supply `revenue_rows`, `revenue_totals`, `revenue_total_amount`,
      `revenue_per_patient` from the range's aggregates.
- [ ] The unknown-bucket footnote (D3) and the partial-data line Plan 16's
      checklist asks for ("Revenue recorded for 12 of 22 reporting days.").
- [ ] Confirm the gated surfaces light up with **no template change** — the
      promise Plan 16 D6 made. Any template edit needed here beyond the two
      new lines above is a Phase 1 miss worth recording.

### 22.3 — Daily report page Revenue section ✅

Plan 16's work item 2, deferred out of Phase 1. Per-service Regular / Zakat /
Total with amount and quantity, a totals row and the split bar, mirroring the
dashboard table's markup and CSS rather than inventing a second idiom.

- [x] Section rendered between "Breakdown" and "Today's notes, summarised",
      omitted **whole** on a date with no revenue (the handoff's explicit
      rule: no heading, no empty table, no zero row).
- [x] Split bar with a third `unknown` segment when D3's unattributed money
      exists, and colours matching the dashboard's funding split rather than
      the handoff's inverted pair — see **D10**.
- [x] Verified on the real 6 Aug page in both themes.

### 22.4 — Parked

`zakat_avg_spend` computed live (D8), and the per-row `Date` column (D6).
Neither ships in this plan.

## Verification

Per the lifecycle's "verify by running the real thing": the 6 Aug export goes
through the **real upload view** in a running app, not a bespoke script, and
the dashboard is driven in a real browser in both themes. The fabricated PKR
20 values in that file make it a good functional fixture and a bad source of
truth — it exercises the path, and D5's warning should fire on it if the
`Total Paid` column disagrees.

Nothing in this plan is published to the live site as a figure until D8's
unpark condition is separately met.

### Result of the 22.1 run (2026-08-11)

The 6 Aug export went through the real upload view over a real logged-in
HTTP session against a running server. 93 rows ingested, and the aggregate
came back:

```
registration → unknown: {"qty": 93, "amount": 1860}
```

Two things this proved, one of them uncomfortable.

**D3 is not a hypothetical.** Every row in that export has a blank `Status`,
so all 93 patients — and all PKR 1,860 — landed in the `unknown` bucket. Under
a two-bucket Regular/Zakat design the entire day's revenue would have silently
vanished from the published figures with nothing indicating a loss.

**D5's check cannot catch a consistently fabricated value, and it didn't.**
The per-service columns sum to 1,860 and `Total Paid (PKR)` also sums to
1,860, so the reconciliation correctly stayed quiet: the export agrees with
itself. It is *internally consistent and externally wrong* — those PKR 20
registration fees are the fabricated ones the maintainer confirmed on
2026-08-10 for an advertised-free camp.

So D5 detects the export disagreeing with itself, not the export disagreeing
with reality. Nothing here weakens the check — a same-day cross-check is
worth having — but it does mean the dashboard will publish PKR 1,860 for
6 Aug once 22.2 lands, and no automated guard in this plan will object. That
is a **content** question for the maintainer (is the clinic-software fix
deployed, and should 6 Aug be re-uploaded once it is?), not a code defect,
and it is exactly why D8 keeps the home page's figure hand-typed.

## Release

No feature flag (D9), no migration ordering hazard (both migrations are
additive, with defaults, and touch no existing column). Ships on the normal
deploy gate.

**Post-deploy, once:** run `recompute_daily_aggregates` so historical dates
pick up their revenue — which will be zero for every date before the clinic
software update, correctly. Re-uploading a July export is not required and
would change nothing.

**Rollback:** revert the deploy. The added columns are additive and unread by
the previous release, so a rollback leaves them in place harmlessly rather
than needing a down-migration.
