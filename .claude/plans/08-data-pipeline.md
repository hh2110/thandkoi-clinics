# Plan 08 — Data Pipeline: Intake, Parser Registry, Aggregate-and-Discard, Daily Report

_Status: Drafted · Depends on: 01 Project foundation, 07 Accounts & roles · Next: 09 AI monthly newsletter_

## Goal

The core of the AI-native side of the project: an authenticated **Uploader**
hands the system a daily Excel export, the system **parses and aggregates it in
memory, then discards the raw file**, persists only de-identified data, and
surfaces the numbers on a **daily report page**. This is where CLAUDE.md's
privacy invariants stop being prose and become the actual shape of the code —
so most of this plan is about making "raw PHI is never persisted" a *structural*
property (you'd have to fight the design to violate it), not a rule someone has
to remember.

No AI in this plan. Numbers are computed deterministically in Python; the
report page renders those numbers. Plan 09 later wraps AI prose around them and
reads from the aggregate tables this plan defines — so a secondary goal here is
leaving Plan 09 a **clean, documented data interface** to read from.

## The privacy invariant, made structural

CLAUDE.md invariant #1 and
[architecture-and-ai-brief.md §4](../../docs/architecture-and-ai-brief.md) say
the raw export is parsed and aggregated **in memory during the request**, then
discarded — and that two things, and only two things, are persisted:
de-identified aggregates, **and** a **de-identified row-level table** with direct
identifiers stripped on the way in (this is a *decided* retention, per brief §8,
not an optional extra). The design has to make each of those true by
construction:

- **The raw bytes never touch disk.** Django's default upload handling spools
  any upload over ~2.5 MB to a **temporary file on disk** (`TemporaryUploadedFile`)
  — which would mean raw PHI transiently written to disk, violating the
  invariant even if we delete it after. So the upload view runs with an
  **in-memory-only upload handler** (`MemoryFileUploadHandler` only, no temp-file
  fallback) — a per-view `request.upload_handlers` override. The file exists only
  as a byte buffer for the life of the request.
- **The raw file is never saved to a model / MEDIA / object storage.** There is
  **no** `FileField`/`ImageField` for the export anywhere in the schema. It is
  read straight from the in-memory buffer into pandas; nothing writes it back
  out. `.gitignore` already blocks `*.xlsx`/`/uploads/`/`/data/` (Plan 01), but
  the real guarantee is that no code path *ever* calls `.save()` on the raw file.
- **Direct identifiers are dropped before anything is persisted.** Name,
  father's/husband's name, and address are stripped inside the parser, before the
  first `INSERT`. They are never written even transiently — the de-identified row
  table is built from a projection that excludes them, not by saving-then-deleting.
- **The AI boundary sits downstream of all of this.** The `ai` module (Plan 09)
  only ever reads the aggregate tables, so it is incapable of reaching raw data
  (brief §6, "the de-identification boundary sits upstream of the `ai` module").

Plan 02 already committed to writing privacy-guardrail **tests** for exactly
these properties (no file on disk after a request; no raw identifier in the DB;
numbers are deterministic). Plan 08 is the plan that gives those tests a real
subject — they move from placeholders to asserting against this code.

```
Uploader ──.xlsx──▶ upload view (Wagtail admin, can_upload_export)
                      │  in-memory upload handler — NO temp file on disk
                      ▼
              ┌──────────────── in-memory, single request ─────────────────┐
              │ ParserRegistry → pick parser (explicit choice / sniff)      │
              │   BaseExportParser.parse(buffer):                           │
              │     • pandas read from the byte buffer                      │
              │     • DROP name / father-husband / address (de-identify)    │
              │     • DOB → age band, then drop DOB                         │
              │     • return de-identified rows + computed aggregates       │
              │ RAW BUFFER GOES OUT OF SCOPE HERE ✗ (never .save()'d)       │
              └──────────────────────────┬─────────────────────────────────┘
                                         ▼ (one DB transaction)
                    PostgreSQL: DeidentifiedVisit rows
                                + DailyAggregate summary
                                + IngestRun audit row (hash, not data)
                                         │
                          ┌──────────────┴───────────────┐
                          ▼                               ▼
                 Daily report page               (Plan 09) ai module
                 (deterministic numbers)          reads aggregates only
```

## Scope

**In scope**
- **Intake**: a permission-gated upload view in the Wagtail admin (Uploader
  role from Plan 07), HTMX-driven, in-memory-only.
- **Parser registry**: a `BaseExportParser` contract + a `ParserRegistry`, and
  the **first concrete parser** for the clinic's current export format.
- **De-identification + aggregation**: strip identifiers, compute deterministic
  aggregates in pandas/Python.
- **Persistence**: the `DeidentifiedVisit` row table, the `DailyAggregate`
  summary table, and an `IngestRun` audit record — the documented read interface
  for Plan 09.
- **Daily report page**: a Wagtail page rendering the latest aggregates
  (numbers only; AI prose is Plan 09). Wires up Home's Report teaser, left
  waiting since Plan 04/06.

**Out of scope** (later plans / by decision)
- **Any AI** — drafting, narrative, translation → Plan 09/10. This plan computes
  and displays numbers; no Anthropic call anywhere in it.
- **Agentic schema inference / model-assisted onboarding of new export formats**
  — explicitly deferred by the
  [plans README "Out of scope"](README.md#out-of-scope-for-now) decision of
  2026-07-19: *"new formats get a hand-written parser."* This plan therefore
  designs a registry of **explicit, hand-written** parsers. It leaves a clean
  extension point (a new `BaseExportParser` subclass) so that if agentic
  onboarding is ever added, it produces a parser of the same shape — but it does
  **not** build any inference here.
- **The Uploader / Approver roles themselves** → Plan 07 (this plan consumes the
  `can_upload_export` permission it defined).
- **Monthly newsletter, "ask your data", funding exports** → Plans 09/11 (they
  read from this plan's aggregate tables).

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| App | A new `apps/pipeline` (Django app) | Keeps ingest/parsers/models/report together, upstream of any `ai` module — mirrors the brief's boundary. |
| Intake UI | A **custom Wagtail admin view** registered via `register_admin_urls` / a menu item, gated by `can_upload_export` (Plan 07), HTMX for the submit + result | Lives where the Uploader already logs in; no separate front-end. HTMX per the stack decision (brief §3). |
| Raw file handling | **In-memory upload handler only** for this view (`request.upload_handlers = [MemoryFileUploadHandler(...)]`); **no** `FileField` for the export anywhere | The structural enforcement of invariant #1 — the raw bytes cannot reach disk or MEDIA because nothing is capable of writing them there. |
| Parser selection | Uploader **picks the format** from a dropdown of registered parsers; each parser also exposes `sniff(workbook) -> bool` used to **confirm/auto-suggest** the choice | Explicit selection avoids silently mis-parsing a look-alike format; `sniff` guards against picking the wrong one. Not AI — a hand-written check of columns/sheet names. |
| Parser contract | `BaseExportParser` with `sniff()` and `parse(buffer) -> ParsedExport` (de-identified rows + aggregate dict); concrete parsers register into `ParserRegistry` by a format key | One parser per export format; adding a format = adding a subclass + registering it, **no change to pipeline core**. This is goal 3 (extensibility) done with explicit code. |
| De-identification | Drop **name, father's/husband's name, address** inside the parser before any persistence; derive **age band** from DOB then drop DOB | Direct identifiers never written even transiently (brief §4). Age *band* rather than exact age/DOB keeps the row table de-identified. |
| Persisted data | `DeidentifiedVisit` (row-level, de-identified) **+** `DailyAggregate` (summary) **+** `IngestRun` (audit: who/when/parser/row-count/**content hash**, no data) | Matches brief §4's "aggregates **and** a de-identified row-level table" (a decided retention). The row table exists so future report types / date-range questions don't need a new aggregate table each time. |
| Aggregate shape | `DailyAggregate`: one row per clinic-date, with **named integer columns** for the common metrics (total visits, by sex, new vs follow-up, Zakat vs paid) **+ a JSON field** for flexible category counts (by department, by diagnosis category) | Named columns give Plan 09 a stable, typed read interface; the JSON field absorbs new categories without a migration per category. This is the **interface Plan 09 reads** — see below. |
| Idempotency | `IngestRun` stores a **content hash** of the parsed input; re-uploading an already-ingested file is detected and **refused** (or explicitly replaces that date), never silently double-counted | The hash is a fingerprint, not the file — storing it is not storing PHI. Prevents a double-upload from doubling a day's numbers. |
| Daily report page | A Wagtail `DailyReportPage` (or a `ReportIndexPage` + children) whose **numbers render live from `DailyAggregate`**, deterministic; **published by an Approver** (Plan 07); the AI-narrative slot is left empty for Plan 09 | Keeps invariant #4 (a human publishes); keeps invariant #3 (numbers are Python-computed, not AI-invented). Whether it's one page per day vs. a rolling "latest" page is an open question. |
| Aggregates vs. pages | Aggregates persist **automatically** on every upload (they're deterministic data, not content needing review); only the **page** goes through Approver publish | Separates "compute the numbers" (no review needed — they're arithmetic) from "publish a public page" (human-reviewed). Avoids auto-publishing anything, which would breach invariant #4. |
| Excel libs | `openpyxl` for `.xlsx`, `xlrd` for legacy `.xls`, via pandas — already in the stack (brief §3) | Format detection by extension + `sniff()`. |

## The data model — and the interface it leaves Plan 09

Three tables, all PHI-free:

1. **`DeidentifiedVisit`** — one row per patient visit, direct identifiers
   removed. Candidate fields (subject to the real export, see open questions):
   `visit_date`, `department`/service, `age_band`, `sex`, `diagnosis_category`,
   `is_new_patient`, `is_zakat_beneficiary`, `ingest_run` (FK). **No** name,
   father's/husband's name, DOB, or address — by construction, not by deletion.
   Purpose (brief §4): answer future date-range / cross-tab questions without
   inventing a new aggregate table each time.
2. **`DailyAggregate`** — one row per clinic-date: named integer metrics
   (`total_visits`, counts by sex, new vs. follow-up, Zakat vs. paid) plus a
   `category_counts` JSON field (by department, by diagnosis category). This is
   the **read interface for Plan 09**: the brief's proposed tools
   (`get_month_stats`, `get_trend_vs_last_month`) become simple ORM reads /
   aggregations over this table — no re-parsing, no touching `DeidentifiedVisit`
   for the common case. Getting this shape right is the point of doing Plan 08
   before Plan 09.
3. **`IngestRun`** — audit: `uploaded_by`, `uploaded_at`, `parser_key`,
   `row_count`, `content_hash`, `status`. No patient data; supports idempotency
   and a "when was the last successful upload" health signal.

> **Recompute path.** Because the de-identified row table is retained, aggregate
> **definitions can change and be back-filled from `DeidentifiedVisit`** without
> re-uploading — which is the whole reason the brief keeps the row table. Confirm
> this is the intended contract (open question), since it shapes how much we lean
> on `DailyAggregate` being canonical vs. derived.

## Parser registry design

- **`BaseExportParser`** (abstract): `format_key`, `label`, `sniff(workbook) ->
  bool`, `parse(buffer) -> ParsedExport`. `ParsedExport` carries the
  de-identified rows and the computed aggregate payload.
- **`ParserRegistry`**: maps `format_key → parser`. Parsers self-register (e.g. a
  decorator or an app-ready hook). The upload view lists registered parsers in
  the dropdown; `sniff()` suggests/validates the choice.
- **First concrete parser**: the clinic's *current* medical-software export.
  Needs a real (de-identified) sample to write against — see open questions; this
  is the main external dependency for actually shipping the plan.
- **Extensibility without a release is deliberately *not* automated here.** The
  README defers agentic onboarding; this registry is the clean seam it would
  plug into later. For now, a new format is a code change (new subclass + test),
  which for a clinic that changes export format rarely is the right trade.

## Task checklist (code — this plan's PR)

1. **`apps/pipeline` scaffold** — app, registered upstream of any `ai` module.
2. **Models + migration** — `DeidentifiedVisit`, `DailyAggregate`, `IngestRun`,
   with the `can_upload_export` permission wired to whichever model owns it
   (coordinated with Plan 07).
3. **Parser registry** — `BaseExportParser`, `ParserRegistry`, `ParsedExport`.
4. **First concrete parser** — for the current export format (against a real
   de-identified sample), including the identifier-stripping and DOB→age-band
   de-identification and the deterministic aggregate computation.
5. **Upload view** — Wagtail admin view, `can_upload_export`-gated, **in-memory
   upload handler override**, HTMX submit; on success writes rows + aggregate +
   `IngestRun` in one transaction and returns a **summary only** (counts), never
   the parsed rows.
6. **Idempotency** — content-hash check against `IngestRun`.
7. **Daily report page** — `DailyReportPage` model + template rendering live
   `DailyAggregate` numbers; wire Home's Report teaser (the half Plan 04/06 left
   waiting).
8. **Privacy-guardrail tests** (the concrete subjects Plan 02 promised):
   - After an upload request, **no file exists on disk** and **no raw identifier
     column value** exists anywhere in the DB.
   - The de-identified row table contains **no** name/father-husband/address/DOB.
   - Aggregates equal a **byte-for-byte deterministic** recomputation from a
     fixture export (numbers come from Python, provable without any AI).
   - The upload view is **denied** to a user lacking `can_upload_export`.
   - Re-uploading the same fixture does not double-count.

## Acceptance criteria

- An Uploader (Plan 07) can upload a fixture `.xlsx` through the admin view and
  see a success summary of **counts only** — never patient rows.
- After that request: **zero** raw files on disk / in MEDIA / in object storage,
  and **zero** direct-identifier values in the database. (Automated test.)
- `DeidentifiedVisit`, `DailyAggregate`, and `IngestRun` are populated;
  aggregates match a deterministic Python recomputation exactly.
- The daily report page renders the latest aggregate numbers and is
  Approver-publishable; nothing in the pipeline auto-publishes a page.
- A user without `can_upload_export` is denied the upload view.
- Re-uploading the same file is detected and does not double-count.
- No AI/Anthropic call exists anywhere in this plan's code.
- `ruff check` and `pytest` (including the guardrail tests) pass in CI.

## Open questions for the maintainer

- **The current export's real shape** — column names, dtypes, sheet layout,
  `.xls` vs `.xlsx`. A **de-identified or synthetic sample** is needed to write
  the first parser against (the model may see column *shapes* per brief §6.1, but
  never real rows). This is the main thing blocking a shippable parser.
- **What the de-identified row table should keep** — age *band* vs. exact age;
  drop location entirely, or keep a coarse level (village / union council) that's
  useful for impact reporting without re-identifying; diagnosis as free text vs.
  a controlled category. Each choice trades analytical richness against
  re-identification risk.
- **Daily report granularity** — one **published page per day** (archivable,
  linkable, but many drafts to manage), a single **rolling "latest report"** page
  that always shows the newest aggregate, or **on-demand** generation? Affects the
  page model and how much the Approver has to click.
- **Aggregate contract** — is `DailyAggregate` canonical, or a **derived cache**
  recomputable from `DeidentifiedVisit` when metric definitions change? (The row
  table was retained precisely to allow the latter — confirm that's the intent.)
- **Re-upload behaviour** — a same-day corrected export: **refuse** the duplicate,
  or **replace** that date's rows/aggregate? Replacement needs a clear "supersede"
  rule so a correction updates rather than duplicates.
