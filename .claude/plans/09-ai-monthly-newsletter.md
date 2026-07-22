# Plan 09 — AI Monthly Newsletter

_Status: In progress (code merged — PR #41; release phases pending, see "Release plan") · Depends on: 06 Newsletters, Camp Reports & Gallery; 07 Accounts & roles; 08 Data pipeline · Next: (none — roadmap ends at 09; see README's "Out of scope")_

## Goal

The first real use of the Anthropic SDK for **content drafting**: once a month,
assemble that month's `DailyAggregate` figures, the admin's notes, and any
photos into a single prompt-with-tools call to Claude, and land the result as
a **Wagtail draft** — a new `NewsletterPage` revision under the
`NewsletterIndexPage` Plan 06 already built — for an Administrator (Plan 07)
to review and publish.

This plan is deliberately the "one-shot prompt with tooling" shape described
in [architecture-and-ai-brief.md §6.2](../../docs/architecture-and-ai-brief.md):
the model receives the month's numbers plus context and calls small,
read-only tools to look up specifics rather than being handed one giant
pre-formatted blob. It is also the plan that puts CLAUDE.md invariant #4's
**general rule** into practice for the first time — Plan 08's daily summary
sentence is a narrow, explicit exception to that rule (a fixed template
restating numbers already on the page); this plan is full free-form narrative
drafting, so it gets the actual human-in-the-loop gate, no exception.

No new model. Plan 06's own doc says this outright: "Plan 09 later drafts
*into* the Newsletter model this plan creates, via `save_revision()` ... not a
new model." This plan produces an unpublished `NewsletterPage` revision; it
never writes anything an Administrator hasn't seen.

## Scope

**In scope**
- A **monthly rollup** computed from `DailyAggregate` (Plan 08's read
  interface) — never a re-parse of raw exports, never a read of
  `DeidentifiedVisit` directly for the common case (see "Data interface"
  below).
- An **admin-notes and photos input mechanism** feeding the prompt: notes are
  a file the admin prepares outside the platform and uploads; photos are
  either picked from the existing Plan 06 gallery or uploaded directly
  (confirmed by the maintainer on PR #17 — see "Resolved questions" below).
- The **tool functions** the model calls during drafting: `get_month_stats`,
  `get_trend_vs_last_month`, `get_previous_newsletter` (brief §6.2), all
  read-only over aggregates/published content.
- The **draft-creation flow**: an Anthropic call producing newsletter body
  content, written into a new `NewsletterPage` instance under
  `NewsletterIndexPage` via `save_revision()` — unpublished, exactly like a
  human editor's draft.
- **Review/publish flow**: an Administrator opens the draft in the Wagtail
  admin, edits if needed, and publishes it — no code-path in this plan holds
  publish permission (per Plan 07's "AI/automation code holds no publish
  permission").
- **Failure handling**: what happens when the Anthropic call fails, times
  out, or returns something unusable — see "Failure handling" below.
- The **deterministic-numbers guardrail test** for this plan's prompt/tool
  payloads, matching Plan 08's pattern.

**Out of scope** (later, or by decision)
- **Any new model, field, or index page for newsletters** — Plan 06 already
  built `NewsletterIndexPage`/`NewsletterPage`; this plan drafts into them.
- **Urdu/Pashto translation** of the drafted newsletter — out of scope for
  this plan (see the roadmap's "Out of scope" section in
  [`.claude/plans/README.md`](README.md)). English-only here.
- **Auto-publish of any kind.** Unlike Plan 08's one narrow, explicitly-scoped
  exception (a fixed-template sentence restating a single page's own
  numbers), this plan's newsletter narrative is full free-form drafting and
  gets the general invariant-#4 rule: draft → human review → publish, every
  time, no exceptions. CLAUDE.md says this explicitly: *"This exception
  covers only that one summary sentence. It does not extend to Plan 09's
  monthly newsletter narrative or any other AI-authored content, which still
  requires human review and approval before publishing."*
- **Camp Report or Gallery drafting** — this plan is newsletters only; camp
  reports remain human-authored per Plan 06.
- **The public site assistant / "ask your data" chat** — architecture brief
  §6.3, deferred (see README's "Out of scope").
- **Agentic schema inference / new export formats** — Plan 08's territory,
  already deferred.

## The invariant-#4 boundary — Plan 08's exception does not apply here

CLAUDE.md invariant #4 states the general rule ("every AI-generated page is a
draft that a person reviews and approves before it is published") and then
carves out **one narrow exception** for Plan 08's daily summary sentence,
under three conditions that are all specific to that one sentence (fixed
template, aggregates-only payload, never blocks the deterministic numbers on
failure). The same paragraph names this plan directly to rule it out:

> "This exception covers *only* that one summary sentence. It does not extend
> to Plan 09's monthly newsletter narrative or any other AI-authored content
> ... Widening this exception is a decision to make deliberately again, not
> something a future plan should assume by analogy."

So Plan 09 is built to the **general** rule, not the exception:
- The model drafts free-form narrative (not a single fixed-template
  sentence) — it has latitude in phrasing, structure, and emphasis, which is
  exactly the kind of output invariant #4 exists to gate.
- The Anthropic call in this plan never has publish permission (Plan 07);
  `save_revision()` is the only write path available to it.
- If the call fails, times out, or the maintainer never runs the monthly
  job, the correct behavior is **no draft is created** — never a fallback
  publish. This is the opposite failure mode from Plan 08's daily page,
  where the numbers must ship regardless of the AI call's outcome. Here
  there is no deterministic content riding alongside the AI prose that needs
  to ship unconditionally; a newsletter that doesn't exist yet is not a
  regression the way an unpublished daily report would be.

## Data interface consumed (from Plan 08)

This plan is a **reader**, not a re-implementer, of Plan 08's data model:

- **`DailyAggregate`** is the primary read interface. A monthly rollup is an
  aggregation *over* `DailyAggregate` rows for the target month (sum/average
  the named integer columns, merge the `category_counts` JSON across the
  month) — not a re-parse of any export and not, for the common case, a
  direct read of `DeidentifiedVisit`. This mirrors Plan 08's own framing:
  *"the brief's proposed tools (`get_month_stats`, `get_trend_vs_last_month`)
  become simple ORM reads / aggregations over this table."*
- **`DeidentifiedVisit` is out of reach for this plan's tools by design.**
  Per CLAUDE.md invariant #2 and the brief's "de-identification boundary
  sits upstream of the `ai` module," nothing in this plan's tool layer
  queries `DeidentifiedVisit`. If a future need ever required row-level
  cross-tabs for the newsletter, that would be a new, explicitly-scoped tool
  decision — not something this plan assumes.
- **`get_previous_newsletter`** reads the most recently *published*
  `NewsletterPage` (Plan 06's model) for voice/style consistency — published
  content only, matching the public-site-assistant principle (brief §6.3) of
  only grounding on what's actually public, even though this tool's use is
  internal rather than public-facing.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Prompt shape | "One-shot prompt with tooling" per brief §6.2 — a single system/user prompt describing the drafting task, with the model calling read-only tools (`get_month_stats`, `get_trend_vs_last_month`, `get_previous_newsletter`) to pull specifics rather than one pre-flattened context blob | Matches the brief's own description verbatim; lets the model ask for exactly the comparisons it needs rather than the app guessing what to include up front. |
| Model | `claude-sonnet-5` (updated 2026-07-22 — see below) | Originally proposed as `claude-opus-4-8` per brief §6's model-selection table. Maintainer decision (2026-07-22, Plan 11 C4): switch newsletter/report drafting to Sonnet 5, keep Haiku for the Plan 08 daily summary sentence. `docs/architecture-and-ai-brief.md`'s model table was updated to match. |
| Numbers guardrail | Every figure available to the model comes from a Python-computed tool result (`get_month_stats` / `get_trend_vs_last_month`), never typed into the prompt as prose by a human and never left for the model to compute or recall | Same discipline as invariant #3 and Plan 08's guardrail — "the AI writes prose only; it must never invent or restate statistics from memory." Testable the same way: a guardrail test asserts every numeric tool-call result traces back to a `DailyAggregate` query, and a fixture-based test asserts the model is never the source of a number that ends up in a published page. |
| Landing point | A new `NewsletterPage` instance under the existing `NewsletterIndexPage` (Plan 06), created via `save_revision()` — unpublished | Plan 06's doc states this exact mechanism as the intended integration point; no new model, no new page type. |
| Publish permission | The drafting code path holds **no** publish permission (Plan 07's "AI/automation code holds no publish permission") | Structural enforcement of invariant #4's general rule, same mechanism Plan 07 already built for any AI-authored page. |
| Failure handling | If the Anthropic call fails, times out, or the output fails a basic sanity check, **no draft is created** for that month — this is a "try again" / "run again later" situation, not a fallback publish | The opposite of Plan 08's daily page, which must ship its numbers regardless. Here, nothing else on the page depends on the AI call succeeding, so there is nothing to protect by publishing a partial or fallback newsletter. |
| Testing | Anthropic client mocked in CI via the existing autouse `conftest.py` guard (Plan 02) — real client never constructible in tests; a guardrail test captures the mocked client's tool-call payloads and asserts they contain only real `DailyAggregate`-derived numbers | Zero real API calls in the suite, exactly like every other AI call in this codebase (Plan 02's convention, reused unchanged by Plan 08 and now this plan). |
| Bilingual scope | English only in this plan | Urdu/Pashto translation of newsletters (and other content) is out of scope for the current roadmap — see [`.claude/plans/README.md`](README.md)'s "Out of scope" section. Not scope-creeping into that here. |
| Monthly trigger mechanism | A management command run **manually** by an Administrator at month-end — no scheduled/cron job | **Maintainer decision (PR #17).** Drafting is an explicit, human-initiated action, not something that runs unattended. |
| Admin-notes input | A **file the admin prepares outside the platform and uploads** through the admin — not a live text field filled in in-app | **Maintainer decision (PR #17).** Exact file format/parsing is an implementation detail for the eventual build PR (e.g. plain text/Markdown is the simplest fit); the structural decision is "upload a file", not "type into a form". |
| Photo input | **Both**: the admin can pick from the existing Plan 06 gallery **or** upload new images directly for the newsletter | **Maintainer decision (PR #17).** Broader than the originally proposed "gallery-only" default — direct upload covers photos that aren't (yet) in the consent-gated gallery; any directly-uploaded photo still needs `consent_confirmed` per Plan 06's convention before it can appear in a published page. |
| "The month" | Calendar month | **Maintainer decision (PR #17).** Confirms the doc's original assumption — no clinic-specific reporting period. |
| Failure visibility | **No active notification** (no email/alert) — but a failed run must be visible somewhere in the admin console (e.g. an audit/log record an Administrator can check) | **Maintainer decision (PR #17).** Passive visibility, not push notification — mirrors Plan 08's `IngestRun` audit-row pattern (status visible on inspection, nothing emailed). |
| `get_previous_newsletter` scope | Just the immediately previous issue | **Maintainer decision (PR #17).** Confirms the doc's original proposal — no need for a last-N window. |

## Resolved questions (answered by the maintainer on PR #17)

- **Monthly trigger mechanism** → manual management command run by an
  Administrator; no scheduled job.
- **Admin-notes input** → a file the admin creates outside the platform and
  uploads through the admin, rather than a live in-app text field.
- **Photo input** → both: pick from the existing Plan 06 gallery, or upload
  new images directly for the newsletter (still consent-gated per Plan 06 if
  they're to appear in a published page).
- **What counts as "the month"** → calendar month.
- **Retry/notification on failure** → no active notification; a failed run
  must be visible to an Administrator somewhere in the admin console (an
  audit/log record, not an email/alert).
- **`get_previous_newsletter` scope** → just the immediately previous issue.

## Feature flag

**No flag** — deliberate, and here the gates are stronger than a flag would be:
this is a **management command an Administrator chooses to run** (no scheduled/
unattended job), and it **only ever creates an unpublished draft** (no publish
permission, per Plan 07). "Don't run the command" is a more absolute off-switch
than a flag, and the human review-before-publish step means nothing reaches the
public without a person's action. The one external dependency — the live
Anthropic call — is already neutralised in tests by Plan 02's autouse mock
(a real client is never constructible in CI). So a flag would gate nothing the
manual trigger and the draft-only boundary don't already gate.

## Precedent map

New-repo note: by Plan 09 almost everything has in-repo precedent — this plan is
a **reader and composer** of Plans 06/07/08, not a new subsystem. Only the
prompt/tooling shape grounds against an external reference.

| Element | Precedent to mirror | Where |
|---|---|---|
| `ai` module (extend Plan 08's, don't fork) | Plan 08's `ai` module for its summary sentence | Plan 08 (in repo) |
| Anthropic call: mocked in CI, autouse guard, aggregates-only | Plan 02's AI-call convention + Plan 08's summary call | Plans 02/08 (in repo) |
| Read-only tools over `DailyAggregate` | Plan 08's documented `DailyAggregate` read interface | Plan 08 (in repo) |
| Monthly rollup (aggregate over `DailyAggregate`) | Plan 08's aggregate shape (named columns + category JSON) | Plan 08 (in repo) |
| Draft via `save_revision()` into `NewsletterPage` | Plan 06's `NewsletterPage` + draft-visibility mechanism | Plan 06 (in repo) |
| No-publish-permission boundary | Plan 07's "automation holds no publish permission" | Plan 07 (in repo) |
| Failure → passive, admin-visible audit record (no email/alert) | Plan 08's `IngestRun` audit-row pattern | Plan 08 (in repo) |
| Photo picker from gallery / direct upload (consent-gated) | Plan 06's `GalleryImage` + `consent_confirmed` | Plan 06 (in repo) |
| Numbers-guardrail test (every figure traces to `DailyAggregate`) | Plan 08's guardrail-test shape | Plan 08 (in repo) |
| **One-shot prompt-with-tooling shape** | **No in-repo precedent for tool-use** — ground against brief §6.2 + Anthropic SDK tool-use docs | architecture brief + SDK docs |
| **Admin-notes file upload** (prepared outside the platform) | **No precedent** — simplest fit (plain text/Markdown) via standard Django file handling; format is a build-PR detail | Django docs (best practice) |

## Task checklist (code — this plan's eventual implementation PR)

1. **`ai` module scaffold** (or extend one if Plan 08 already started one for
   its summary sentence) — wraps the Anthropic Python SDK, houses tool
   functions, kept upstream-clean of `DeidentifiedVisit` per the
   de-identification boundary.
2. **Monthly rollup** — a function/queryset aggregating `DailyAggregate` rows
   for a target month into the shape `get_month_stats` and
   `get_trend_vs_last_month` need (this month's totals/category counts, and
   a comparison against the prior month).
3. **Tool functions** — `get_month_stats(month)`, `get_trend_vs_last_month(month)`,
   `get_previous_newsletter()`, each a thin, typed, read-only wrapper with
   its own unit test independent of any AI call.
4. **Admin-notes and photo input** — a file-upload field for the admin's
   monthly notes (prepared outside the platform), plus a photo-selection step
   that supports both picking existing Plan 06 `GalleryImage`s and uploading
   new images directly (consent-gated, per Plan 06's convention).
5. **Drafting call** — the one-shot prompt-with-tooling Anthropic call
   (`claude-sonnet-5`, updated 2026-07-22 from the originally proposed
   `claude-opus-4-8` — see the decision table above), assembling the month's
   data, notes, and photos, and producing newsletter body content.
6. **Draft-landing** — write the model's output into a new `NewsletterPage`
   under `NewsletterIndexPage` via `save_revision()`; no publish call
   anywhere in this code path (Plan 07 permission boundary).
7. **Failure handling** — no draft on failure/timeout/sanity-check rejection;
   log the failure to an admin-visible record (no email/alert — an
   Administrator checks the admin console, mirroring Plan 08's `IngestRun`
   audit-row pattern).
8. **Trigger mechanism** — a management command, run manually by an
   Administrator at month-end (no scheduled job), that runs the monthly
   rollup + drafting call.
9. **Deterministic-numbers guardrail test** — mocked-client test asserting
   every numeric value in the tool-call payloads and in the resulting draft
   traces back to a real `DailyAggregate`-derived computation, never a
   model-invented figure (same discipline and same test shape as Plan 08's
   guardrail test for its summary sentence).
10. **Draft-visibility test** — the drafted `NewsletterPage` revision does
    not appear in the public archive or Home's teaser until an Administrator
    publishes it (reusing the draft-visibility mechanism Plan 06 already
    tested).
11. **Permission test** — the drafting code path cannot publish; only a user
    with publish permission (Administrator) can turn the draft into a
    published page.

## Acceptance criteria

- Running the monthly drafting flow for a month with existing
  `DailyAggregate` data produces an **unpublished** `NewsletterPage` revision
  under `NewsletterIndexPage`, visible to Administrators in the Wagtail admin
  and nowhere else.
- Every figure that appears in the draft is traceable, in a guardrail test,
  to a real `DailyAggregate`-derived computation — never a number the model
  supplied from its own generation.
- The tool functions (`get_month_stats`, `get_trend_vs_last_month`,
  `get_previous_newsletter`) never query `DeidentifiedVisit`.
- If the mocked Anthropic client is made to raise or time out in a test, **no**
  `NewsletterPage` revision is created for that run — no partial or fallback
  draft.
- No code path in this plan can publish a page; only a human Administrator,
  via the normal Wagtail publish action, can.
- The **only** Anthropic call in this plan's code is the monthly-newsletter
  drafting call described above; it is always mocked in tests (Plan 02's
  convention — no real API call anywhere in the suite).
- `ruff check` and `pytest` (including the guardrail and draft-visibility
  tests) pass in CI.

## Release plan

The failure mode here is benign — nothing auto-publishes — so this ships more
simply than Plan 08, gated by the human review step rather than a kill switch.

- **How it ships:** merge → deploy (the management command + read-only tools). No
  scheduled job, no public surface — the command is dormant until an
  Administrator runs it.
- **Phased first run:** the **maintainer** runs the command for the first month
  personally against real `DailyAggregate` data, reviews the drafted
  `NewsletterPage` for **quality and numeric fidelity**, edits if needed, and
  publishes it — the trial that proves the drafting flow before others use it.
  Routine monthly use by the Administrators follows.
- **Gating check:** the numbers-guardrail test (every figure traces to a
  `DailyAggregate` computation, never a model-invented figure), the
  draft-visibility test (the draft is invisible until published), and the
  permission test (the code path cannot publish) all green in CI.
- **Who gets access:** Administrators run the command and review/publish the
  draft; the **public** sees only the published newsletter. No auto-publish —
  the invariant-#4 **general** rule applies here (Plan 08's exception explicitly
  does not extend to this narrative).
- **Who's informed:** the three Administrators — brief them that every AI-drafted
  newsletter is a **draft they must review and publish**, and that a figure that
  looks off means stop and check the guardrail, not hand-edit the number.
- **Rollback trigger:** none needed as a live switch — a bad or unwanted draft is
  simply **not published** (or discarded in the admin), and the command is re-run
  or skipped. A failed run leaves no draft and an admin-visible audit record; it
  is a "run again later," never a regression.
