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
   reviews and approves before it is published.
5. **Never commit patient data or raw exports.** `.gitignore` blocks `*.xls`,
   `*.xlsx`, `/uploads/`, `/data/`. Do not override this.

## Stack

- **Django + Wagtail** (CMS) + **HTMX** — one Python codebase, minimal JS.
- **pandas / openpyxl / xlrd** — Excel parsing and aggregation.
- **Anthropic Python SDK** — generation. Models: `claude-opus-4-8` for drafting
  and schema inference, `claude-haiku-4-5` for translation / short tasks.
- **PostgreSQL** — aggregates and de-identified data only.
- **Hosting:** Render (or Railway), ~US$20–30/month all-in.

## Workflow conventions

- **Plans live in [`.claude/plans/`](.claude/plans/).** We plan each build step,
  commit the plan, then implement it. See the [plans index](.claude/plans/README.md).
- **One plan at a time.** Don't run ahead of the current step's plan.
- **Branch, don't commit to `main`.** Branch names: `plan/NN-slug`,
  `feat/slug`, `fix/slug`, `docs/slug`, `chore/slug`.
- **PR flow:** open a PR with `gh pr create`; keep PRs scoped to one plan/step.
- **Secrets** live in environment variables / `.env` (gitignored) — never in the
  repo or in prompts.

## Bilingual

Content is English + Urdu (tagline: صحت سب کے لیے / چراغ شفا). Build with i18n in
mind; Pashto may follow.
