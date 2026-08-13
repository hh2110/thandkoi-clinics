# Plan 23 — Let Neon scale to zero: split `/healthz` from `/readyz`

**One line:** the health probe runs `SELECT 1` and Render polls it every five
seconds, so the Neon compute has not suspended once since 2026-07-26 and is
burning roughly twice the free tier's monthly compute allowance; split liveness
(no database) from readiness (database) so the high-frequency poll stops
touching Postgres.

---

## Background — why now

On 2026-08-13 Neon emailed that project `thandkoi-clinics` had used **80.2 of
its 100 CU-hour monthly compute allowance (80%)**. Nothing about the site's
traffic explains that: Umami measured 15 page views in a day the last time it
was checked (2026-07-25, recorded in Plan 17).

### What is actually happening

Neon autosuspend *is* enabled. The project reports
`suspend_timeout_seconds: 0`, which is the API's spelling of "the 5-minute
default". The compute simply never gets five idle minutes.

`apps.core.views.healthz` issues a real query on every request:

```python
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
```

and the live Render service (`srv-d9ej48n41pts73f1i3p0`) has
`healthCheckPath: /healthz`, which Render polls continuously.

Evidence, gathered 2026-08-13 by sampling `pg_stat_activity` on the production
branch (system catalogs only — no patient data was read):

- The compute `ep-orange-meadow-az8103hh` reports `started_at:
  2026-07-26T17:36:13Z` with `current_state: active` — **18 days continuously
  running, not one suspend.**
- There is exactly one application backend at a time (`neondb_owner`, from
  `10.53.35.99`), and its `last_query` is `SELECT 1` on every sample.
- Four samples put that query **3.59 s, 3.98 s and 3.69 s** in the past —
  never the ~30 s average you would see against a 60-second poll.
- Its completion timestamps land on a five-second grid, phase-locked to the
  same sub-second offset: `13:34:49.843`, `13:35:54.843`, `13:36:54.842`,
  `13:37:24.843`. Every gap is a multiple of 5 s.
- `backend_start` advances every 60 s (`13:34:04.857` → `13:35:04.858` →
  `13:36:09.209`), which is `CONN_MAX_AGE = 60` recycling the connection
  underneath a poll that is much faster than it.

So the dominant caller is **Render's own health check at ~5-second intervals** —
about **17,000 `SELECT 1` round-trips a day**. The UptimeRobot 60-second poll
that Plan 17 sized at ~43k requests/month is real but secondary: pausing it
would change nothing, because Render's check alone keeps the compute awake
forever.

### The arithmetic

The compute sits at its 0.25 CU floor, always on:

| | |
|---|---|
| 0.25 CU × 24 h | 6.0 CU-hr/day floor |
| observed (80.2 CU-hr over 12.57 days) | **6.38 CU-hr/day** |
| projected full month | **~195 CU-hr** |
| free tier allowance | **100 CU-hr** |
| projected date of 100% | **~2026-08-16** |

An always-on 0.25 CU compute needs ~182 CU-hr/month at minimum. **The free tier
structurally cannot host one.** This is not overuse — scale-to-zero is
load-bearing for the plan, and we disabled it by accident.

---

## Scope

### Track A — code

1. **`apps/core/views.py`** — `healthz` becomes a liveness probe with no
   database access. A new `readyz` carries the `SELECT 1` and the existing
   503-on-failure behaviour, docstring and all.
2. **`config/urls.py`** — register `readyz` alongside `healthz`, unprefixed,
   for the same reason the health check is unprefixed.
3. **`config/observability.py`** — `UNSAMPLED_PATHS` keeps `/healthz` and
   deliberately does *not* gain `/readyz` (see D7).
4. **`apps/core/tests.py`** — `/healthz` returns 200 **and issues zero
   queries**; `/readyz` returns 200 against a live database and 503 when the
   connection raises.
5. **`scripts/release.sh`** — `HEALTH_URL` points at `/readyz`, so the
   post-deploy gate still proves the new build can reach its database.

### Track B — Render configuration (maintainer, no deploy needed)

- Set **`DB_CONNECT_TIMEOUT=15`** before the compute is first allowed to sleep
  (D5). It is a `sync: false` env var, dialable from the dashboard.
- Leave `healthCheckPath: /healthz` exactly as it is — that path keeps working
  and gets cheaper. No dashboard change, which is the point of D1.
- Leave the UptimeRobot monitor on `/healthz`. It keeps answering "is the site
  up" and stops billing us for the privilege.

### Track C — docs made true again

A stale doc is a defect (lifecycle Stage 4), and this change falsifies three
existing statements:

