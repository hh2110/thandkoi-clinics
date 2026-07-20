# Plan 08 — Data Pipeline: Intake, Parser Registry, Aggregate-and-Discard, Daily Report

_Status: Drafted · Depends on: 01 Project foundation, 07 Accounts & roles · Next: 09 AI monthly newsletter_

## Goal

The core of the AI-native side of the project: an authenticated user with the
`can_upload_export` permission (the single **Administrator** role from Plan 07)
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
Admin ──.xlsx──▶ upload view (Wagtail admin, can_upload_export)
                      │  in-memory upload handler — NO temp file on disk
                      ▼
              ┌──────────────── in-memory, single request ─────────────────┐
              │ ParserRegistry → pick parser (explicit choice / sniff)      │
              │   BaseExportParser.parse(buffer):                           │
              │     • pandas read from the byte buffer                      │
              │     • DROP name / father-husband / full address             │
              │     • DOB → age band; full address → coarse location        │
              │     • return de-identified rows + computed aggregates       │
              │ RAW BUFFER GOES OUT OF SCOPE HERE ✗ (never .save()'d)       │
              └──────────────────────────┬─────────────────────────────────┘
                                         ▼ (one DB transaction)
                    PostgreSQL: DeidentifiedVisit rows
                                + DailyAggregate summary (derived cache)
                                + IngestRun audit row (hash, not data)
                                         │
                          ┌──────────────┴───────────────┐
                          ▼                               ▼
             Daily report page (per date)        (Plan 09) ai module
             deterministic — auto-published       reads aggregates only
```

## Scope

**In scope**
- **Intake**: a permission-gated upload view in the Wagtail admin (the
  `can_upload_export` permission, held by the single Administrator role from Plan
  07), HTMX-driven, in-memory-only.
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
- **The roles/accounts themselves** → Plan 07 (this plan consumes the
  `can_upload_export` permission it defines; per PR #15 there is one Administrator
  role, no Uploader/Approver split).
- **Monthly newsletter, "ask your data", funding exports** → Plans 09/11 (they
  read from this plan's aggregate tables).

## Decisions (rows marked "Maintainer decision" confirmed on PR #15)

| Choice | Decision | Notes |
|---|---|---|
| App | A new `apps/pipeline` (Django app) | Keeps ingest/parsers/models/report together, upstream of any `ai` module — mirrors the brief's boundary. |
| Intake UI | A **custom Wagtail admin view** registered via `register_admin_urls` / a menu item, gated by `can_upload_export` (Plan 07), HTMX for the submit + result | Lives where the admin already logs in; no separate front-end. HTMX per the stack decision (brief §3). |
| Raw file handling | **In-memory upload handler only** for this view (`request.upload_handlers = [MemoryFileUploadHandler(...)]`); **no** `FileField` for the export anywhere | The structural enforcement of invariant #1 — the raw bytes cannot reach disk or MEDIA because nothing is capable of writing them there. |
| Parser selection | The uploading admin **picks the format** from a dropdown of registered parsers; each parser also exposes `sniff(workbook) -> bool` used to **confirm/auto-suggest** the choice | Explicit selection avoids silently mis-parsing a look-alike format; `sniff` guards against picking the wrong one. Not AI — a hand-written check of columns/sheet names. |
| Parser contract | `BaseExportParser` with `sniff()` and `parse(buffer) -> ParsedExport` (de-identified rows + aggregate dict); concrete parsers register into `ParserRegistry` by a format key | One parser per export format; adding a format = adding a subclass + registering it, **no change to pipeline core**. This is goal 3 (extensibility) done with explicit code. |
| De-identification | Drop **name, father's/husband's name, and full street address** inside the parser before any persistence; derive **age band** from DOB then drop DOB; **keep a coarse `location`** (village / union council), not the exact address; **classify free-text diagnosis into a fixed `diagnosis_category` via a parser-side mapping table**, never store the raw text | **Maintainer decision (PR #15): age bands, and keep location.** Age *band* rather than exact age/DOB, and a *coarse* location rather than a full address, keep the row table de-identified while preserving location for impact reporting. Direct identifiers never written even transiently (brief §4). **Diagnosis confirmed free text in the source clinic software** (maintainer, post-PR-15) — the parser owns a hand-written keyword/lookup mapping (e.g. `{"htn": "hypertension", "high bp": "hypertension", ...}`) into a small fixed category set, with an explicit **`other`/`unclassified`** bucket for anything unmapped. Raw diagnosis text is read only transiently during parsing and is never written to `DeidentifiedVisit` or anywhere else — it's a second application of invariant #1 (not just row-vs-aggregate, but free-text-vs-category within the row itself), and it's what makes `category_counts` aggregation actually work (free text doesn't group cleanly). The mapping table lives in code, reviewed like the rest of the parser — not user-editable at runtime, consistent with "hand-written parser per format, not agentic inference." |
| Persisted data | `DeidentifiedVisit` (row-level, de-identified) **+** `DailyAggregate` (summary) **+** `IngestRun` (audit: who/when/parser/row-count/**content hash**, no data) | Matches brief §4's "aggregates **and** a de-identified row-level table" (a decided retention). The row table exists so future report types / date-range questions don't need a new aggregate table each time. |
| Aggregate shape | `DailyAggregate`: one row per clinic-date, with **named integer columns** for the common metrics (total visits, by sex, new vs follow-up, Zakat vs paid) **+ a JSON field** for flexible category counts (by department, by diagnosis category) | Named columns give Plan 09 a stable, typed read interface; the JSON field absorbs new categories without a migration per category. This is the **interface Plan 09 reads** — see below. |
| Idempotency / re-upload | `IngestRun` stores a **content hash** of the parsed input; a re-upload for a date that already has data **replaces** (supersedes) that date's rows + aggregate in one transaction, never silently double-counting | **Maintainer decision (PR #15): replace.** A same-day corrected export supersedes the earlier one (delete-then-reinsert that date's `DeidentifiedVisit` + recompute its `DailyAggregate` atomically). The hash is a fingerprint, not the file — storing it is not storing PHI; here it identifies an exact-duplicate re-upload (a no-op) vs. a genuine correction (replace). |
| Daily report page | A Wagtail `DailyReportPage` under a `ReportIndexPage`, **one page per clinic-date** (archivable, linkable), whose **numbers render live from `DailyAggregate`** (deterministic), plus a **short AI-written summary sentence** generated from a fixed, targeted prompt over that same page's numbers | **Maintainer decision (PR #15): one published page per day, archivable, and auto-published straight to production — no draft step.** Extended by a follow-up maintainer decision (2026-07-19, CLAUDE.md invariant #4) to allow a short AI summary sentence on the same page to auto-publish too, under narrow conditions — see "The AI summary sentence" below. This is a deliberate, scoped exception to invariant #4, not a general allowance for AI content to skip review; Plan 09's newsletter narrative still requires draft/approve. |
| Aggregates & pages | Aggregates persist **automatically** on every upload; the deterministic daily page (numbers + summary sentence) is likewise **created and published automatically** for that date | Both the numbers and the summary sentence are auto-published for this one page type only, per the CLAUDE.md invariant #4 exception. Plan 09's newsletter narrative is unaffected — it stays a draft until an Administrator publishes it. |
| Excel libs | `openpyxl` for `.xlsx`, `xlrd` for legacy `.xls`, via pandas — already in the stack (brief §3) | Format detection by extension + `sniff()`. |

## The AI summary sentence — and why it's allowed to auto-publish

CLAUDE.md invariant #4 was amended (2026-07-19, maintainer decision) with one
narrow exception, scoped specifically to this page. The exception exists
*because* it's this narrow — it is not a precedent for AI content generally
skipping review:

- **Fixed template, not a free-form prompt.** The prompt is a single hardcoded
  template (e.g. `"In one sentence, summarize this clinic's day: {numbers}.
  State only these figures — do not add context, comparisons, or claims not
  present in the data."`) with the page's own `DailyAggregate` values
  interpolated in. The model is not asked to draft, opine, or contextualize —
  only to phrase the numbers it's handed, same discipline as invariant #3
  ("the AI writes prose only; it must never invent or restate statistics from
  memory" — here it restates statistics it's *given*, which is the allowed
  direction).
- **The payload is aggregates only.** Same guardrail as everywhere else in
  this codebase (invariant #2): the prompt payload is built from
  `DailyAggregate`'s named columns and JSON category counts — never from
  `DeidentifiedVisit` rows, and structurally incapable of containing anything
  row-level.
- **Never blocks the deterministic content.** If the Anthropic call fails,
  times out, or returns something that fails a basic sanity check (e.g.
  empty, or exceeds a length cap), the page **still auto-publishes with the
  numbers alone** and no summary sentence (or a static fallback line like "See
  the figures above."). The AI sentence is a nice-to-have layered on top of
  the numbers, never a dependency for shipping them.
- **Tested exactly like every other AI call (Plan 02's convention).** Mocked
  client in CI, real client never constructible in tests (the existing
  autouse guard in `conftest.py`), plus a guardrail test asserting the
  payload sent to the mock contains only that page's own aggregate values.
- **Scope is this one sentence, nothing else.** Plan 09's monthly newsletter
  narrative is unaffected by this exception and still requires a human
  Administrator to review and publish the draft.

## The data model — and the interface it leaves Plan 09

Three tables, all PHI-free:

1. **`DeidentifiedVisit`** — one row per patient visit, direct identifiers
   removed. Candidate fields (final field list still subject to the real export
   sample): `visit_date`, `department`/service, `age_band`, `sex`,
   `location` (**coarse** — village / union council, per the maintainer's PR #15
   decision to keep location; **not** the full address), `diagnosis_category`
   (a **fixed category**, mapped by the parser from the source system's free-text
   diagnosis field — the raw text itself is never stored, see the
   De-identification decision above), `is_new_patient`, `is_zakat_beneficiary`,
   `ingest_run` (FK). **No** name, father's/husband's name, DOB, full street
   address, or raw diagnosis text — by construction, not by deletion. Keeping
   location only at the village / union-council level preserves impact reporting
   without re-identifying individuals. Purpose (brief §4): answer future
   date-range / cross-tab questions without inventing a new aggregate table each
   time.
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

> **Recompute path (confirmed contract, PR #15).** `DeidentifiedVisit` is the
> **canonical** store; `DailyAggregate` is a **derived cache** recomputable from
> it. The maintainer confirmed "the latter" — so when a metric definition changes,
> aggregates are **back-filled from `DeidentifiedVisit`** without re-uploading,
> which is the whole reason the brief keeps the row table. Practically:
> `DailyAggregate` is treated as rebuildable at any time (a management command can
> drop and recompute it from the row table), and Plan 09 reads it as a convenience
> layer, not a source of truth.

## Parser registry design

- **`BaseExportParser`** (abstract): `format_key`, `label`, `sniff(workbook) ->
  bool`, `parse(buffer) -> ParsedExport`. `ParsedExport` carries the
  de-identified rows and the computed aggregate payload.
- **`ParserRegistry`**: maps `format_key → parser`. Parsers self-register (e.g. a
  decorator or an app-ready hook). The upload view lists registered parsers in
  the dropdown; `sniff()` suggests/validates the choice.
- **First concrete parser**: the clinic's *current* medical-software export.
  Needs a real (de-identified) sample to write against. The maintainer confirmed
  (PR #15) this sample **can be provided before the Plan 08 feature is built**, so
  it is a sequencing dependency, not a blocker — the parser is written once the
  de-identified/synthetic sample lands.
- **Extensibility without a release is deliberately *not* automated here.** The
  README defers agentic onboarding; this registry is the clean seam it would
  plug into later. For now, a new format is a code change (new subclass + test),
  which for a clinic that changes export format rarely is the right trade.

## Feature flag

**No flag** — consistent with the rest of the roadmap: this is a **brand-new,
pre-launch repo**, so there are no existing users a partial slice could reach and
nothing in production a runtime toggle would protect. That said, Plan 08 is the
**highest-risk surface in the project** — it ingests raw PHI and its daily report
page auto-publishes — so the safety a flag might provide is supplied instead by
mechanisms that don't need one:

- The `can_upload_export` permission (Plan 07) limits *who* can ingest to the
  three Administrators.
- The **phased release** (below) proves the first parser against synthetic data
  on **staging** before any real export flows — the parser is verified, not
  toggled.
- Rollback is a **PR revert / permission removal / unpublish / purge-and-
  recompute** (see Release plan), not a flag flip — and because raw PHI is never
  persisted, there is no raw data to clean up.

If the site is already live by the time this ships and a runtime kill switch
becomes worth it, adding one is a deliberate decision to make *then*, not a
default this greenfield plan assumes.

## Precedent map

New-repo note: the load-bearing privacy mechanisms (in-memory upload handler,
parser registry, de-identification) are **new to the repo and the riskiest
part** — every one is grounded against an authoritative reference or a maintainer
decision, never invented. Wiring and page patterns reuse merged plans.

| Element | Precedent to mirror | Where |
|---|---|---|
| `apps/pipeline` app scaffold | Plan 01's app/settings structure | Plan 01 (in repo) |
| pandas + openpyxl/xlrd parsing | Stack decision (brief §3) — already chosen | architecture brief |
| Custom Wagtail admin view (`register_admin_urls`, menu item) + HTMX | Wagtail admin-hooks idiom + the HTMX stack decision | Wagtail docs + brief §3 |
| `can_upload_export`-gated view | Plan 07's permission | Plan 07 (in repo) |
| `ReportIndexPage` + per-date `DailyReportPage` | Plan 06's index + child-page archive pattern | Plan 06 (in repo) |
| Home Report-teaser wiring (the half left waiting) | Plan 04/06's conditional teaser | Plans 04/06 (in repo) |
| AI summary-sentence call (mocked in CI, autouse guard, aggregates-only payload) | **Plan 02's AI-call test convention** — first real use | Plan 02 (in repo) + Anthropic SDK docs |
| Privacy-guardrail tests (no file on disk, no identifier in DB, deterministic numbers) | **Plan 02's promised guardrail tests** — placeholders become real here | Plan 02 (in repo) |
| **In-memory-only upload handler** (`MemoryFileUploadHandler`, no temp-file fallback) | **No precedent — load-bearing privacy mechanism** — ground against Django's upload-handler docs; this is what makes invariant #1 structural | Django docs (best practice) |
| **Parser registry / `BaseExportParser` contract** | **No precedent** — ground against the abstract-base + registry pattern described in brief §6; hand-written parsers only (agentic inference deferred) | architecture brief + best practice |
| **De-identification rules** (age bands, coarse location, free-text-diagnosis → fixed category, drop identifiers pre-persist) | **No precedent** — grounded in maintainer decisions (PR #15 / post-PR-15) + brief §4, not invented | maintainer decisions + brief |

## Task checklist (code — this plan's PR)

1. **`apps/pipeline` scaffold** — app, registered upstream of any `ai` module.
2. **Models + migration** — `DeidentifiedVisit`, `DailyAggregate`, `IngestRun`,
   with the `can_upload_export` permission wired to whichever model owns it
   (coordinated with Plan 07).
3. **Parser registry** — `BaseExportParser`, `ParserRegistry`, `ParsedExport`.
4. **First concrete parser** — for the current export format (against a real
   de-identified sample), including the identifier-stripping, DOB→age-band
   de-identification, the free-text-diagnosis→`diagnosis_category` mapping
   table (with an `other`/`unclassified` fallback), and the deterministic
   aggregate computation.
5. **Upload view** — Wagtail admin view, `can_upload_export`-gated, **in-memory
   upload handler override**, HTMX submit; on success writes rows + aggregate +
   `IngestRun` in one transaction and returns a **summary only** (counts), never
   the parsed rows.
6. **Idempotency / replace** — content-hash check against `IngestRun`; an
   exact-duplicate re-upload is a no-op, a genuine re-upload for an existing date
   **replaces** that date's rows + aggregate atomically (supersede rule).
7. **Daily report page** — `ReportIndexPage` + one `DailyReportPage` **per date**
   rendering live `DailyAggregate` numbers, **auto-created and auto-published** for
   that date (no draft, since the parser is committed & reviewed); pages are
   archivable/linkable. Wire Home's Report teaser (the half Plan 04/06 left
   waiting).
8. **AI summary sentence** — a fixed-template Anthropic call (aggregates-only
   payload) that generates the page's one-sentence summary at the same time the
   aggregate is computed; a failure/timeout/sanity-check falls back to
   publishing the numbers with no sentence (or a static fallback line) rather
   than blocking — see "The AI summary sentence" above.
9. **Aggregate recompute command** — a management command that rebuilds
   `DailyAggregate` from `DeidentifiedVisit` (the derived-cache contract), so metric
   definitions can change without re-uploading.
10. **Privacy-guardrail tests** (the concrete subjects Plan 02 promised):
   - After an upload request, **no file exists on disk** and **no raw identifier
     column value** exists anywhere in the DB.
   - The de-identified row table contains **no** name/father-husband/full-address/DOB,
     **and no raw diagnosis text** — only a `diagnosis_category` value from the
     fixed set the mapping table can produce (a coarse `location` is allowed and
     expected).
   - Aggregates equal a **byte-for-byte deterministic** recomputation from a
     fixture export (numbers come from Python, provable without any AI).
   - The AI summary sentence's prompt payload (captured via the mocked client)
     contains only that page's own `DailyAggregate` values — no row-level data,
     no other date's data.
   - A published daily report page still contains its numbers even when the
     mocked AI client is made to raise/time out (the fallback path).
   - The upload view is **denied** to a user lacking `can_upload_export`.
   - Re-uploading the same fixture does not double-count; a corrected re-upload for
     the same date **replaces** rather than appends.

## Acceptance criteria

- An Administrator (Plan 07) can upload a fixture `.xlsx` through the admin view
  and see a success summary of **counts only** — never patient rows.
- After that request: **zero** raw files on disk / in MEDIA / in object storage,
  and **zero** direct-identifier values in the database. (Automated test.)
- `DeidentifiedVisit`, `DailyAggregate`, and `IngestRun` are populated;
  aggregates match a deterministic Python recomputation exactly.
- The daily report page for that date renders its aggregate numbers and is
  **auto-published to production** (no draft) — the numbers are deterministic
  (invariant #3), and the one AI-written summary sentence on the page is
  covered by the narrow, explicit CLAUDE.md invariant #4 exception (2026-07-19)
  — fixed-template prompt, aggregates-only payload, never blocks the numbers on
  failure. **No other AI content auto-publishes anywhere in this plan** — this
  exception is scoped to exactly this one sentence.
- The AI summary sentence's prompt payload, captured in a guardrail test,
  contains only that page's own aggregate values.
- A published daily report page still ships its numbers when the mocked AI
  client raises or times out (fallback path exercised in tests).
- `DailyAggregate` can be dropped and rebuilt from `DeidentifiedVisit` and matches
  the original (derived-cache contract).
- A user without `can_upload_export` is denied the upload view.
- Re-uploading the same file is detected as a no-op; a corrected re-upload for the
  same date **replaces** that date's data rather than double-counting.
- The **only** Anthropic call in this plan's code is the daily-summary-sentence
  generation described above; it is always mocked in tests (Plan 02's
  convention — no real API call anywhere in the suite).
- `ruff check` and `pytest` (including the guardrail tests) pass in CI.

## Resolved questions (answered by the maintainer on PR #15)

- **The current export's real shape** (column names, dtypes, sheet layout, `.xls`
  vs `.xlsx`) → a **de-identified or synthetic sample can be provided before Plan
  08 is built**. Sequencing dependency, not a design blocker; the first parser is
  written against that sample when it lands (the model may see column *shapes* per
  brief §6.1, never real rows).
- **What the de-identified row table keeps** → **age bands** (not exact age/DOB)
  and **keep location at a coarse level** (village / union council, not full
  address). **Diagnosis representation** → confirmed **free text in the source
  clinic software** (maintainer, post-PR-15); the parser maps it to a fixed
  `diagnosis_category` via a hand-written keyword/lookup table with an
  `other`/`unclassified` fallback, and never persists the raw text — see the
  De-identification decision above.
- **Daily report granularity** → **one published page per date**, archivable, and
  **auto-published straight to production without a draft** for pages produced by a
  committed, code-reviewed parser (see the invariant-#4 note in the decisions
  table and Plan 07's "How invariant #4 is enforced").
- **Aggregate contract** → `DailyAggregate` is a **derived cache** recomputable
  from the canonical `DeidentifiedVisit` row table ("the latter").
- **Re-upload behaviour** → **replace**: a same-day corrected export supersedes the
  prior one for that date (atomic delete-and-reinsert + recompute).

## Release plan

This plan handles PHI and auto-publishes to production, so it ships in **explicit
phases across environments** — no runtime flag (see Feature flag), but the hard
gate stands: **prove no PHI persists, using synthetic/de-identified data on
staging, before a single real export touches production.**

- **Phase 0 — merge, models only.** Merge → migrations → deploy. The upload view
  is live but reachable only by holders of `can_upload_export` (the three
  Administrators); nothing else changes for anyone.
- **Phase 1 — staging, synthetic data (the privacy gate).** On **staging**,
  upload the de-identified/synthetic sample and verify, as automated tests plus a
  manual check: **no raw file on disk / in MEDIA** after the request; **zero
  direct-identifier values** anywhere in the DB; no raw diagnosis text (only
  mapped categories); aggregates equal a deterministic Python recompute; the AI
  summary payload contains **only that page's aggregates**; the fallback
  publishes numbers when the AI client is forced to fail; a
  non-`can_upload_export` user is denied. **Success criterion: every guardrail
  green on staging with synthetic data.** No real data yet.
- **Phase 2 — production, first real upload by the maintainer alone.** Only after
  Phase 1 passes, the **maintainer** does the first real export upload on
  production personally and confirms the same guarantees hold against prod
  (success summary shows counts only; the daily page auto-publishes numbers
  correctly). Success criterion: one clean real ingest with no PHI persisted.
- **Phase 3 — routine use.** The other Administrators begin daily uploads.
- **Who gets access:** the three Administrators (`can_upload_export`, Plan 07)
  for *uploading*; the **public** for the auto-published daily report pages
  (numbers + the one AI sentence).
- **Who's informed:** the three Administrators — brief them specifically on the
  PHI discipline (raw exports are never committed and never persisted; only
  de-identified aggregates and rows survive a request) before Phase 3, not after.
- **Rollback trigger:** **revert the PR** (removes the upload view and daily
  auto-publish) or **remove `can_upload_export`** from the Administrator group —
  either takes the surface down without a runtime flag. Because raw PHI is never
  persisted, there is **no raw data to clean up**; if a de-identification defect
  is found, the affected `DeidentifiedVisit`/`DailyAggregate`/report pages are
  purged and rebuilt via the recompute command after the fix. Any concern about a
  published daily page → unpublish in the admin immediately.
