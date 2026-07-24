# Plan 12 — Observability (error tracking, uptime alerting, traffic analytics)

**One-line:** give the solo maintainer visibility into production failures and
site traffic — currently zero on both — at near-zero cost and with no new
service to operate.

## Background — why now

A full-codebase review (2026-07-24) confirmed there is **no observability at
all** in production: prod logging is plain stdout captured by Render with no
search/retention beyond the log tail, no error tracker, no uptime alerting, and
no traffic/pageview analytics. This isn't an oversight — `.claude/plans/README.md`
already listed *"Ops hardening — deploy hardening, backups, monitoring"* under
**Out of scope (for now)**, deferred 2026-07-19, and Plan 02 itself lists
"Backup strategy, monitoring/alerting, funding-export → out of scope for now".
That deferral is now being revisited.

The concrete gap found: every AI-drafting call site in `apps/pipeline/ai.py`
(newsletter prose, daily summary) sits inside a deliberate
`except Exception: logger.warning(...)` — correct per CLAUDE.md invariant #4
(the page must still auto-publish with numbers alone) — but a sustained
failure (an expired API key, a prompt tripping a length guard) currently
degrades silently forever. Separately, the maintainer wants basic traffic
metrics (visits, top pages, time on site) that don't exist in any form today.

## Goal & scope

**Goal:** know when the app breaks, know when it's down, and know whether
anyone is visiting it — without adding a service that itself needs looking
after, and without becoming a new single point of failure for the site.

**In scope**

*Track A — operational monitoring*
- Error tracking via Sentry (free tier), prod-only.
- Explicit `capture_exception()` calls at the existing deliberate
  broad-except sites in `apps/pipeline/ai.py` and `apps/pipeline/admin_views.py`
  so a swallowed-by-design failure still surfaces as an event.
- An external uptime monitor polling `/healthz`, with email alerting.
- Release tagging so Sentry can attribute a regression to a specific deploy
  tag (ties into `scripts/release.sh`).

*Track B — traffic analytics*
- Umami Cloud (free tier) — a cookieless, privacy-friendly pageview/visitor
  analytics script, added to `templates/base.html`.
- Gives: visits, unique visitors, top pages, referrers, and average visit
  duration ("how long they spend").

**Out of scope (parked, deliberately)**
- **Full APM / performance tracing** (Sentry performance monitoring,
  Datadog/New Relic) — disproportionate to current traffic. Revisit if
  traffic or team size grows.
- **Dedicated log aggregation** (Better Stack Logs, Papertrail) beyond
  Render's own tail — a related but separate concern; no action here beyond
  what Track A's Sentry events already surface.
- **Dependency vulnerability scanning** (Dependabot, `pip-audit` in CI) — a
  real gap the same review surfaced, but unrelated to observability; own
  follow-up plan.
- **Test coverage measurement in CI** — same: real gap, separate concern.
- **A custom "AI failures this month" dashboard** next to the existing
  `AiCallLog` cost table — Sentry's own issue counts cover this need for now;
  revisit only if Sentry's per-issue view proves insufficient in practice.
- **Backups, deploy hardening, funding-export tooling** — the remaining
  items from the original 2026-07-19 "Ops hardening" deferral; still out of
  scope, not part of this plan.

## Decisions

- **Sentry over rolling a custom error log** — free tier is enough at this
  scale; the Django integration is a few lines; avoids building and
  maintaining error-aggregation infra ourselves.