- **`config/database.py`** — its `DEFAULT_CONNECT_TIMEOUT_SECONDS` note says
  "today the UptimeRobot `/healthz` poll queries the database often enough to
  keep the compute warm, so resumes effectively do not happen". After this
  plan that is false, and the scenario it names as hypothetical becomes the
  normal case.
- **`docs/deploying.md`** — the same claim, the `DB_CONNECT_TIMEOUT` table, and
  release step 6's `/healthz`.
- **`CLAUDE.md`** — the Observability section should name the split so a future
  session doesn't "helpfully" restore the DB check to `/healthz`.
- **`.claude/plans/README.md`** — add the row for this plan.

---

## Decisions

**D1 — `/healthz` loses the query; a new `/readyz` gains it. Not the reverse.**
The obvious alternative is to leave `/healthz` as the readiness probe, add a
DB-free `/livez`, and repoint Render at it. Rejected: that puts the fix behind
a **manual dashboard change**, and this project has already been burned by
exactly that failure mode — `render.yaml` was found never to have been applied
to the live service (2026-07-26), so its `startCommand` and `healthCheckPath`
differed from what was actually running. Making the *existing, already
wired-up* path the cheap one means the fix lands entirely on deploy, with no
step anyone can forget. The naming also matches the Kubernetes
`livez`/`readyz` convention, so an operator reads it correctly without asking.

**D2 — the regression guard is `assertNumQueries(0)`, not "the view no longer
calls `cursor()`".**
Deleting the query from the view body is *not* evidence that a `/healthz`
request costs zero round-trips. Any middleware in the stack could issue its own
— `SessionMiddleware` and `AuthenticationMiddleware` are both lazy today, but
that is a property of the current stack, not a guarantee, and a future
middleware would silently re-arm the whole problem. The test asserts the
property the CU budget actually depends on: **the entire request issues zero
queries.** Per this repo's habit with retargeted guards, it gets broken
deliberately once to prove it goes red.

**D3 — `/readyz` is checked once per deploy, and that is the only scheduled
reader.**
Deploy time is the right cadence for a readiness check: it answers "did this
build come up able to reach its database" exactly when that can newly be false,
then stops. Cost is one 5-minute suspend window per release — noise against a
100 CU-hour budget.

**D4 — what we give up, stated plainly rather than implied.**
Between deploys there is **no automatic alert for "app is up, database is
unreachable"**. That is a real reduction and should not be dressed up. Three
things bear on how much it matters:

- The DB check **did not actually work** during the one outage it was written
  for. On 2026-07-26 a blocked connect is not an exception, so `healthz`'s own
  `except Exception` never fired and the probe hung instead of answering 503.
  What made that path real was bounding `connect_timeout`, not the query.
- Now that connect *is* bounded, a database outage surfaces as a prompt
  `OperationalError` on real traffic, which Sentry already captures.
- If the gap proves real, the cheap fix is a **slow** second UptimeRobot
  monitor on `/readyz` — hourly costs ~15 CU-hr/month (24 wakes × 5-minute
  suspend window × 0.25 CU), half-hourly ~30. Deliberately **not** added now:
  it trades a third of the budget for a check whose value is unmeasured, and
  it is one dashboard entry to add later if wanted.

**D5 — raise `DB_CONNECT_TIMEOUT` to 15 before the compute is first allowed to
sleep.**
`config/database.py` is explicit that **no cold resume was ever timed**,
precisely because the poll keeps the compute warm. This plan removes the thing
keeping it warm, so cold resumes become real for the first time and the 5-second
default becomes an untested bound on the one path that newly exercises it. A
resume slower than 5 s would turn a quiet-period first page load into a 503.
Raise it in the dashboard first, measure a real cold resume, then decide whether
to bring it back down — the module's own instruction, followed.

**D6 — no feature flag, deliberately.**
Infrastructure with no user-visible surface. Rollback is redeploying the
previous tag, and `DB_CONNECT_TIMEOUT` is independently dialable without a
deploy. Recorded here so the choice is deliberate (lifecycle Stage 6).

**D7 — `/readyz` is deliberately left *traced*, inverting Plan 17 D3 for it.**
Plan 17 dropped `/healthz` from tracing because a high-volume bare 200 says
nothing and drags every p50 widget toward zero. `/readyz` is the opposite on
both counts: once per deploy, and — now that resumes are real — its latency is
the single most informative number on the site, because it is the one request
guaranteed to pay the cold-connect cost. Keeping it sampled is how D5's
"measure a real cold resume" gets answered without extra tooling.

**D8 — the Neon 5-minute suspend timeout is left alone.** Configuring it is a
paid-plan feature; on the free plan the 5-minute default is what we get. Noted
so nobody goes looking for the knob.

