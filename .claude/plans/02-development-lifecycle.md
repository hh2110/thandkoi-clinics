# Plan 02 — Development Lifecycle & Environments

_Status: Drafted · Depends on: 01 Project foundation · Next: 03 Design system & base templates_

## Goal

A repeatable, low-cost path from a merged PR to a live production change, with
a safety net (tests, a human approval gate) that fits free/near-free hosting
tiers and doesn't burn AI budget on every CI run. This step exists because
Plan 01 only gets the app to "boots locally, CI is green" — it doesn't yet
answer how code actually reaches users, or how we catch a privacy-invariant
regression before it ships.

## Scope

**In scope**
- Environment topology: local, CI, production. No staging environment.
- CD pipeline: merge to `main` → manual approval → deploy production.
- Testing strategy: unit/integration tests, and privacy-invariant guardrail
  tests — both fully deterministic, no AI involved in testing at all.
- Secrets/config via a GitHub Environment (scoping only, not a protection
  gate — see decisions table for why).
- Hosting choice, made explicit so cost is no surprise.

**Out of scope** (later plans)
- The actual pages/models being deployed → Plans 03–09.
- Backup strategy, monitoring/alerting, funding-export → Plan 11 (Ops).
- Load/performance testing — not warranted at this traffic scale yet.

## No staging environment — and why that's fine

Earlier drafts of this plan proposed a persistent staging deployment (Render
free tier) that a reviewer would check before approving production. Dropped,
per explicit direction: no staging environment or staging database branch.

The reasoning that made this safe to drop: staging was solving two different
problems, and only one of them actually needs a deployed environment.

1. **"Is this code safe to ship?"** — a deploy-safety concern. Solved by the
   manual-approval gate below: a human confirms before the deploy job runs.
   No staging URL is needed for this — the reviewer is reviewing the PR/diff,
   the same thing code review already covers.
2. **"Is this AI-drafted content good enough to publish?"** — a content-review
   concern, and a *different* one. This is already solved, independent of
   deployment, by Wagtail's own **draft → preview → publish** workflow (see
   [architecture-and-ai-brief.md §3](../../docs/architecture-and-ai-brief.md)):
   an AI-generated newsletter or report lands as a Wagtail draft *inside the
   running app* and is previewed and approved there before publishing. That's
   true on production itself — a separate staging deploy adds nothing to it.

