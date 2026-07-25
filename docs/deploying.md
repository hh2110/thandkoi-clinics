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

**Production URL:** https://thandkoiclinics.com — health check at
[`/healthz`](https://thandkoiclinics.com/healthz).

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

### Cut a release tag and deploy it

```bash
scripts/release.sh
```

This one script (not a Claude Code skill — added 2026-07-23, replacing the
earlier `release-prod` skill, per maintainer preference for a plain,
inspectable script over an agent-driven one) does the whole runbook:

1. Checks `main` is up to date with `origin/main`, CI is green on that exact
   commit, and `RENDER_DEPLOY_HOOK_URL` is configured.
2. Prints what's shipping since the previous release tag.
3. Prompts for confirmation (the deploy gate — see below).
4. Cuts and pushes a date-based tag (`vYYYY.MM.DD`, or `-2`/`-3`… for a
   second release the same day).
5. Triggers the Deploy workflow for that tag and watches it to completion.
6. Health-checks production (`/healthz`) with a few retries.
7. Once the health check passes, publishes a [GitHub Release](https://github.com/hh2110/thandkoi-clinics/releases)
   for the tag with auto-generated notes (added 2026-07-24) — skipped if a
   Release for that tag already exists (the `--ref` rollback/redeploy path
   targets a tag that was already released when it first shipped, and a
   redeploy doesn't change the code, so that Release is left untouched). A
   failure to publish the Release is a warning, not a script failure — the
   deploy itself already succeeded by this point.

   [`.github/release.yml`](../.github/release.yml) groups these notes by PR
   label (Features / Fixes / Docs & Planning / Chores / Other Changes)
   instead of one flat list — GitHub's release-notes generator reads only PR
   labels, never commit messages or titles, so this depends on every PR
   being labeled by its Conventional-Commit type when it's opened (see
   CLAUDE.md's "PR flow").

> **2026-07-23 observed gap:** `/healthz: 200` confirms *a* healthy instance
> is responding, not that *every* access path is already on the new build.
> After a real release (`v2026.07.23-4`, adding `CampReportPage.report_document`),
> `scripts/release.sh` reported the health check passing and Render's own API
> already showed the new deploy as `"live"` — but an SSH shell into the
> instance (see [content-operations.md](content-operations.md)) still ran the
> *previous* build for roughly a minute afterwards, raising a `TypeError` for
> the field the new release had just added. If you're chaining an SSH
> content-op onto a release you just ran, don't treat the script's success
> output as proof that path is on the new code yet — re-check (e.g. retry, or
> confirm the deployed git SHA over SSH) rather than assuming.

Two flags: `--ref vYYYY.MM.DD` (deploy an existing tag as-is instead of
cutting a new one — see Rollback below), and `--yes` (skip the interactive
confirmation prompt — added 2026-07-23, maintainer decision, reversing the
script's original "no way to skip it, ever" policy specifically so an agent
session can run a release unattended; every other check, including the
CI-green check, still applies unchanged — `--yes` only skips the final "do
you want to do this" prompt). Run `scripts/release.sh --help` for the full
usage note.

Tags are **lightweight and date-based** (`v2026.07.20`), not semver — a CMS
website has no API consumers for "breaking change" semantics to describe; a tag
just answers "when was this cut and what commit is it."

Under the hood, this drives the Deploy workflow (`.github/workflows/deploy.yml`),
which is `workflow_dispatch`-only and takes a **required `ref` input** — the
tag. It checks out the tag, **verifies the ref really is a tag** (it refuses a
branch or raw SHA), and triggers a Render deploy of that exact commit. You can
still run it directly (UI: Actions → **Deploy** → *Run workflow*; CLI:
`gh workflow run deploy.yml -f ref=v2026.07.20`) if you want to skip the
script's precondition checks for some reason — not recommended for a normal
release.

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

Re-deploy the **previous** tag:

```bash
scripts/release.sh --ref v2026.07.19
```

Because deploys are tag-addressed, rollback is precise — no guessing which entry
in Render's own deploy history is the right one. `--ref` skips the
main/CI-freshness checks (there's nothing to check — you're deploying a tag
that already exists) but still confirms before triggering and health-checks
after.

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

For how content itself gets created or edited on production — by hand in the
Wagtail admin, or agent-driven via SSH into the Render instance — see
[content-operations.md](content-operations.md). Either way it's a content
change, not a deploy, so nothing here applies to it.

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
  (the Cloudflare R2 bucket for user uploads; `MEDIA_CUSTOM_DOMAIN` is a **bare
  hostname — no `https://`, no trailing slash** — see
  [Plan 10](../.claude/plans/10-media-object-storage.md)); `SENTRY_DSN`
  (Sentry error tracking); and `UMAMI_WEBSITE_ID` (Umami Cloud traffic
  analytics) — see [Plan 12](../.claude/plans/12-observability.md) for both.
  `SECRET_KEY` is generated by Render.
- **GitHub `production` Environment** (repo → Settings → Environments):
  `RENDER_DEPLOY_HOOK_URL`, used by the Deploy workflow to trigger the deploy.

> **Media storage is required in production.** Because these five `MEDIA_*`
> variables are read unconditionally in `config/settings/prod.py`, the service
> will fail to boot until they are set. Create the R2 bucket and set them
> **before** the next deploy — see the Plan 10 first-time-setup steps.

> **Limitation — the media bucket is public; Wagtail collection privacy does
> not gate it.** The R2 bucket is served as a public origin
> (`querystring_auth: False`, `default_acl: None` in `config/settings/prod.py`),
> so **any object in it is reachable by anyone who has (or guesses) its URL**,
> regardless of the Wagtail collection it lives in. Marking a Wagtail
> collection or document as *private* in the admin controls only who can see
> it **inside `/admin/`** — it does **not** put the served object behind a
> signed URL or an authentication check. Do not treat "private collection" as
> access control for a document that must not be public. This is acceptable
> today because no private documents exist — every uploaded image/document is
> intended to be public (newsletter photos, camp-report PDFs). If a genuinely
> private document is ever needed, the storage backend must first be
> re-architected to issue signed, expiring URLs (`querystring_auth: True` on a
> non-public bucket); enabling that is deliberately deferred until such a
> document exists (Plan 15 Track D6, Decision 5).

`SENTRY_DSN` is the deliberate exception to that "required" pattern: it's read
with a blank default and Sentry is only initialized if it's non-empty, so the
app boots and behaves identically whether or not it's set — see Plan 12's
Decisions. Leave it unset until a Sentry project exists; set it whenever
error tracking should turn on.

`SENTRY_TRACES_SAMPLE_RATE` ([Plan 17](../.claude/plans/17-observability-round-2.md)
Track A) follows the same soft-fail posture, one step further: it is optional,
not a secret, and an *unparseable or out-of-range* value is logged and ignored
in favour of the code default (`1.0`) rather than raising at import — a typo in
a monitoring knob must never be a boot failure. Its purpose is to make trace
volume dialable without a deploy:

| Value | Effect |
|---|---|
| unset / blank | code default, `1.0` — trace every request except `/healthz` |
| `0` | performance tracing off; errors and logs unaffected |
| e.g. `0.25` | sample a quarter of requests |

`/healthz` is never traced at any setting (Plan 17 Decision 3) — a 60-second
uptime poll is ~43k requests/month whose latency says nothing, and including it
would drag every p50 widget toward zero. Sizing note: the free Developer plan
includes **5M spans/month with no pay-as-you-go**, so over-quota spans are
dropped and never billed; at this site's measured traffic (15 page views in the
24h to 2026-07-25) full sampling sits orders of magnitude inside that budget.

`UMAMI_WEBSITE_ID` ([Plan 12](../.claude/plans/12-observability.md) Track B)
is set in the Render dashboard too, but isn't a secret — it's a public value
that ships in every page's HTML source regardless, so unlike the vars above
it doesn't need Render's secret handling. It's blank by default, and
`base.html` renders no analytics script at all until it's set — the app boots
and behaves identically either way.

## First-time setup (manual, one-off)

These require account/billing access and are done by the maintainer:

1. **Neon** — create a project and a single production database; copy its
   connection string into Render as `DATABASE_URL`.
2. **Render** — create one web service from `render.yaml` (Starter compute);
   set `DATABASE_URL` and `ANTHROPIC_API_KEY`; grab the service's **Deploy
   Hook** URL.
3. **GitHub** — create a `production` Environment (no protection rule) and add
   `RENDER_DEPLOY_HOOK_URL` as an environment secret.