**D9 — the deploy gate falls back to `/healthz` on a 404 (added in review).**
Moving `HEALTH_URL` to `/readyz` silently broke the documented rollback path:
every tag cut before this plan serves 404 there, so
`scripts/release.sh --ref v2026.07.19` would swap Render to the old build
successfully and *then* fail its own health check, telling the operator the
rollback may not be healthy. That is the worst possible time for a false
alarm. The loop now treats "404 from `/readyz`" as "this build predates Plan
23", falls back to `/healthz`, and says out loud that the check just weakened
to liveness-only. Verified both ways against mock builds (see Verification):
the fallback rescues a rollback, and a build where *nothing* returns 200 still
fails the gate. The fallback is marked for deletion once no rollback target
predates Plan 23.

---

## Parked, deliberately

- **A scheduled readiness monitor.** See D4 — revisit if a database outage
  goes unnoticed for long enough to matter.
- **Upgrading to Neon Launch ($19/mo) or moving to Render Postgres.** This plan
  should take usage from ~195 CU-hr/month to comfortably under 100, making the
  spend unnecessary. Revisit if measured usage after a full month still
  approaches the cap.
- **`tcp_user_timeout` / server-side `statement_timeout`.** Still the open gap
  `config/database.py` names (keepalives bound idle sockets, not in-flight
  queries). Untouched here — this plan changes how often we connect, not what
  happens mid-query.

---

## Verification

Done, with real results (2026-08-13):

**The guard goes red when it should.** `assertNumQueries(0)` on `/healthz`, then
the `SELECT 1` re-added to the view to prove the test isn't decorative:

```
FAILED apps/core/tests.py::test_healthz_issues_no_database_queries
  - Failed: Expected to perform 0 queries but 1 was done
```

**Measured against a real Postgres, through the real server**, not just the
test client. `runserver` on the worktree's own database, counting
`pg_stat_database.xact_commit` either side of 20 requests, with a control run
to account for the two `psql` measurement connections themselves:

```
control (0 requests) -> postgres transaction delta: 2
20x /healthz         -> postgres transaction delta: 2     # i.e. 0 from the app
20x /readyz          -> postgres transaction delta: 62    # 3 per request
```

`/healthz` costs the database **nothing**; `/readyz` still does its job. That
is the entire plan in two numbers.

**Both probes over HTTP:**

```
--- /healthz ---   HTTP/1.1 200 OK   {"status": "ok"}
--- /readyz  ---   HTTP/1.1 200 OK   {"status": "ok"}
```

**The rollback fallback (D9), both directions.** The health-check loop was
extracted from `scripts/release.sh` *by line range* — so the thing under test
cannot drift from the real script — and run against two mock builds:

```
# a pre-Plan-23 build: 404 on /readyz, 200 on /healthz
NOTE: .../readyz returned 404 — this build predates Plan 23's readiness probe.
      Falling back to .../healthz, which only confirms the process is serving.
OK — .../healthz returned 200
--- loop exit status: 0 ---            # rollback correctly reported healthy

# a genuinely broken build: nothing returns 200
Attempt 2..6: .../healthz returned 404 — retrying in 15s
ERROR: ... did not return 200 after several retries.
--- loop exit status: 1 ---            # gate is not a rubber stamp
```

**Suite and lint:** 502 passed; `ruff check` clean; `ruff format --check` clean;
`manage.py check` reports 15 issues, all pre-existing `treebeard.E001` warnings
identical on `main` (confirmed by running it there) and unrelated to this change.

**Still outstanding, after deploy** — the only proof that finally matters:
confirm in Neon that the compute reaches `current_state: idle` during a quiet
period, and that `started_at` stops being weeks old.

---

## Release plan

Ships behind no flag (D6), as a normal tagged release via `scripts/release.sh`.

| Phase | Action | Gate | Rollback trigger |
|---|---|---|---|
| 0 | Set `DB_CONNECT_TIMEOUT=15` in the Render dashboard | Value visible on the service; no deploy | — (env-only, revert by clearing) |
| 1 | Deploy the tag | `scripts/release.sh`'s `/readyz` check passes | Health check fails → redeploy previous tag |
| 2 | Confirm scale-to-zero within ~10 min of quiet | Neon shows compute `idle`, `started_at` stops being 18 days old | Compute still never idle → something else polls; re-open the investigation before assuming this plan failed |
| 3 | Watch cold-resume latency for a week | `/readyz` (and ordinary page) traces in Sentry show resume cost; CU-hours trend flat | First-page-load 503s after a quiet period → raise `DB_CONNECT_TIMEOUT` further (no deploy) |

**Who is informed:** maintainer only. No downstream operators or users to
brief; the site's user-visible behaviour is unchanged except that the first
page load after a quiet period is slower by one Neon resume.
