# Deploying

How a change gets from a merged PR to live production, who gates it, and how AI
content is reviewed separately. This implements
[Plan 02](../.claude/plans/02-development-lifecycle.md).

## Environments

There are three, and only three:

| Environment | Where | Database | AI calls |
|---|---|---|---|
| **local** | your machine | docker-compose Postgres (or SQLite) | mocked in tests |
| **CI** | GitHub Actions, per PR | ephemeral Postgres service container | mocked — never real |
| **production** | Render (Starter compute) | Neon Postgres, single database | real, from live traffic |

There is **no staging environment** — deliberately. See the plan's
[rationale](../.claude/plans/02-development-lifecycle.md#no-staging-environment--and-why-thats-fine):
the two jobs a staging deploy would do are handled elsewhere — "is this code
safe to ship?" by the deploy gate below, and "is this AI content good enough to
publish?" by Wagtail's in-app draft workflow.

## From merge to production

```
PR → CI (ruff + pytest, AI mocked) → review → merge to main
                                                   │
                          (nothing deploys — main can sit ahead of prod)
                                                   │
                        cut a release tag  →  run the Deploy workflow
                                                   │
                                                   ▼
                                             Render deploys
```

Merging to `main` **never** changes production on its own. Production only
changes when a human runs the Deploy workflow.

### 1. Cut a release tag

Deploys target a **tag**, not a moving branch — so "what's in production" is
always a specific, named commit.

```bash
git checkout main && git pull
git tag v2026.07.20        # date-based; add -2, -3… for a second release same day
git push origin v2026.07.20
```

Tags are **lightweight and date-based** (`v2026.07.20`), not semver — a CMS
website has no API consumers for "breaking change" semantics to describe; a tag
just answers "when was this cut and what commit is it."

Optionally, publish a [GitHub Release](https://github.com/hh2110/thandkoi-clinics/releases)
from the tag with auto-generated notes — a free, human-readable "what shipped
and when" log.

### 2. Run the Deploy workflow

The Deploy workflow (`.github/workflows/deploy.yml`) is `workflow_dispatch`-only
and takes a **required `ref` input** — the tag you just cut.

- **UI:** Actions → **Deploy** → *Run workflow* → enter the tag (e.g.
  `v2026.07.20`) → *Run*.
- **CLI:** `gh workflow run deploy.yml -f ref=v2026.07.20`

The workflow checks out the tag, **verifies the ref really is a tag** (it
refuses a branch or raw SHA), and triggers a Render deploy of that exact commit.

## Who approves the deploy gate

The `workflow_dispatch` trigger **is** the gate. Nothing deploys without a
person explicitly running the workflow against a chosen tag.

There is intentionally **no** GitHub Environments "required reviewers" rule:
that feature needs GitHub Pro/Team on a private repo (this repo is on Free — the
API rejects a reviewer rule here), and `workflow_dispatch` gives the identical
safety property — no deploy without a human — for $0. Anyone who can run the
workflow already has repo write access, i.e. the same people who can merge a PR.

The `production` GitHub Environment still exists, but **only to scope secrets**
(so only this workflow can read production secrets), not as a protection gate.

## Rollback

Re-run the Deploy workflow with the **previous** tag as the `ref`:

```bash
gh workflow run deploy.yml -f ref=v2026.07.19
```

Because deploys are tag-addressed, rollback is precise — no guessing which entry
in Render's own deploy history is the right one.

## AI content review is a *separate* gate

The deploy gate ships **code**. It does **not** decide whether AI-drafted
*content* is fit to publish — that is a different checkpoint, handled entirely
in-app by Wagtail's **draft → preview → publish** workflow (CLAUDE.md invariant
#4). An AI-generated newsletter or report lands as a Wagtail **draft** on
production; a person previews and approves it there before it goes live. No
deploy is involved in publishing a piece of content, and no separate
environment is needed to review it.

So the two gates are orthogonal:

- **Deploy gate** (this workflow) — "is this code safe to ship?"
- **Wagtail draft workflow** (in-app) — "is this AI content good enough to
  publish?"

## Testing keeps AI out of the loop

CI runs `ruff` + `pytest` with **zero** real Anthropic API calls — the client is
always mocked (see `conftest.py` and `apps/pipeline/`). The test suite is 100%
deterministic Python and never validates model output quality or reaches
`api.anthropic.com`. Whether the live API integration still works, and whether
AI output is good, are checked by a human on production — never by a test.

## Secrets

Production secrets live in two places, never in the repo:

- **Render dashboard** (service → Environment): `DATABASE_URL` (the Neon
  connection string), `ANTHROPIC_API_KEY`, and the media object-storage
  variables — `MEDIA_BUCKET_NAME`, `MEDIA_S3_ENDPOINT_URL`,
  `MEDIA_S3_ACCESS_KEY_ID`, `MEDIA_S3_SECRET_ACCESS_KEY`, `MEDIA_CUSTOM_DOMAIN`
  (the Cloudflare R2 bucket for user uploads — see
  [Plan 10](../.claude/plans/10-media-object-storage.md)). `SECRET_KEY` is
  generated by Render.
- **GitHub `production` Environment** (repo → Settings → Environments):
  `RENDER_DEPLOY_HOOK_URL`, used by the Deploy workflow to trigger the deploy.

> **Media storage is required in production.** Because these five `MEDIA_*`
> variables are read unconditionally in `config/settings/prod.py`, the service
> will fail to boot until they are set. Create the R2 bucket and set them
> **before** the next deploy — see the Plan 10 first-time-setup steps.

## First-time setup (manual, one-off)

These require account/billing access and are done by the maintainer:

1. **Neon** — create a project and a single production database; copy its
   connection string into Render as `DATABASE_URL`.
2. **Render** — create one web service from `render.yaml` (Starter compute);
   set `DATABASE_URL` and `ANTHROPIC_API_KEY`; grab the service's **Deploy
   Hook** URL.
3. **GitHub** — create a `production` Environment (no protection rule) and add
   `RENDER_DEPLOY_HOOK_URL` as an environment secret.
