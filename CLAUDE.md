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
   sample — never real patient rows. **One narrow, explicit exception**
   (decided 2026-07-23, Plan 11 Track B8/B9): the clinic export's seven named
   free-text columns (Presenting Complaints, Investigation, Provisional
   Diagnosis, Prescribed Medicine, Doctor's/Nurse's/Dietitian's Notes, Diet &
   Drug Compliance, Plan) may cross into a model call as raw text, because
   the maintainer confirmed the clinic software's data-entry UI structurally
   cannot accept a patient identifier in these specific fields — they are
   free of identifiers by construction, not by any scrub step this codebase
   performs. This exception covers *only* those seven named columns; a new
   free-text column added later needs that same question asked explicitly
   before it may cross into a model call, never assumed by analogy. See
   `apps.pipeline.freetext`'s module docstring for the full grounding note.
3. **Numbers are deterministic.** All published figures are computed in Python
   and injected into prompts. The AI writes prose only; it must never invent or
   restate statistics from memory.
4. **Human-in-the-loop.** Every AI-generated page is a draft that a person
   reviews and approves before it is published. **One narrow, explicit
   exception** (decided 2026-07-19, Plan 08, widened 2026-07-23, Plan 11
   Track B8/B9): a short AI-written summary sentence attached to a
   deterministic daily report page — and, as of the widening, that same
   page's AI-drafted free-text summary and empty-columns flag — may
   auto-publish together with the numbers they describe, but only when *all*
   of the following hold for each —
   - the prompt is a **fixed template** that only restates figures/values
     already computed in Python (per invariant #3 — it may not invent,
     fetch, or generalize beyond what it's given: the daily summary sentence
     gets the page's own aggregate figures; the free-text summary and
     empty-columns flag get only the already-collected free-text entries and
     already-computed booleans from `apps.pipeline.freetext`);
   - the call is tested exactly like every other AI call in this codebase:
     mocked in CI, with a guardrail test asserting the payload sent to it
     contains only that page's own de-identified data; and
   - if the call fails or times out, the page **still auto-publishes with the
     numbers alone** — none of these three AI outputs is ever allowed to
     block or gate the deterministic content.

   This exception covers *only* these three outputs (the daily summary
   sentence, the free-text summary, and the empty-columns flag) on the daily
   report page. It does not extend to Plan 09's monthly newsletter narrative
   or any other AI-authored content, which still requires human review and
   approval before publishing. Widening this exception further is a decision
   to make deliberately again, not something a future plan should assume by
   analogy.
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

## Observability

Sentry error tracking is live in production (Plan 12 Track A,
[.claude/plans/12-observability.md](.claude/plans/12-observability.md)).
`SENTRY_DSN` is read in `config/settings/prod.py` with a blank default and the
SDK only initializes if it's set — deliberately soft-fail, unlike
`ANTHROPIC_API_KEY`/`MEDIA_*`, so a missing/revoked DSN never affects boot or
behavior. Events are tagged with `environment=production` and `release`
(Render's auto-injected `RENDER_GIT_COMMIT` — no separate release-tag env var
exists). See [docs/deploying.md](docs/deploying.md) → Secrets.

