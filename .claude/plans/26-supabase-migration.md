# Plan 26 — Move Postgres off Neon: Supabase, or pay $6

**One line:** Plans 23 and 24 cut Neon compute burn from 6.38 to 1.69 CU-hr/day
and it is still 2.1× more than the free tier allows, so the allowance runs out
around **24 August** and the site goes down until 1 September; move the database
to a host that does not meter compute at all — Supabase's free plan, whose real
price is a backup job we have to own — and decide that trade explicitly against
$6/month for Render Postgres rather than by default.

---

## Background — measured, 2026-08-17T15:57Z

Read straight off the Neon projects API (a control-plane call; unlike SQL it does
not wake the compute), project `dawn-dream-80048612`:

| | |
|---|---|
| `cpu_used_sec` | 318,785 → **88.6 / 100 CU-hr used** |
| burn rate | **1.69 CU-hr/day** (6.38 before Plan 23, 1.92 after it, 1.80 after Plan 24 Tracks A–C) |
| compute awake | **26.4%** of the time (100% before Plan 23) |
| affordable rate for the rest of the month | **0.80 CU-hr/day** |
| projected exhaustion | **~24 August** |
| quota reset | **1 September** |
| database size | **41 MB** (`synthetic_storage_size` 42,940,096 B) |
| region | `aws-ap-southeast-1` — same city as the Render web service |
| Postgres major version | **18** |
| PITR / history retention | `history_retention_seconds: 21600` — **6 hours** |

Two plans of real engineering have moved this from 6.38 to 1.69 and it is still
not enough. That is not a failure of either plan; it is the shape of the cost
model:

```
daily cost ≈ (isolated wake moments) × 5 min × 0.25 CU
```

Queries are nearly free. **Separate moments are what bill.** That identity is
why Plan 23 — deleting a continuous 5-second poll — cut 70%, and why Plan 24 —
removing queries from inside windows that were already open — cut 12%. What is
left is ~740 crawler page-loads a day arriving in bursts separated by 17–60
minute gaps. Each *gap* is the product. There is no further code change that
removes gaps between visits from strangers, so the remaining levers are all
commercial:

- **Neon Launch, $19/mo.** Buys a configurable suspend timeout and a real
  allowance. No migration, no risk, one click. Most expensive.
- **Render Postgres Basic, $6/mo.** Always-on, no idle meter, same region and
  private network as the web service, continuous backups included. Needs a
  migration. (Render's *free* Postgres is not an option — it expires 30 days
  after creation.)
- **Supabase free, $0.** 500 MB database, no compute-hour meter at all, and a
  project pauses only after a week of inactivity. Needs a migration **and** a
  backup job we build and operate ourselves, because the free plan has none.

The 5-minute Neon suspend timeout that makes the arithmetic hurt is fixed on the
free plan and configurable only on Scale (Plan 23 D8 already recorded that
there is no knob to go looking for). And exhausting the allowance does not
throttle: Neon **suspends the compute — open connections drop and new ones
cannot be made.** Every page on this site reads Postgres, so 24 August is an
outage date, not a billing footnote.

### What this plan is not

It is not a rescue plan for the 24 August deadline. The deadline has a $19
answer that carries no risk at all (see D9 and release Phase 0). This plan is
about where the database should live for the next year, and it deliberately
refuses to let a deadline choose that.

### Two findings that change the shape of the work

**1. Neon runs Postgres 18; Supabase runs 17.** So this is a major-version
*downgrade*, and `pg_dump`/`pg_restore` are only supported in the forward
direction — a custom-format dump taken from an 18 server cannot be restored into
a 17 server, and a v17 `pg_dump` refuses to talk to an 18 server at all. Every
mechanic in D7 exists because of this sentence, and it is the one thing that
must be proven on a throwaway target before anything touches production. It is
not Supabase-specific: any destination that is not on 18 has the same problem.

**2. We do not currently have backups.** Neon's history retention on this
project is **six hours**, and there is no dump anywhere else. So "Supabase free
has no backups" is not a regression from a safe position — it is the same gap we
are already living with, and this plan is the moment to close it. Stated plainly
because the naive reading of D4 is "we're giving up backups", and the truth is
the opposite.

---

## Scope

### Track A — settings and connection (code, small)

Almost nothing changes in code, which is the point: `DATABASE_URL` is already
the single seam (`config/settings/base.py`, `prod.py`), and `config/database.py`
already applies `connect_timeout` + keepalives to any Postgres URL.

1. **No settings change is required to connect.** The session-mode pooler URL is
   an ordinary `postgres://` URL; `env.db()` parses it and
   `database.harden_connection` hardens it exactly as it does Neon's.
2. `config/database.py` — the `DEFAULT_CONNECT_TIMEOUT_SECONDS` docstring is
   now false in its central claim (it is a five-paragraph argument about Neon
   cold resumes). Rewritten, not deleted: the *bound* still matters, the
   *reason* changes (D2).