- **Sentry is prod-only and *soft-fail*, unlike `ANTHROPIC_API_KEY` or the
  `MEDIA_*` vars.** Those are read unconditionally and the app refuses to
  boot without them (Plan 10's "fail loud" doctrine) — deliberately different
  here. `SENTRY_DSN` is read with `default=""`, and the SDK is simply never
  initialized if it's blank. **Observability must never become a new reason
  the site goes down** — a missing or revoked Sentry DSN degrades to "no
  error tracking," never to a 500 or a boot failure.
- **Umami Cloud over self-hosting or Cloudflare Web Analytics.** Self-hosted
  Umami is free software but adds another service + database for a solo
  maintainer to operate — real ongoing burden for one more project. Cloudflare
  Web Analytics is free forever but doesn't reliably report visit duration,
  which was explicitly asked for. Plausible (hosted, ~$9/mo) is the fallback
  if Umami Cloud's free-tier event cap proves too low in practice.
- **The analytics script is added once, to `templates/base.html`, not
  per-page** — it needs to run on every page to count visits at all, matching
  how the existing theme-toggle bootstrap script in the same file is scoped.

## Privacy note

`templates/base.html` carries a standing comment — *"No analytics or
third-party scripts by default (privacy invariant)"* — a deliberate guardrail
from Plan 01, reaffirmed in Plans 04 and 05. This plan is the explicit,
recorded decision to turn that default on, which the "by default" wording
always left room for. It does **not** touch CLAUDE.md's numbered PHI
invariants (1–5) — those govern the clinic-export pipeline (patient health
data), which this plan never goes near. Umami Cloud was chosen specifically
*because* of that standing guardrail: it is cookieless, stores no
cross-site or persistent visitor identifier, and reports aggregate counts
only (pageviews, referrers, durations) — the same "aggregate, not identifying"
shape CLAUDE.md already requires of the clinic data pipeline, applied here to
ordinary web traffic. No cookie-consent banner is needed because no
identifying cookie is set.

Track A (Sentry) similarly never sees patient data — it captures Python stack
traces and request metadata (path, method, non-PHI context) from the
*website* process, not clinic-export content. The upload view
(`apps/pipeline/admin_views.py`) never has patient rows in scope by the time
it reaches any of its `except` blocks (see CLAUDE.md invariant #1), so nothing
Sentry could capture there differs from what it captures anywhere else.

## Precedent map (Stage 7)

- **`SENTRY_DSN` as an optional, `sync: false` env var** — mirrors the
  existing secret pattern in `render.yaml` (`ANTHROPIC_API_KEY`,
  `MEDIA_S3_*`), with the "fail loud vs soft-fail" distinction called out
  above as a deliberate divergence.
- **`capture_exception()` call sites** — the exact same locations as the
  existing `logger.warning(...)` calls in `apps/pipeline/ai.py:104`, `:261`,
  `:798` and `apps/pipeline/admin_views.py`'s upload-parsing except blocks;
  one additional line each, no new branching.
- **Sentry Django integration + `sentry_sdk.init()` in `prod.py`** — no
  in-repo precedent (greenfield); grounded against Sentry's own Django
  integration docs, same class of gap as Plan 10's R2 setup (external
  reference, not a guess).
- **Umami script tag placement** — mirrors the theme-toggle bootstrap
  `<script>` already inline in `templates/base.html`'s `<head>`; grounded
  against Umami's own install docs for the `data-website-id` attribute and
  cookieless configuration (`data-do-not-track`, if wanted).
- **External uptime monitor on `/healthz`** — no in-repo precedent (external
  SaaS, no code); grounded against the target service's own docs, same
  pattern as Plan 10's bucket first-time-setup.

## Feature flag (Stage 6)

No runtime flag. Both tracks are either prod-only settings (Track A, mirrors
Plan 10's environment-separation gate — dev/CI never load a DSN) or a single
site-wide script include with no partial user-facing behavior to gate
(Track B). Neither has a slice that could reach some users before others.

## Release plan (Stage 10)

- **How it ships:** two independent small PRs (Track A, Track B — see Tasks),
  each following the normal branch → CI → `code-review-tc` → draft PR flow.
  Track A requires the maintainer to create a Sentry account/project and set
  `SENTRY_DSN` in Render *before* it does anything (harmless if unset — see
  Decisions). Track B requires an Umami Cloud account + website ID.
- **Gating check:**
  - Track A: after deploy with `SENTRY_DSN` set, trigger one real exception
    (e.g. a Django shell `1/0` over SSH, or hit a route that 404s in a way
    that raises) and confirm it appears in the Sentry dashboard tagged with
    the current release tag.
  - Track B: load the live site, confirm a pageview registers in the Umami
    dashboard within a couple of minutes.
  - Uptime monitor: use the monitoring service's own "send test alert"
    feature rather than deliberately breaking prod.
- **Rollback:** both tracks are additive-only — no schema or data change.
  Rollback is either redeploying the previous tag or simply unsetting the
  relevant env var / removing the script tag.
- **Who's informed:** maintainer only (solo project).

### First-time setup (maintainer, one-off)

1. **Sentry** — create a free account + Python/Django project; copy the DSN.
2. **Render** (service → Environment) — set `SENTRY_DSN` (optional; leave
   unset and the app runs exactly as it does today).
3. **Uptime monitor** — create a monitor (e.g. UptimeRobot or Better Uptime,
   both free-tier) pointed at `https://thandkoiclinics.com/healthz`, with an
   email alert contact.
4. **Umami Cloud** — create a free account, add the site, copy the
   `data-website-id`; set it as `UMAMI_WEBSITE_ID` in Render's environment (or
   inline in the template if we decide it isn't sensitive enough to warrant a
   secret — call this at implementation time).
5. Deploy a new tag and run the gating checks above.

## Tasks

**Track A — operational monitoring**
- [ ] Add `sentry-sdk` to `pyproject.toml`; refresh `uv.lock`.
- [ ] Initialize Sentry in `config/settings/prod.py`, reading `SENTRY_DSN`
      with a blank default; pass the current release tag if available.
- [ ] Add `capture_exception()` calls at the existing except sites in
      `apps/pipeline/ai.py` and `apps/pipeline/admin_views.py`.
- [ ] Declare `SENTRY_DSN` in `render.yaml` (`sync: false`); document it in
      `docs/deploying.md` → Secrets.
- [ ] Maintainer: create the Sentry project, set the secret, wire up the
      external uptime monitor (docs-only, no code).
- [ ] Deploy a new tag; run both Track A gating checks.

**Track B — traffic analytics**
- [x] Add the Umami script tag to `templates/base.html`, replacing the
      "no analytics by default" comment with one explaining the decision and
      linking this plan. (PR #116)
- [x] Read `UMAMI_WEBSITE_ID` from settings/env — landed as a plain env var
      (`config/settings/base.py`, default `""`) exposed to templates via a new
      `apps.core.context_processors.analytics` context processor; not a
      secret, since it's a public site ID embedded in the page source either
      way. (PR #116)
- [x] Update `docs/deploying.md` to document `UMAMI_WEBSITE_ID`. (The Plan 01
      "Privacy guardrails to bake in now" addendum pointing here was already
      added when this plan was drafted — no further action needed on it.)
      (PR #116)
- [ ] Maintainer: create the Umami Cloud site, set the website ID.
- [ ] Deploy a new tag; run the Track B gating check.

## Acceptance criteria

- A deliberately-triggered exception in production appears in Sentry within
  a minute, tagged with the deploying release.
- The app boots and runs identically with `SENTRY_DSN` unset — no new
  fail-loud dependency.
- The external uptime monitor sends a real test alert successfully.
- The live site registers pageviews in the Umami dashboard, with no cookie
  set and no consent banner added.
- `docs/deploying.md` documents both new env vars; Plan 01's guardrail note
  points to this plan.
