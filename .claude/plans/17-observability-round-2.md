# Plan 17 — Observability round 2 (performance tracing, structured logs, dashboard)

**One-line:** turn on the two Sentry signals Plan 12 deliberately left off —
request performance (response times) and warning-level structured logs — with
the PHI scrubbing that tracing newly requires, and give the maintainer one
custom dashboard that shows errors, latency and warnings together.

## Background — why now

[Plan 12](12-observability.md) shipped Sentry error tracking and explicitly
**parked** two things:

> **Full APM / performance tracing** (Sentry performance monitoring,
> Datadog/New Relic) — disproportionate to current traffic. Revisit if
> traffic or team size grows.

and, by omission, structured log forwarding (it listed "Dedicated log
aggregation … beyond Render's own tail" as out of scope).

The maintainer asked (2026-07-25) for a Sentry dashboard tracking **response
times, warnings, errors, and anything else useful**. Verified against the live
Sentry org (`thandkoi-clinics`, region `de.sentry.io`) before planning:

| Signal | State on 2026-07-25 |
|---|---|
| Errors | ✅ flowing — 2 `level:error` events in the trailing 30d |
| Response times | ❌ **0 spans in 30d** — `sentry_sdk.init()` sets no `traces_sample_rate`, so tracing is off entirely |
| Warnings | ❌ **0 rows in the logs dataset** — `enable_logs` is off, and the default logging integration only promotes `ERROR`+ to events, so `logger.warning(...)` is a breadcrumb at best |

So the dashboard the maintainer wants cannot be built from existing data: two
of its three panels would render permanently empty. This plan is the explicit,
recorded reversal of Plan 12's parked APM decision — not a bug fix.

## Goal & scope

**Goal:** response-time percentiles and warning-level logs visible in Sentry
alongside the errors already there, on the free Developer plan, with no new
PHI exposure and no new way for the site to fall over.

**In scope**

*Track A — tracing (response times)*
- `traces_sample_rate` wired via a new optional `SENTRY_TRACES_SAMPLE_RATE`
  env var, so the rate is dialable from the Render dashboard without a code
  change or PR.
- A `traces_sampler` that drops `/healthz` traffic entirely (see Decision 3).
- **`before_send_transaction`** — the PHI hook tracing newly requires
  (Decision 1). This is the load-bearing part of the track.

*Track B — structured logs (warnings)*
- `enable_logs=True` plus `LoggingIntegration(sentry_logs_level=WARNING)` so
  `logger.warning(...)` becomes a searchable, dashboard-able signal instead of
  a breadcrumb.
- `before_send_log` applying the same scrub posture as the event hooks.

*Track C — testability*
- Extract the Sentry hooks out of `config/settings/prod.py` into a plain
  `config/observability.py` module so the test suite can exercise them
  (Decision 2).

*Track D — the dashboard itself*
- One custom Sentry dashboard ("Thandkoi Clinics — Service health") built in
  the Sentry UI. Not code; recorded here so the widget set is documented.

**Out of scope (parked, deliberately)**

- **Profiling.** Sentry's pricing page marks profiling "Pay-as-you-go
  required", and the Developer plan has no PAYG — so it is not merely
  expensive here, it is unavailable. Revisit only on a paid plan.
- **Session Replay.** 50/month are included on the free plan, but replay
  records the DOM of pages an admin views — which, in the Wagtail admin,
  can include a rendered patient export mid-upload. Turning it on would need
  its own PHI decision; not taken here.
- **Tracing the Anthropic SDK calls as AI spans.** Sentry's AI Agents
  dashboards exist in the org and would light up with `gen_ai.*` spans, but
  routing prompt payloads into span attributes crosses the CLAUDE.md
  invariant #2 line and needs the same deliberate widening the free-text
  exception got. Not in this plan.
- **Raising log volume beyond WARNING.** `sentry_logs_level=INFO` would ship
  every request's INFO chatter; no value at this traffic level.
- **Replacing the external uptime monitor with Sentry's.** One uptime monitor
  is included free, and it is a good idea — but it is a Sentry-UI setup task
  with no code change, tracked with Track D rather than as code scope.

## Free-tier feasibility (verified 2026-07-25)

The maintainer asked explicitly whether this fits the free tier. Checked
against [Sentry's pricing page](https://sentry.io/pricing/):

| Free Developer plan, per month | Included |
|---|---|
| Errors | 5k |
| **Spans (tracing)** | **5M** |
| **Logs** | **5GB** |
| Custom dashboards | 10 |
| Uptime monitors | 1 |
| Cron monitors | 1 |
| Replays | 50 |
| Attachments | 1GB |

**The Developer plan has no pay-as-you-go.** Over-quota data is dropped and
never billed, so the worst case of mis-sizing the sample rate is "some spans
go missing", never a surprise invoice. That property is what makes a high
sample rate safe to start with.

Sizing against real traffic rather than a guess — Render's HTTP metrics and
request logs are unavailable on this service's plan (`http_request_count`
404s; gunicorn runs without `--access-logfile`), so the figure comes from
Umami, checked in the live dashboard on 2026-07-25:

> **15 page views, 3 visits, 1 visitor** in the trailing 24 hours.

At that volume, even 100% sampling of every request is roughly three orders of
magnitude inside the 5M-span budget. The dominant span source would in fact be
the **uptime monitor itself** — a 60-second poll of `/healthz` is ~43,200
requests/month all on its own, which is why Decision 3 drops it.

## Decisions

**D1 — `before_send` is not enough once tracing is on; add
`before_send_transaction`.**
`config/settings/prod.py` currently registers `_sentry_before_send`, which
strips `request.data` / `request.body` so the upload view's multipart body — a
raw patient export, CLAUDE.md invariant #1 — never leaves the process. That
hook fires **only for error events**. A transaction (performance) event
carries its own `request` section, so enabling `traces_sample_rate` without a
matching `before_send_transaction` would reopen exactly the hole Plan 15 Track
A1 closed, through a new door. The scrub is therefore factored into one
function applied by both hooks.

**D2 — move the hooks into `config/observability.py` so they can be tested.**
Today the scrub lives inside `prod.py`, and importing `prod.py` executes the
whole production settings file and demands every required secret. That is
precisely why the original scrub shipped with **no unit test** — the CI
`check --deploy` gate (Plan 15 Track A2) proves it *imports*, not that it
*scrubs*. Given that a Sentry PHI leak is the one defect class this codebase
has already shipped once, the hooks become plain functions in a plain module
with direct tests. `prod.py` keeps its comments and simply wires them up.

**D3 — the `traces_sampler` drops `/healthz`.**
Health-check traffic is the single highest-volume route on this site and its
latency tells the maintainer nothing (it is a bare 200). Sampling it would
spend most of the span budget on noise and drag the p50 of every "all
transactions" widget toward zero, making the dashboard actively misleading.

**D4 — the sample rate is an env var, defaulting to 1.0.**
`SENTRY_TRACES_SAMPLE_RATE` follows `SENTRY_DSN`'s soft-fail precedent: absent
or unparseable → fall back to the default rather than fail boot. Observability
must never become a new reason the site goes down (Plan 12's standing
decision). 1.0 is chosen because at 15 views/day a lower rate yields too few
samples for a meaningful p95, and the no-PAYG property caps the downside.

**D5 — forwarding `logger.warning` to Sentry is consistent with Plan 15 A1,
and is being recorded rather than assumed.**
`apps/pipeline/admin_views.py:152-165` deliberately does *not*
`capture_exception()` on `ExportParseError`, and its comment gives the reason:
capturing would attach a traceback "whose frame-locals sit on a raw patient
row mid-parse". The same comment states the log *message* is
"structural-only by the ExportParseError contract (never a cell value)".
Sentry log records carry the formatted message, not frame-locals — so
forwarding it is within the existing reasoning, not an extension of it.
`include_local_variables=False` remains set regardless. Flagged explicitly
here because "we already log it to stdout" is *not* on its own a reason it may
go to an external service.

## Precedent map (Stage 7)

- **`SENTRY_TRACES_SAMPLE_RATE` as an optional, soft-fail env var** — mirrors
  `SENTRY_DSN` in `config/settings/prod.py:123` (`env(..., default=...)`,
  never a boot failure), deliberately *unlike* the `MEDIA_*` / `ANTHROPIC_API_KEY`
  fail-loud pattern.
- **The scrub function itself** — lifts the body of the existing
  `_sentry_before_send` (`prod.py:126`) verbatim; no new scrubbing logic is
  invented.
- **CI coverage** — extends the existing "Check production settings" step in
  `.github/workflows/ci.yml:71` rather than adding a new gate; that step
  already sets a dummy `SENTRY_DSN` specifically so the `init(...)` path with
  its PHI kwargs executes at import.
- **Test style** — docstring-first tests naming the plan and the reason, per
  `apps/core/tests.py`.
- **Docs to update in the same change** (Stage 4 rule): `docs/deploying.md`
  Secrets section, `CLAUDE.md` Observability section, and this plan's row in
  the [plans index](README.md).

## Track D — dashboard widget set

Built in the Sentry UI (no code). Recorded so it can be rebuilt:

1. **Errors over time** — `count()` on the errors dataset, grouped by `level`.
2. **Errors by release** — attributes a regression to a deploy;
   `release` is already tagged from `RENDER_GIT_COMMIT`.
3. **p50 / p95 response time** — `p50(span.duration)`, `p95(span.duration)`
   over transactions, `/healthz` already excluded at source by D3.
4. **Slowest transactions** — `p95(span.duration)` grouped by transaction,
   sorted descending.
5. **Warnings over time** — logs dataset, `severity:warning`.
6. **Recent warning messages** — logs table, newest first.

Uptime monitor on `/healthz` set up alongside it (1 included free).

## Release plan

- **How it ships.** No feature flag. This is prod-only configuration with no
  user-visible surface: the site renders identically whether tracing is on or
  off, and every new hook is a no-op when `SENTRY_DSN` is blank. A flag would
  add a failure mode without protecting a user-facing behaviour — the
  deliberate no-flag choice Stage 6 asks to be recorded.
- **Rollback.** Set `SENTRY_TRACES_SAMPLE_RATE=0` in the Render dashboard —
  no deploy, no revert. Full rollback is re-deploying the previous release
  tag.
- **Gate.** CI's "Check production settings" step must pass (it executes
  `sentry_sdk.init(...)` with the new kwargs), plus the new scrub tests.
- **Who is informed.** Maintainer only; no downstream operators or users.

## Status

Track A–C implemented on `plan/17-observability-round-2`. Track D is a
Sentry-UI task done alongside.
