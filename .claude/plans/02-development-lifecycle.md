# Plan 02 — Development Lifecycle & Environments

_Status: Drafted · Depends on: 01 Project foundation · Next: 03 Design system & base templates_

## Goal

A repeatable, low-cost path from a merged PR to a live production change, with a
safety net (tests, a staging environment, a human approval gate) that fits
free/near-free hosting tiers and doesn't burn AI budget on every CI run. This
step exists because Plan 01 only gets the app to "boots locally, CI is green" —
it doesn't yet answer how code actually reaches users, or how we catch a
privacy-invariant regression before it ships.

## Scope

**In scope**
- Environment topology: local, CI, staging, production.
- CD pipeline: merge → auto-deploy staging → manual approval → deploy production.
- Testing strategy: unit/integration tests, and privacy-invariant guardrail
  tests — both fully deterministic, no AI involved in testing at all.
- Secrets/config per environment via GitHub Environments.
- Free-tier hosting choices and their limits, made explicit so nothing breaks
  by surprise (e.g. a DB that expires, a service that cold-starts).

**Out of scope** (later plans)
- The actual pages/models being deployed → Plans 03–09.
- Backup strategy, monitoring/alerting, funding-export → Plan 11 (Ops).
- Load/performance testing — not warranted at this traffic scale yet.

## Why staging, given "production only for now"

Two earlier answers looked like they conflicted: *skip staging* vs. *merge →
staging → manual approve → prod*. They don't, once split by what they're each
about:

- **Plan 01** doesn't need a live staging deploy — there's no content yet, just
  a health check. Config-only (`render.yaml` present, reviewed) is enough.
- **From this plan onward**, once there's real content and an AI-drafting step
  with a human-review gate, a staging environment is what that review gate
  deploys *to* — a reviewer needs a real URL to look at before approving
  production, not just a diff. That only works if standing it up is free.

Render's free web service tier makes this free: it sleeps after 15 minutes of
inactivity, which is a non-issue for a low-traffic internal review target and
disqualifying for a public production site. So: **free tier for staging, paid
Starter ($7/mo) for production** — one environment absorbs the free tier's
downside, the other avoids it. This keeps us inside the ~$20–30/month already
budgeted in [CLAUDE.md](../../CLAUDE.md).

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Environments | local, CI, staging, production | No per-feature preview envs — team is too small to need them. |
| Staging host | Render **Free** web service | Sleeps when idle; acceptable, staging is reviewer-only traffic. |
| Production host | Render **Starter** ($7/mo) | No cold starts; public-facing. |
| Database | **Neon Postgres**, branch per environment | Free tier doesn't expire (unlike Render's free Postgres, which drops after 90 days). `main` branch → prod, `staging` branch → staging. |
| CD trigger | Merge to `main` → auto-deploy staging | Render auto-deploy from branch, or a deploy-hook step in GitHub Actions. |
| Promotion | Manual approval → deploy production | GitHub Environments protection rule: a required reviewer must approve the `production` deployment job before it runs. |
| AI calls in tests | **Never** — always mocked with fixture responses | The test suite never calls the real Anthropic API and is never used to validate AI output quality or privacy compliance. Testing is 100% deterministic Python assertions. |
| Verifying the live API | Manual, outside the test suite | If the Anthropic API integration needs checking (new model, SDK upgrade), a person runs it manually against staging. Not automated, not scheduled, not part of CI. |
| Secrets | GitHub Environments (`staging`, `production`), separate secret sets | Never share a Neon connection string or Anthropic key between environments. |

## Environment topology

```
 local            CI (per PR)         staging                 production
 ───────          ─────────────       ─────────────────       ─────────────────
 SQLite or        Postgres service    Render Free web svc      Render Starter web svc
 docker-compose    container          Neon `staging` branch    Neon `main` branch
 Postgres          (ephemeral)        auto-deployed on         deployed on manual
                   AI calls: mocked   merge to main             approval only
                                      AI calls: real            AI calls: real
                                      (this is what a human
                                      reviewer reads and
                                      approves — not AI)
```

## CD pipeline

```
PR opened  ──▶  CI: ruff + pytest (Postgres service, AI mocked)  ──▶  PR review
                                                                          │
                                                                     merge to main
                                                                          │
                                                                          ▼
                                                        Deploy → staging (automatic)
                                                                          │
                                                        Reviewer checks staging URL,
                                                        approves prod deploy job in
                                                        GitHub Environments UI
                                                                          │
                                                                          ▼
                                                        Deploy → production (manual gate)
```

Rollback: redeploy the previous commit's Render deploy (Render keeps prior
deploys one click away) — no separate rollback tooling needed at this scale.

## Testing strategy

Two layers, both fully deterministic — **no AI is involved in the testing
process itself**, either as the thing being validated with a real API call or
as a mechanism for judging output. AI-output quality is checked by the human
reviewer at the approval gate (CLAUDE.md invariant #4), not by a test:

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
questions for a human on staging, not for the test suite.

## Task checklist

1. **Neon setup** — create project, `main` + `staging` branches, connection
   strings recorded as secrets (not committed).
2. **Render setup** — staging (Free) and production (Starter) web services;
   confirm `render.yaml` from Plan 01 covers both via Render's blueprint
   `envGroups` or two service blocks.
3. **GitHub Environments** — create `staging` (no protection, auto-deploy) and
   `production` (required reviewer) environments in repo settings; add
   per-environment secrets.
4. **CD workflow** — `.github/workflows/deploy.yml`: on push to `main`, deploy
   to staging automatically; a second job targeting the `production`
   environment (gated by the required reviewer) deploys the same commit.
5. **Mock AI client fixture** — a pytest fixture/conftest that swaps the
   Anthropic client for a canned-response stub; used by default in CI.
6. **Privacy guardrail tests** — write the three tests described above (or
   more, if more invariants exist by the time the pipeline exists).
7. **Update Plan 01's `render.yaml`** — confirm it parameterizes environment
   (staging/production) rather than assuming one target.
8. **Document the flow** — short section in README or a `docs/deploying.md`:
   how a change goes from merge to production, who approves, what to check on
   staging before approving.

## Acceptance criteria

- Merging a PR to `main` deploys to staging without manual steps.
- Production deploy requires an explicit approval in GitHub's Environments UI;
  it cannot happen from a PR merge alone.
- CI runs with zero real Anthropic API calls and passes without network access
  to `api.anthropic.com`.
- No AI model call appears anywhere in the automated test suite, scheduled or
  otherwise — the only real API calls happen from staging/production traffic.
- At least one privacy-guardrail test exists per invariant in CLAUDE.md that's
  testable at this stage (raw-PHI-never-persisted; AI-never-sees-patient-data;
  numbers-are-deterministic) — the human-in-the-loop invariant is enforced by
  the approval gate itself, not a test.
- Total monthly hosting cost stays within the ~$20–30/month range already
  budgeted in CLAUDE.md.

## Open questions for the maintainer

- Confirm Render Starter ($7/mo) for production is acceptable, or prefer to
  stay fully free and accept production cold-starts for now.
- Who is the required reviewer for production deploys — just you, or others
  from the ≤20-person admin group?
