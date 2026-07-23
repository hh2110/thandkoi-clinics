# CLAUDE.md — Thandkoi Clinics

Project guide for Claude Code sessions in this repository. Read this first.

## What this is

Website + AI-native data pipeline for **The Thandkoi Clinics**, a not-for-profit,
family-run primary care clinic in Thandkoi, Swabi (KPK, Pakistan), funded on a
Zakat / Sadaqa model. Full context: [docs/architecture-and-ai-brief.md](docs/architecture-and-ai-brief.md).

## Privacy invariants (NON-NEGOTIABLE)

The daily clinic export contains full patient health information (PHI). These
rules are architectural constraints, not preferences — never weaken them:

1. **Never persist raw PHI.** Uploaded exports are parsed and aggregated **in
   memory during the request**, then discarded. Only de-identified aggregates
   (and optionally a de-identified row table with direct identifiers stripped)
   are stored.
2. **Never send patient data to any AI model.** Only de-identified numbers and
   category counts may cross into a model call. For schema inference on new
   formats, the model sees column names/dtypes and a synthetic/de-identified
   sample — never real patient rows.
3. **Numbers are deterministic.** All published figures are computed in Python
   and injected into prompts. The AI writes prose only; it must never invent or
   restate statistics from memory.
4. **Human-in-the-loop.** Every AI-generated page is a draft that a person
   reviews and approves before it is published. **One narrow, explicit
   exception** (decided 2026-07-19, Plan 08): a short AI-written summary
   sentence attached to a deterministic daily report page may auto-publish
   together with the numbers it describes, but only when *all* of the
   following hold —
   - the prompt is a **fixed template** that only restates the page's own
     already-computed figures (per invariant #3 — it may not invent, fetch,
     or generalize beyond the numbers it's given);
   - the call is tested exactly like every other AI call in this codebase:
     mocked in CI, with a guardrail test asserting the payload sent to it
     contains only that page's aggregate numbers; and
   - if the call fails or times out, the page **still auto-publishes with the
     numbers alone** — the AI sentence is never allowed to block or gate the
     deterministic content.

   This exception covers *only* that one summary sentence. It does not extend
   to Plan 09's monthly newsletter narrative or any other AI-authored content,
   which still requires human review and approval before publishing. Widening
   this exception is a decision to make deliberately again, not something a
   future plan should assume by analogy.
5. **Never commit patient data or raw exports.** `.gitignore` blocks `*.xls`,
   `*.xlsx`, `/uploads/`, `/data/`. Do not override this.

## Stack

- **Django + Wagtail** (CMS) + **HTMX** — one Python codebase, minimal JS.
- **pandas / openpyxl / xlrd** — Excel parsing and aggregation.
- **Anthropic Python SDK** — generation. Models (maintainer decision,
  2026-07-22): `claude-sonnet-5` for newsletter drafting, `claude-haiku-4-5`
  for the daily summary sentence / translation / short tasks, `claude-opus-4-8`
  reserved for schema inference (deferred — see plans README "Out of scope").
- **PostgreSQL** — aggregates and de-identified data only.
- **Hosting:** Render (or Railway), ~US$20–30/month all-in.

## Workflow conventions

- **Plans live in [`.claude/plans/`](.claude/plans/).** We plan each build step,
  commit the plan, then implement it. See the [plans index](.claude/plans/README.md).
- **One plan at a time.** Don't run ahead of the current step's plan.
- **Branch, don't commit to `main`.** Branch names: `plan/NN-slug`,
  `feat/slug`, `fix/slug`, `docs/slug`, `chore/slug`.
- **Review before a PR ever opens, every branch, no exceptions.** Once a
  branch's changes are committed and tests/lint pass, run the
  [`code-review-tc`](.claude/skills/code-review-tc/SKILL.md) skill (the
  repo-local wrapper around the built-in local code-review workflow) and loop:
  fix reasonable findings, reply to unreasonable ones with reasoning, re-run
  until the review comes back clean. Do this **before** `gh pr create`, not
  after — a PR only gets opened once its branch's review is clean. This
  applies uniformly, including to branches an agent/session produced as part
  of a larger batch — reviewing each one is not optional cleanup, it's the
  step that comes before a PR exists at all.
- **PR flow:** once review is clean, open a PR with `gh pr create` (draft —
  see the personal lifecycle doc's "drafts stay drafts until I sign off");
  keep PRs scoped to one plan/step. Merge once CI is green and the PR has been
  taken out of draft.
- **Secrets** live in environment variables / `.env` (gitignored) — never in the
  repo or in prompts.

## Bilingual

Content is English + Urdu (tagline: صحت سب کے لیے). Build with i18n in mind;
Pashto may follow.

> **2026-07-23:** the "چراغ شفا" half of the tagline was deliberately retired
> (maintainer's explicit ask, Plan 11 D4) — this is a content removal, not a
> doc that fell out of sync. Newsletter branding instead carries a clay-lamp
> ("chiragh") motif; see the newsletter archive template.