A **Sentry MCP server** is registered on the maintainer's machine for this
project (`claude mcp add --transport http sentry https://mcp.sentry.dev/mcp`,
scope `local` — lives in Claude Code's own config, not the repo, so it won't
exist on a fresh clone or another machine; OAuth-connected to the
maintainer's Sentry account as of 2026-07-24). Where present, query
issues/events/traces directly via its `mcp__sentry__*` tools instead of
driving the dashboard through a browser. MCP servers load at session start,
so a session already running before the server was added won't see the tools
until it's restarted; check with `claude mcp list`.

## Traffic analytics (Umami)

Site traffic (visits, top pages, referrers, time on site) is tracked with
**Umami Cloud** — a cookieless, aggregate-only script, added deliberately as a
recorded reversal of the earlier "no analytics by default" guardrail (Plan 12
Track B; see `templates/base.html` and Plan 01's dated addendum). The site's
`UMAMI_WEBSITE_ID` is set in Render (see `docs/deploying.md`), not sensitive —
it's a public value embedded in every page's HTML source anyway.

There is no MCP server wired up for Umami in this project (no official one
exists; a few community ones do, but none are connected here). To check
analytics or edit the dashboard, use Chrome browser automation:

1. Navigate to `https://cloud.umami.is/login`.
2. Click "Continue with Google" — this picks up the maintainer's already
   authenticated Google session (`hikmatyarhasan@gmail.com`) with no password
   prompt. If a password prompt ever does appear, stop and hand off to the
   maintainer rather than entering one.
3. The site is listed as "Thandkoi Clinics" (`thandkoiclinics.com`). A saved
   board named **"Thandkoi clinics"** (Boards in the left nav) already has the
   key widgets: Metrics bar (visitors/visits/views/bounce rate/visit
   duration), a visitors-over-time chart, Top pages, and Referrers.

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
  step that comes before a PR exists at all. **Keep every re-run targeted**
  (2026-07-23 — see the skill's own "Token discipline" note): only the first
  pass on a branch needs the whole diff; every loop iteration after a fix
  should scope the re-review to just the files that fix touched, not the
  full branch again, and a tiny or docs-only diff should get a single-pass
  read instead of the full multi-agent workflow. **The multi-agent dynamic
  Workflow review is opt-in, not automatic** (2026-07-23 — it burns too many
  tokens to run by default). The mandatory pre-PR review default is a
  careful single-pass manual read; only invoke the `Workflow`-tool-backed
  multi-agent pass when the maintainer has explicitly asked for it earlier
  in the current session. If a change looks risky enough to warrant the
  heavier pass, ask first — never launch it unprompted.
- **PR flow:** once review is clean, open a PR with `gh pr create` (draft —
  see the personal lifecycle doc's "drafts stay drafts until I sign off");
  keep PRs scoped to one plan/step. Merge once CI is green and the PR has been
  taken out of draft.
- **Label every PR by its Conventional-Commit type** (2026-07-24), right
  after opening it: `feat` → `enhancement`, `fix` → `bug`, `docs` →
  `documentation`, `chore` → `chore` (e.g.
  `gh pr edit <number> --add-label enhancement`). This is what
  [`.github/release.yml`](.github/release.yml) groups the auto-generated
  GitHub Release notes by — GitHub's release-notes generator reads only PR
  labels, never commit messages or titles, so a PR left unlabeled falls into
  the release notes' catch-all "Other Changes" bucket instead of its real
  category. Skip only for the rare PR whose title doesn't start with one of
  these four types.
- **After every merge:** run the [`cleanup-worktrees`](.claude/skills/cleanup-worktrees/SKILL.md)
  skill immediately (2026-07-23 — the trigger is "a PR just merged," not
  "whenever the worktree pile-up gets noticed"), and flip that plan's row in
  the [plans index](.claude/plans/README.md) to ✅ Done (or ⏸ Paused if only
  part of the plan's scope landed and the rest has stalled) in the same pass.
- **Secrets** live in environment variables / `.env` (gitignored) — never in the
  repo or in prompts.
- **Content changes (Wagtail pages/documents) are not code changes.** They
  don't need a branch, plan, or PR. See
  [docs/content-operations.md](docs/content-operations.md) for the two
  ways content gets published: by hand in the Wagtail admin, or
  agent-driven via SSH into the production Render instance running
  Wagtail's own Python API.

## Bilingual

Content is English + Urdu (tagline: صحت سب کے لیے). Build with i18n in mind;
Pashto may follow.

> **2026-07-23:** the "چراغ شفا" half of the tagline was deliberately retired
> (maintainer's explicit ask, Plan 11 D4) — this is a content removal, not a
> doc that fell out of sync. Newsletter branding instead carries a clay-lamp
> ("chiragh") motif; see the newsletter archive template.