So: one environment (production), one manual approval gate on the deploy
pipeline, and Wagtail's built-in draft workflow as the content-review gate
required by CLAUDE.md invariant #4. No second hosted environment to pay for,
patch, or keep in sync.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Environments | local, CI, production | No staging, no per-feature preview envs. |
| Production host | Render **Hobby workspace** ($0/mo) + **Starter compute** ($7/mo) = $7/mo total | Render splits pricing into a workspace plan (Hobby/Pro/Scale/Enterprise — account-level features, Hobby's limits are well above what this project needs) and per-service compute (Free/Starter/Standard/… — the actual instance size, found under "Compute pricing," not one of the four big workspace cards). Easy to miss "Starter" looking only at the top-level plan cards. No cold starts on Starter compute; public-facing. |
| Database | **Neon Postgres**, single database | No branch-per-environment — there's only one deployed environment now. |
| CD trigger | Merge to `main` → CI only, no deploy | Merging never triggers a live change by itself — see Promotion. |
| Promotion | A separate `workflow_dispatch`-only GitHub Actions workflow, run manually (Actions tab or `gh workflow run deploy.yml`) | **Not** a GitHub Environments protection rule — "required reviewers" on environments needs GitHub Pro/Team for a private repo (confirmed directly against this repo: the API rejects a reviewer rule on the Free plan). `workflow_dispatch` gives the identical safety property — nothing deploys without a human explicitly triggering it — for $0, on any plan, and is arguably simpler to reason about than an approval queue. |
| AI calls in tests | **Never** — always mocked with fixture responses | The test suite never calls the real Anthropic API and is never used to validate AI output quality or privacy compliance. Testing is 100% deterministic Python assertions. |
| Verifying the live API | Manual, outside the test suite | If the Anthropic API integration needs checking (new model, SDK upgrade), a person runs it manually. Not automated, not scheduled, not part of CI. |
| Secrets | A `production` GitHub Environment, used only for secret scoping (no protection rule) | Environments without protection rules are free on every plan and still usefully restrict which workflows/branches can read production secrets — just dropping the reviewer-gate feature specifically, not the environment concept. |

## Environment topology

```
 local                       CI (per PR)                production
 ─────────────────────       ─────────────────────       ─────────────────────
 SQLite or docker-compose    Postgres service container   Render Starter web svc
 Postgres                    (ephemeral)                  Neon Postgres (single db)
                              AI calls: mocked             deployed on manual
                                                            approval only
                                                            AI calls: real
                                                            (content review happens
                                                            via Wagtail drafts,
                                                            in-app — not a separate
                                                            deploy step)
```

## CD pipeline

```
PR opened  ──▶  CI: ruff + pytest (Postgres service, AI mocked)  ──▶  PR review
                                                                          │
                                                                     merge to main
                                                                          │
                                                                          ▼
                                                        (nothing deploys automatically —
                                                        main can sit ahead of production
                                                        indefinitely, that's fine)
                                                                          │
                                                        a human runs the `Deploy` workflow
                                                        manually (workflow_dispatch) —
                                                        this *is* the code-safety gate
                                                                          │
                                                                          ▼
                                                        Deploy → production
                                                                          │
                                                        AI-drafted pages still land as
                                                        Wagtail drafts and are
                                                        previewed/approved in-app
                                                        before publish (separate from
                                                        this deploy gate)
```

Rollback: run the deploy workflow again targeting the previous release tag
(see Versioning below) — git-native, doesn't depend on remembering or
finding the right entry in Render's own deploy history.

## Versioning & releases

`workflow_dispatch` can target any ref, which raises the question the
maintainer flagged: without something more disciplined than "whatever's on
`main` right now," there's no clear answer to "what version is actually
running in production" or "what exactly do I roll back to."

- **Deploys target a tag, not a moving branch.** `deploy.yml`'s
  `workflow_dispatch` takes a required `ref` input (a release tag); it does
  not default to deploying the tip of `main` directly. This makes every
  deploy an explicit, auditable choice of a specific, named commit.
- **Tagging scheme: lightweight, date-based** (`v2026.07.20`, incrementing
  a suffix `-2` if there's a second release the same day) — not strict
  semver. Semver's "breaking change" semantics don't map onto a CMS website
  with no API consumers; a tag's only job here is answering "when was this
  cut and what commit does it point to," and a date does that more directly
  than a semver number would.
- **Cutting a release** is a small manual step before deploying: tag the
  commit on `main` that's ready to ship (`git tag v2026.07.20 && git push
  --tags`), then run the deploy workflow with that tag as the `ref` input.
  Could be automated into a single "cut a release" workflow later if the
  two-step version gets tedious — not necessary to build that now.
- **GitHub Releases** (auto-generated notes from merged PRs, one per tag)
  give a human-readable "what shipped and when" log for free — cheap to
  turn on, useful for a small nonprofit team without needing a separate
  changelog process.
- **Rollback** is now precise: re-run the deploy workflow with the previous
  tag as the `ref` input. No ambiguity about which of Render's own deploy
  history entries is "the right one."

## Testing strategy

Two layers, both fully deterministic — **no AI is involved in the testing
process itself**, either as the thing being validated with a real API call or
as a mechanism for judging output. AI-output quality is checked by a human in
Wagtail's draft/preview workflow (CLAUDE.md invariant #4), not by a test or by
the deploy-approval gate — see "No staging environment" above for why those
are different checkpoints:

1. **Unit / integration tests** (pytest, every PR) — ordinary correctness:
   parsers, views, models. Already scaffolded in Plan 01's CI job.
2. **Privacy-invariant guardrail tests** (pytest, every PR, non-negotiable) —
   plain Python assertions against code behavior, no AI call in the loop:
   - Uploading a fixture `.xlsx` never results in a file on disk or a raw row
     in the database after the request completes.
   - The payload passed to the (mocked) Anthropic client contains only
     aggregate numbers/category counts — assert no patient-identifying field
     names or row-level data appear in the captured prompt object. This
     inspects what our code *sent*; it does not ask any model to judge
     anything.
   - A published newsletter/report page's numeric claims match the
     deterministic Python-computed aggregate byte-for-byte (the AI client is
     mocked to return fixed prose; the test asserts the numbers came from
     code, not the mock).

Any code path that calls the Anthropic client is exercised in tests only
against a mocked client — this is about keeping CI fast, free, and
deterministic, not about validating model output quality. Whether the real
API integration still works, and whether AI-drafted output is good, are both
questions for a human to check on production — via Wagtail's draft preview,
not the test suite.

## Task checklist

1. **Neon setup** — create project, a single production database, connection
   string recorded as a secret (not committed).
2. **Render setup** — one production web service (Starter); confirm
   `render.yaml` from Plan 01 targets it.
3. **GitHub Environment** — create a `production` environment (no protection
   rule — see Promotion decision above) in repo settings, purely to scope
   secrets; add them.
4. **CD workflow** — `.github/workflows/deploy.yml`: `on: workflow_dispatch`
   only (no `push` trigger), targeting the `production` environment for
   secrets. Takes a required `ref` input (a release tag — see Versioning &
   releases above), not an implicit "whatever's on `main`." That manual
   trigger, against an explicit tag, is the entire deploy gate.
5. **Mock AI client fixture** — a pytest fixture/conftest that swaps the
   Anthropic client for a canned-response stub; used by default in CI.
6. **Privacy guardrail tests** — write the three tests described above (or
   more, if more invariants exist by the time the pipeline exists).
7. **Update Plan 01's `render.yaml`** — confirm it targets the one production
   service.
8. **Document the flow** — short section in README or a `docs/deploying.md`:
   how a change goes from merge to production, who approves the deploy gate,
   and how Wagtail's draft workflow separately handles AI-content review.

## Acceptance criteria

- Merging a PR to `main` does **not** immediately change production — a deploy
  job is queued but held for approval.
- Production deploy requires an explicit approval in GitHub's Environments UI;
  it cannot happen from a PR merge alone.
- CI runs with zero real Anthropic API calls and passes without network access
  to `api.anthropic.com`.
- No AI model call appears anywhere in the automated test suite, scheduled or
  otherwise — the only real API calls happen from production traffic.
- At least one privacy-guardrail test exists per invariant in CLAUDE.md that's
  testable at this stage (raw-PHI-never-persisted; AI-never-sees-patient-data;
  numbers-are-deterministic) — the human-in-the-loop invariant is enforced by
  Wagtail's draft/publish workflow, not a test.
- Total monthly hosting cost stays within the ~$20–30/month range already
  budgeted in CLAUDE.md — simpler now than the earlier staging+production
  draft, since there's only one hosted environment.

## Resolved (was open questions)

- **Approval gate mechanism**: resolved — `workflow_dispatch`, not GitHub
  Environments protection rules (that feature isn't available on this
  repo's current plan; `workflow_dispatch` achieves the same property for
  free). Since anyone who can run a workflow already has write access to
  the repo, "who's the required reviewer" is now moot — it's whoever has
  repo write access, same as who can merge a PR.

## Open questions for the maintainer

- Confirm Render Starter ($7/mo) for production is acceptable, or prefer to
  stay fully free and accept production cold-starts for now.