3. `apps/core/tests.py` / `config/test_database.py` — no new behaviour to guard
   here; the existing `/readyz` tests already assert the property that matters
   ("this build can reach its database").

### Track B — backups (the load-bearing track)

A daily logical dump of the whole database to a **private** Cloudflare R2
bucket, with 30 days of retention, run as a scheduled job off the web service.
This is the track that makes Supabase free honest; without it, D9's answer flips
to "pay the $6". Details in D4.

### Track C — cutover (operational, no deploy)

Dry run against a throwaway target, then a short maintenance window: dump →
restore → verify (Track D) → swap `DATABASE_URL` in the Render dashboard →
`/readyz`. Mechanics in D7.

### Track D — verification, before the swap and after it

Row counts per table, `Page.find_problems()`, the real reader pages rendered
against the new database, `migrate --check`, `/readyz`. Spelled out in
**Verification** below.

### Track E — docs made true again

A stale doc is a defect (lifecycle Stage 4). This change falsifies statements in
five places:

- **`CLAUDE.md`** — the Observability section's whole "`/healthz` must never
  touch the database" paragraph is argued from Neon's CU meter, and its
  corollary ("Neon cold resumes are real, so production needs
  `DB_CONNECT_TIMEOUT=15`") loses its premise. The *rule* survives on other
  grounds and must not be softened — see D3.
- **`config/database.py`** — as Track A.
- **`docs/deploying.md`** — the environments table names "Neon Postgres", the
  `/healthz` vs `/readyz` table explains itself in CU-hours, the
  `DB_CONNECT_TIMEOUT` table says `15` is "required in production … headroom for
  a Neon cold resume", and first-time setup step 1 is "create a Neon project".
- **`render.yaml`** — the header comment, the `region: singapore` comment ("Neon
  runs in aws-ap-southeast-1") and the `DATABASE_URL` / `DB_CONNECT_TIMEOUT`
  comments. Remember this file **is not reaching the live service** (2026-07-26):
  editing it is documentation, and the dashboard is where the change lands.
- **`README.md`** (the repo's own front page) — line 101 names the
  [Neon](https://neon.tech/) Postgres database directly. The repo is public, so
  this is the one publicly-readable place the host is named.
- **`.claude/plans/README.md`** — this plan's row.

Separately noted, not fixed here: `render.yaml` never gained
`CACHE_PAGE_SECONDS` / `CACHE_DIR` when Plan 24 shipped them, so the blueprint
has drifted a third time.

---

## Decisions

**D1 — connect through the Supavisor **session-mode** pooler (port 5432), not
the direct connection and not transaction mode.**

The direct connection is not available to us at all: on new Supabase projects
`db.<ref>.supabase.co` resolves to **IPv6 only**, the IPv4 add-on that would
change that is **Pro-plan and above**, and **Render has no IPv6 egress** — this
is a well-documented dead end that Render's own community threads are full of.
So the shared pooler is the only reachable endpoint on a free project, and both
of its modes are IPv4 on every tier. The choice is session vs transaction:

```
postgres://postgres.<project-ref>:<password>@aws-<n>-ap-southeast-1.pooler.supabase.com:5432/postgres
                                                                                     ^^^^ session mode
```

(Copy the exact host from the dashboard — the `aws-<n>-` prefix is
project-specific. Transaction mode is the same host on **6543**.)

Session mode, for three reasons, in ascending order of importance:

1. Supabase's own guidance points persistent servers, migrations and `pg_dump`
   at a session-level connection; transaction mode exists for serverless
   functions that open a connection per invocation. This app is one long-lived
   container.
2. Transaction mode would buy nothing. Plan 23's `pg_stat_activity` sampling saw
   **exactly one** application backend at a time, so with `CONN_MAX_AGE=60` this
   app holds on the order of one Postgres connection. `render.yaml` declares no
   `--workers` flag and no `WEB_CONCURRENCY`, which would make gunicorn's
   default of one worker consistent with that measurement — but **that file is
   not the live service** (2026-07-26), and its `startCommand` is one of the two
   fields already caught diverging, so the claim rests on the measurement, not
   the blueprint. Either way, multiplexing solves a problem this app does not
   have. Confirm the live worker count from the dashboard if a future change
   ever depends on it.
3. It is the closest behavioural match to what runs today, and the entire job of
   a cutover is to change the host without changing anything else.

**The prepared-statement hazard is real in general but does not apply here, and
the reason matters more than the conclusion.** Transaction mode does not support
prepared statements — but **Django 5.2 already disables them by default**:
`django/db/backends/postgresql/base.py` sets `prepare_threshold = None` with the
comment *"Disable prepared statements by default to keep connection poolers
working"*, and this repo sets neither `prepare_threshold` nor
`server_side_binding` in `OPTIONS` (`config/database.py` sets only
`connect_timeout` and the four keepalives). Verified against the installed
Django 5.2.16, not recalled. So transaction mode would probably *work*; it is
rejected on the three grounds above, and anyone who later reaches for it should
know that prepared statements are not the blocker they will read about
elsewhere. What *would* bite in transaction mode is session state — Django
issues `SET TIMEZONE` in `init_connection_state`, which is a session-level
statement whose effect is not guaranteed to survive to the next transaction.

**D2 — `DB_CONNECT_TIMEOUT` stays at 15 through the cutover; `CONN_MAX_AGE`
stays at 60. Neither changes in the same move as the host.**

The *reason* for 15 disappears — Plan 23 D5 raised it because Neon cold resumes
became real, and Supabase's compute does not scale to zero, so the first request
after a quiet period no longer pays a resume. But a connect timeout is a
**ceiling, not a delay**: when connects are fast, 15 costs exactly nothing. What
it does cost is 10 extra seconds of worker-blocking during a genuine network
fault — bounded well inside gunicorn's `--timeout 120`, so the 2026-07-26
failure mode stays fixed either way. Against that: the pooler is a new connect
path whose latency we have never measured, through a hop the direct connection
did not have. Changing the host and tightening the bound on the same day would
leave us unable to say which one caused a 503.

So: leave it at 15, read the real number off `/readyz` traces in Sentry (which
Plan 23 D7 deliberately left sampled for exactly this purpose), and only then
decide whether to clear the variable and take the code default of 5. `parse_connect_timeout`'s
soft-fail behaviour means clearing it is safe.

`CONN_MAX_AGE=60` is kept for the same "change one thing" reason, plus one
positive: with no CU meter, connection churn no longer costs money, so 60 is now
purely a latency choice — and it is a good one. Zero would pay TCP+TLS on every
request; much higher would hold a pooler client slot open for longer with
nothing to gain.

**D3 — Plan 24's page cache stays, and `/healthz` still never touches the
database. Both keep their tests. The reasons change; the rules do not.**

The cache was built to keep Neon's compute asleep, and that reason is now gone.
Delete it anyway and three things are lost:

1. **Latency.** Measured in Plan 24 through the real app: a cold request costs
   16 database transactions, twenty warm ones cost **0**. Every one of those
   round-trips crosses to a managed database — now through one more hop than
   before (D1's pooler). A cache hit skips the view and Wagtail's entire page
   lookup.
2. **The public site keeps serving when the database does not.** `PageCacheMiddleware`
   is innermost, so a hit never reaches the view; `SessionMiddleware` and
   `AuthenticationMiddleware` are lazy and issue nothing for an anonymous
   visitor; `RedirectMiddleware` queries only on a 404. Plan 24 verified this
   accidentally and precisely — two full page loads of `/en/` returned 200 in
   0.66 s and 0.26 s **while the Neon compute was suspended**, with zero
   database contact. That is a real availability property that has nothing to do
   with Neon's billing, and it is worth more on a free-tier database, not less.
3. **A tested guard.** `apps/core/test_middleware.py`'s cache correctness rules
   (never a logged-in user's page, never a response that sets a cookie) are the
   kind of thing you do not casually re-derive.

Stated against itself, honestly: a cache **can mask** a database outage from a
casual look at the home page. That is what `/readyz` and Sentry are for, and it
was already true before this plan.

The same argument protects `/healthz`. Its zero-query rule now has no CU-hour
justification, but it keeps two better ones: a liveness probe that depends on a
dependency cannot distinguish "the process is wedged" from "the database blipped"
(and Render restarts the instance on a failed health check — restarting the app
because Postgres hiccuped is a way to turn a blip into an outage). `CLAUDE.md`
must be edited to say *that*, because a rule whose only stated reason has expired
is a rule the next session deletes.

**D4 — a daily `pg_dump` to a private R2 bucket, run as a Render cron job in
Singapore, 30 days retained. Not a GitHub Actions workflow.**

This is the load-bearing risk and the honest cost of "free". Supabase's own
documentation is unambiguous: the free plan has **no automated daily backups**,
backups cannot be downloaded, and *"we recommend that free tier plan projects
regularly export their data … and maintain off-site backups."* PITR is a Pro
add-on starting around $100/month, so it is not in this conversation.

What is at stake is worth being precise about, because the two halves differ:

- **`DeidentifiedVisit` rows and `DailyAggregate` are recoverable in principle.**
  The clinic's own software still holds the source records and can re-export a
  day; ingest is re-runnable and `recompute_daily_aggregates` is non-destructive
  by design (Plan 22 D2). Recovery would be days of tedium, not a permanent
  loss.
- **Wagtail content is not recoverable from anywhere.** Pages, newsletter and
  camp bodies, revisions, the redirects Plan 21 created, `ContactBankSettings`,
  snippets, users. There is no second copy of any of it. **This is the thing the
  backup is for.**

Mechanism, and why each part:

- **`pg_dump` of the whole database, plain SQL, gzipped**, named
  `tkc-YYYY-MM-DD.sql.gz`. A logical dump is restorable into *anything*
  including a different provider and a different major version, which is exactly
  the property a backup should have — a provider-specific snapshot is a hostage,
  not a backup.
- **Destination: a new, private R2 bucket** in the account that already holds
  media. Not a new vendor, credentials already of a shape this repo handles
  (`MEDIA_S3_*` in `config/settings/prod.py`), and R2's free tier is 10 GB
  against ~2–5 MB gzipped per day. **It must NOT be the media bucket**:
  `docs/deploying.md` records that one as deliberately public
  (`querystring_auth: False`, `default_acl: None`) so *"any object in it is
  reachable by anyone who has or guesses its URL"*. A dump of de-identified
  clinical free text in a public bucket would be the worst mistake this plan
  could make.
- **Where it runs: a Render cron job**, `region: singapore`, same repo and
  build as the web service, minimum **$1/month**. Chosen over a free GitHub
  Actions schedule deliberately and on privacy grounds: this repo is
  **public**, so workflow logs are world-readable (a dump must never be an
  artifact, and a connection string must never be echoed), and a GitHub-hosted
  runner would pull a full copy of the de-identified clinical text onto a
  US-region machine that is not otherwise a processor for this project. $1
  keeps the data in the same city it already lives in and off a public CI
  surface. If the maintainer would rather not add a service, the GitHub
  Actions variant is documented in "Parked" with its cost stated as a privacy
  cost, not zero.
- **Retention 30 days**, deleted by the same job. Long enough that a corruption
  noticed a fortnight late is still recoverable; short enough to be free.
- **It must fail loudly.** A backup job nobody watches is theatre. The job exits
  non-zero on any failure, which surfaces in Render's dashboard and its
  notification email; if that proves too quiet, the follow-up is a Sentry
  cron monitor — deliberately not added on day one, because Sentry check-ins are
  a *new event kind* and `CLAUDE.md`'s observability note is explicit that each
  new kind needs its own scrub hook rather than inheriting `before_send`'s.
- **A restore drill is part of shipping this, not a follow-up.** An untested
  backup is an assumption. The drill: take yesterday's object, restore it into a
  scratch database, and run the Track D verification against it. Done once at
  release, then annually or whenever the schema changes shape.

**D5 — no keepalive service. The nightly backup is the keepalive.**

The free plan pauses a project after ~7 days of inactivity (Supabase's wording
is *"applications … that exhibit low activity in a 7-day period"* — softer than
"no activity", so treat 7 days as a ceiling on our margin, not a promise). Two
independent things already prevent it:

1. **Real traffic.** Plan 24 measured 2,219 successful page loads over 3 days
   (~740/day). The page cache absorbs many, but its TTL is 3 hours and it is
   cleared on every deploy, so a day with zero database contact is not a shape
   this site produces.
2. **The Track B backup connects every night** and reads every row.

Adding a third thing to solve a problem two things already solve would be
cargo-culted infrastructure. Two honest caveats: the coupling means a silently
broken backup job takes the keepalive with it (mitigated by D4's fail-loudly
requirement), and the consequence is mild — a paused free project is resumed
from the dashboard and **loses no data**. Unpark condition: if Supabase pauses
the project even once, or if traffic ever falls to nothing for a week, the
cheapest honest keepalive is one extra `psql -c 'select 1'` line inside the
existing nightly job — not a new service and not a monitor pointed at
`/readyz`, which Plan 23 D3 and `docs/deploying.md` both warn against for
reasons that survive this migration in spirit (a probe that exists to be polled
should not be the thing that keeps a dependency awake).

**D6 — no doc names the database host today, so the published privacy notice
does not become untrue; but Plan 25 is in flight and this is where that gets
decided.**

Checked rather than assumed. "Neon" appears in **20 files**, among them
`CLAUDE.md`, `render.yaml`, `docs/deploying.md`, six plan files,
`config/database.py`, `config/observability.py`, `apps/core/middleware.py`,
`scripts/release.sh` and their tests — and **every occurrence is engineering
documentation, a docstring or a code comment**. In particular nothing rendered
on the website names it: no template matches, and `apps/core/views.py`'s two
mentions are inside docstrings, not inside the `ROBOTS_TXT` body it serves. The
one publicly-readable mention is the repo's own `README.md` (the repo is
public), which Track E updates.

**Plan 25 (`plan/25-privacy-notice`, branched off `main`, not yet merged) is the
one that could change that, and it interacts with this plan in three concrete
ways.** Read from that branch:

1. **Its notice does not name the database host, and that is a deliberate
   scoping choice, not an omission.** Its "outside services involved" section
   enumerates *"four, and no more"* — Umami, Sentry, Cloudflare, and the Google
   Maps embed — and the template's own header comment defines the scope as
   *"the third parties a visitor's browser talks to"*. The section on what is
   kept describes the `DeidentifiedVisit` fields in detail and says nothing
   about where the rows physically sit. Only Sentry gets a region ("Sentry's
   European region"). **So swapping Neon for Supabase falsifies no published
   sentence.**
2. **Its guard test cannot catch this change, and must not be trusted to.**
   `test_privacy_notice_names_exactly_the_third_parties_that_are_wired` scans
   `templates/**`, `apps/**/templates/**` and `config/settings/*.py` for
   installation markers — `cloud.umami.is`, `sentry_sdk.init`,
   `storages.backends.s3.S3Storage`, `map_embed_url` and six not-yet-wired
   trackers. A database host lives in an environment variable, matches no
   marker, and the test stays green in both directions. Anyone reading "tests
   fail the build if the software starts collecting something this page does not
   describe" should know this is outside that guarantee.
3. **It is a decision for the maintainer, not for this plan.** Plan 25 D1 has
   North West Data Products Ltd (England and Wales, company 17388764) as a
   controller in its own right for part of this site, and the notice already
   discloses a *region* for Sentry — so whether to name the data host and its
   region is a live question of exactly the same kind, and it is the maintainer's
   to answer. What this plan can state as fact: **the region does not change.**
   Neon is `aws-ap-southeast-1`; the Supabase project is to be created in
   Singapore, the same region the Render service already runs in. So the answer
   is not urgent, and it does not gate the cutover.

Against `CLAUDE.md`'s invariants: no raw PHI is persisted anywhere, so no raw
PHI moves. What moves is `DeidentifiedVisit` (including the seven free-text
clinical columns, whose sensitivity Plan 25's notice describes better than any
summary here would), the aggregates, and all Wagtail content — to a new
sub-processor, in the same region, with the same access model (one secret in the
Render dashboard). Invariant #2 is untouched: a database host is not a model
call.

**Mechanical note, since both branches are open:** Plan 25 and this plan both
add a row to `.claude/plans/README.md`. Whichever merges second resolves a
trivial conflict; neither should rebase the other.

**D7 — cutover is a plain dump-and-restore in a short window, dry-run first,
and the 18 → 17 downgrade is what the dry run exists to prove.**

41 MB does not justify logical replication, a dual-write period, or any other
zero-downtime machinery. It justifies a quiet hour.

The version gap is the whole difficulty. `pg_dump`/`pg_restore` support the
forward direction only; a v17 `pg_dump` refuses an 18 server outright, and a
v18 custom-format dump is not loadable by a v17 `pg_restore`. So:

- **Primary mechanic:** dump with the **v18** client in **plain SQL**, restore
  with `psql`. Plain SQL is text a v17 server can execute, and neither Django
  5.2 nor Wagtail 7.4 emit PG18-only DDL — but "should work" is not "works", and
  proving it is the dry run's entire job.
  ```
  pg_dump "$NEON_URL" --schema=public --no-owner --no-privileges \
      --format=plain --file=tkc.sql
  psql "$SUPABASE_SESSION_URL" --single-transaction \
      --set ON_ERROR_STOP=on --file=tkc.sql
  ```
  `--schema=public` because a Supabase project's `postgres` database already
  owns `auth`, `storage`, `extensions` and `realtime` schemas that are none of
  our business. `--no-owner --no-privileges` because Supabase's `postgres` role
  is not a superuser and cannot chown to `neondb_owner`. `--single-transaction`
  with `ON_ERROR_STOP` so a failed restore leaves **nothing** behind rather than
  half a schema — a half-restored database that then verifies "mostly fine" is
  the failure worth engineering against.
- **Documented fallback if that dump will not load:** let Django build the
  schema on 17 (`manage.py migrate` against the empty project), then copy data
  only. This works without `--disable-triggers` (which would need superuser)
  because **Django creates every Postgres FK as `DEFERRABLE INITIALLY
  DEFERRED`** — verified in `django/db/backends/postgresql/operations.py` — so a
  single-transaction data load is insensitive to table order. It costs one extra
  step: `migrate` writes its own rows into `django_migrations`,
  `django_content_type` and `auth_permission`, so every table in `public` must
  be truncated before the data load or the load hits duplicate keys.
- **Dry run target:** a second free Supabase project (the free plan allows two),
  thrown away afterwards. It costs nothing, it is the same Postgres version as
  the real target, and it lets the whole sequence including Track D verification
  run with production still serving.
- **The window:** the only writers are staff uploads and Wagtail edits, both
  behind a login, and anonymous page views write nothing. So "do not upload or
  publish between the dump and the swap" is a sufficient control, and no
  read-only mode needs building. The window is bounded by the swap, not the
  dump: **anything written after the dump and before the swap is lost.** Pick a
  Karachi-night hour and tell the one person who can write.
- **The swap:** update `DATABASE_URL` in the Render dashboard. Render
  auto-redeploys on an environment change (observed in Plan 23's own Phase 0),
  and `preDeployCommand` runs `migrate --no-input`, which is a free extra check:
  against a correctly restored database it is a **no-op**, and if it announces
  migrations to apply, the restore lost `django_migrations` and the swap should
  be reverted rather than reasoned about.

**D8 — rollback is putting the old `DATABASE_URL` back, and it has an expiry
date that decides the schedule.**

The Neon project is **not deleted** at cutover, and not for at least a full
month afterwards. But the rollback is only real while Neon can serve
connections, and its compute suspends the moment the allowance is gone:

- **Cut over before ~24 August** and the rollback lever works — that is the
  whole reason to do this before the deadline rather than after it.
- **Between exhaustion and 1 September there is no rollback**, because the thing
  we would roll back to is off. Do not schedule the cutover into that window.
- **From 1 September the lever comes back**, the quota having reset.

The second half of rollback is data, and it is honest rather than clean: writes
made on Supabase after the cutover are not on Neon. Mitigation is the same as
D4's — a day's export can be re-uploaded, Wagtail edits made in that window
cannot. So the rollback decision is cheap for the first hours and gets expensive
once someone publishes. Roll back fast or not at all.

**D9 — Supabase over $6 Render Postgres, on one condition; and here is the
honest case against.**

The condition: **Track B ships with the cutover, not after it.** Without a
working, drilled backup, Supabase free is not cheaper than Render Postgres —
it is worse and cheaper-looking, because $6 buys exactly the thing Supabase free
makes you build.

The case against Supabase, stated as strongly as it deserves, because it is
close:

- Render Postgres Basic has **continuous backups with point-in-time recovery**
  (a 3-day window on a Hobby workspace, 7 on Pro — read the live workspace plan
  rather than assuming which applies), plus downloadable logical backups from
  the dashboard. Managed, monitored, zero code.
- It sits in the same region **and on the same private network** as the web
  service — no public-internet hop, no IPv6 dead end, no pooler mode to reason
  about, no session-vs-transaction footgun for a future session to step in.
- It deletes the whole category of work this plan is made of: no backup job to
  own, no restore drill to remember, no 7-day pause, no 500 MB ceiling, no
  connection-mode decision.
- The real gap is **$5/month**, not $6, once D4's $1 cron job is counted. $60 a
  year. `CLAUDE.md` budgets *"~US$20–30/month all-in"* and the project currently
  spends about $7, so it fits the stated budget with room to spare.
- Plans 23, 24 and now 26 are all the same bug wearing different hats: a free
  tier whose cost model does not match this workload. Three plans of engineering
  is not obviously cheaper than $60.

The case for Supabase, which is why this plan proceeds:

- The money is donated. This is a Zakat/Sadaqa-funded not-for-profit, and a
  dollar not spent on hosting is a dollar spent on patients. "It fits the
  budget" is a weaker argument here than it would be anywhere else.
- **500 MB against 41 MB is not a tight fit.** At the observed ingest rate —
  tens of visit rows a day, Plan 24's own 16-90/day figures — the ceiling is
  years out, and it is the same 512 MB ceiling Neon's free plan already
  imposes on this project today. Nothing narrows.
- **No compute meter at all** is a categorically better fit than a bigger
  allowance. It ends the class of problem rather than raising its bound, which
  is more than $19 Neon Launch buys.
- The backup job is **work worth doing regardless**. Today's backup story is six
  hours of Neon history and nothing else (see Background). A provider-independent
  nightly dump in our own bucket is strictly better than what Render's managed
  backups would give us, in the one respect that matters most: it restores
  anywhere, including away from Render.

So: proceed with Supabase, ship Track B in the same release, and treat the
decision as reversible — Render Postgres remains a $6 fallback for which Tracks
A, C, D and E are almost entirely reusable, and only D1's pooler reasoning and
Track B's necessity fall away. **If the maintainer would rather not own a backup
job at all, that is a legitimate reading of the same evidence and the answer is
Render Postgres Basic.** Release Phase 0 puts that decision where it belongs:
before any of the work.

**D10 — no feature flag, deliberately.**
There is no user-visible surface and no partial state to flag. The rollback
lever is an environment variable and a redeploy (D8), which is what a flag would
have provided. Recorded so the choice is deliberate (lifecycle Stage 6),
matching Plan 23 D6.

---

## Verification — what must be true before the swap, and after it

Specified here; run during Track C. Every check is against the **new** database,
and the first four run during the dry run too, when nothing is at stake.

**1. Row counts per table, exact, both sides.** Not `pg_stat_user_tables`
estimates — `n_live_tup` is an approximation and this is the one check that
proves nothing was dropped. Generate the query from the catalogue so no table
can be forgotten:

```sql
SELECT format('SELECT %L AS t, count(*) FROM %I.%I', tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
```

Run the generated `UNION ALL` on Neon and on Supabase and diff. Pass condition:
**identical, every table, including the ones nobody thinks about** —
`wagtailcore_pagerevision`, `wagtailcore_pagelogentry`,
`wagtailredirects_redirect`, `django_content_type`, `auth_permission`,
`django_migrations`.

**2. `manage.py migrate --check`** against the new database. Run it with
`config.settings.dev` and `DATABASE_URL` pointed at Supabase, not with prod
settings: importing the prod module demands every production secret
(`SECRET_KEY`, `ALLOWED_HOSTS`, all five `MEDIA_*`) before it will even boot —
the same property `config/database.py`'s docstring cites as its reason for
existing. It must report nothing to apply. A pending migration here means the restore lost
`django_migrations`, which would make the next deploy's `preDeployCommand` try
to rebuild a schema that already exists.

**3. Wagtail page-tree integrity: `Page.find_problems()` must return empty.**
The precedent is Plan 21, where it caught `numchild` corruption from a cascade
nobody predicted. A dump/restore should not be able to break `path`/`depth`/
`numchild`, and this is how that stops being a belief. Run it in
`manage.py shell` pointed at the new database.

**4. The real reader pages render, through a real server, against the new
database.** Not the test client — the lifecycle's own rule is to exercise the
change through the entry point a real visitor uses. `runserver` against the
Supabase URL, with the page cache disabled (`CACHE_PAGE_SECONDS=0`) so every
request actually reaches Postgres, and fetch:

- `/en/` — the home page, including the live impact-stats band, which reads
  `DailyAggregate`;
- a **daily report page** — the deepest read path (aggregates, free-text
  summary, revenue surfaces);
- `/en/reports/` and `/en/reports/dashboard/` — the funding-mix chart and the
  range dashboard, both of which aggregate across many rows;
- `/en/newsletters/` and one issue — images and documents, which also proves the
  R2 media URLs survived;
- `/admin/` login and one page's edit view — the write path, and the only way to
  see that revisions came across.

Paste the real output. A 200 with a silently empty stat band is a failure, so
check the numbers match what production shows for the same pages.

**5. `/readyz` returns 200 after the swap.** This is the gate that matters
because it is the one the tooling shares: `scripts/release.sh` polls `/readyz`
for up to 10 minutes as its post-deploy gate (Plan 23 D10 sized that window),
so a database the app cannot reach fails every future release, not just this
one. Note that an environment-variable swap is **not** a tagged release, so
`release.sh` is not what runs here — check `/readyz` by hand, then treat the
*next* ordinary release as the real end-to-end proof of the deploy path.

**6. The restore drill (Track B).** Fetch the newest object from the backup
bucket, restore it into a scratch database, and run checks 1–3 against it. A
backup that has never been restored is not a backup.

**7. After the swap, watch for a week.** `/readyz` and page traces in Sentry for
connect latency through the pooler (which is D2's input), Render logs for
`OperationalError`, and the Supabase dashboard for connection counts — the
number should sit near one, and if it does not, something about D1's reasoning
is wrong and worth knowing.

---

## Parked, deliberately

- **Render Postgres Basic at $6/month.** The better engineering answer on every
  axis except price (D9). Unpark if the Track B backup job proves to be work we
  do not want to own, if a restore drill fails, or if Supabase's free plan
  changes shape under us.
- **Neon Launch at $19/month.** Zero-risk, zero-migration. Unpark as the
  deadline valve (Phase 0) or if this migration has to be abandoned mid-flight.
- **The GitHub Actions variant of the backup job.** Free instead of $1, at the
  cost of pulling de-identified clinical text onto a US-region runner attached to
  a **public** repository. Unpark only if the Render cron job is unavailable, and
  if so: never as an artifact, always straight to R2, and never echo the
  connection string into a world-readable log.
- **A Sentry cron monitor on the backup job.** The right long-term answer to
  "did the backup run", but check-ins are a new Sentry event kind and
  `CLAUDE.md` requires asking what payload a new kind carries before enabling
  it. Unpark once the job has a track record and that question has been
  answered.
- **Lowering `CACHE_PAGE_SECONDS` now that cost is not the reason for it.**
  Fresher content is a real benefit and compute is no longer the constraint —
  but the publish-signal invalidation (Plan 24 D4) already handles the case
  people actually notice. Unpark if a content change is ever observed to lag.
- **`tcp_user_timeout` / server-side `statement_timeout`.** Still the open gap
  `config/database.py` names, still untouched, and now with one more hop in
  front of it than when Plan 23 parked it.
- **Supabase's other products** (Auth, Storage, Realtime, the REST API). We are
  buying a Postgres host and nothing else. Wagtail owns auth, R2 owns media.
  Unpark: no condition — this is a "no", not a "later".

---

## Release plan

No flag (D10). This ships as **two changes with different mechanisms**: a
docs-and-comments PR that goes out with an ordinary tagged release, and a
dashboard environment-variable swap that is not a deploy at all.

| Phase | Action | Gate | Rollback trigger |
|---|---|---|---|
| 0 | **Maintainer decision (D9):** Supabase + own the backup job, or $6 Render Postgres and skip Tracks B and D6's pooler reasoning. Also decide whether the 24 Aug deadline gets the $19 Neon-Launch valve so the cutover is not done in a hurry | An answer, recorded in this file | — |
| 1 | Create the Supabase project in **Singapore**, strong password, copy the **session-mode** URI (D1). Create the throwaway second project for the dry run (the free plan's two-project cap is exactly enough) | Both projects exist, **and the session URI connects from an SSH shell on the live Render instance** — not just from a laptop. A laptop may well have IPv6 and so cannot prove the thing D1 depends on, which is that the *instance* can reach the host. See `docs/content-operations.md` for the SSH route | — (nothing live is touched) |
| 2 | **Dry run** the whole of D7 against the throwaway project, then Verification 1–4 against it | The 18 → 17 plain-SQL restore loads clean, counts match, `find_problems()` empty, every page in Verification 4 renders with correct figures | Dry run fails → try D7's fallback mechanic; if that fails too, **stop and take Render Postgres or Neon Launch**. This is the phase that is allowed to end the plan |
| 3 | Ship the docs/comment PR (Track A + E) as a normal tagged release, still pointing at Neon | `scripts/release.sh`'s `/readyz` gate; site renders | Redeploy previous tag |
| 4 | **Cutover** (D7): quiet Karachi-night hour, no uploads or publishes, dump → restore → Verification 1–4 against the real target → swap `DATABASE_URL` in the dashboard (leave `DB_CONNECT_TIMEOUT=15`, D2) | `/readyz` 200; the auto-redeploy's `migrate --no-input` is a **no-op**; home, a daily report and the dashboard all render with the right numbers | Any check fails → put the Neon `DATABASE_URL` back and let it redeploy. **Only available while Neon has CU-hours (D8) — so do not schedule this into the 24 Aug → 1 Sep window** |
| 5 | Ship **Track B**: the backup cron job, then the restore drill (Verification 6) | A dump lands in the private bucket; yesterday's object restores into a scratch database and passes checks 1–3 | Job broken → fix before Phase 6; the site is fine, the safety net is not |
| 6 | Watch a week (Verification 7): pooler connect latency, connection count, Sentry errors, and that the project does not pause | No `OperationalError`s; connect latency in line with today's ~0.5 s; connections ≈ 1 | Sustained connect failures → revert `DATABASE_URL` (from 1 Sep, Neon is available again) |
| 7 | Decide `DB_CONNECT_TIMEOUT` on measured data (D2), and only then delete the Neon project | A number from `/readyz` traces, not a guess | — |

**Keep the Neon project until at least a full billing month after Phase 6**, and
delete it only once a Supabase restore drill has passed. It is the only rollback
target that exists.

**Who is informed:** the maintainer, who is also the only person who can write
to the database and therefore the only person the Phase 4 window depends on. No
downstream operators or users. User-visible behaviour is unchanged; if anything
the first page load after a quiet period gets faster, because nothing is
resuming from zero any more.

---

## Reference material

- Supabase — [connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)
  (direct vs session vs transaction, ports, IPv6), [dedicated IPv4](https://supabase.com/docs/guides/platform/ipv4-address)
  (Pro-plan only), [backups](https://supabase.com/docs/guides/platform/backups)
  (no automated backups on Free; export your own), [going into prod](https://supabase.com/docs/guides/platform/going-into-prod)
  (the 7-day low-activity pause).
- Render — [cron jobs](https://render.com/docs/cronjobs) ($1/month minimum, no
  free instance type), [Postgres backups](https://render.com/docs/postgresql-backups)
  (continuous backups and PITR on paid instances only), and the community thread
  on [Render ↔ Supabase after the IPv6 transition](https://render.discourse.group/t/issues-connecting-render-to-supabase-after-ipv6-transition/24156).
- In-repo — [Plan 23](23-healthz-scale-to-zero.md) (the cost model and the
  `/healthz` split), [Plan 24](24-crawler-load.md) (the cache, and what
  measurement did to two confident predictions), `config/database.py` (the
  connect-timeout argument this plan rewrites), `docs/deploying.md` (the deploy
  gate and every secret involved), and `plan/25-privacy-notice` (D6).
