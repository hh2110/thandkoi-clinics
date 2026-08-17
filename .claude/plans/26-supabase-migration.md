# Plan 26 — Move Postgres off Neon to Render Postgres

**One line:** Plans 23 and 24 cut Neon compute burn from 6.38 to 1.69 CU-hr/day
and it is still 2.1× more than the free tier allows, so the allowance runs out
around **24 August** and the site goes down until 1 September; stop engineering
around a free tier whose cost model does not fit this workload and move the 41 MB
database to **Render Postgres Basic at $6/month** — same provider, same region,
private network, Postgres 18 on both ends, and point-in-time recovery included.

> **Renamed and reversed, 2026-08-17, before any implementation.** This plan was
> drafted as a migration to Supabase's free plan, with a section arguing honestly
> that $6 Render Postgres was the better answer on every axis except price. The
> maintainer read that section and took the $6. So the argument that was the
> counter-argument is now the plan, Supabase is the parked alternative, and a
> large amount of drafted complexity — a connection-pooler decision, a
> major-version downgrade procedure, a truncate-and-reload decision, a backup job
> and a keepalive — is **deleted rather than kept**, because none of it is load
> bearing any more. What survives as a note survives because it is a trap worth
> having documented, not because it was hard to write.
>
> The file keeps its `26-supabase-migration` name so it stays consistent with the
> open PR and its branch (`plan/26-supabase-migration`) — nothing but the roadmap
> row links here, so rename it if you would rather the filename matched the
> decision; the branch name cannot follow without abandoning PR #170.

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
| region | `aws-ap-southeast-1` |
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
minute gaps, and each *gap* is the product. There is no third code change that
removes the gaps between visits from strangers.

Exhausting the allowance does not throttle: Neon **suspends the compute — open
connections drop and new ones cannot be made.** Every page on this site reads
Postgres, so 24 August is an outage date, not a billing footnote.

### Why this stopped being an optimisation problem

Plans 23, 24 and this one are the same bug wearing three hats: **a free tier
whose billing unit does not match this workload.** A site with fifteen human
visitors a day cannot be made cheap on a meter that charges for five minutes of
wakefulness per unrelated crawler visit — the only winning move is a host that
does not meter wakefulness. Three plans of engineering is not cheaper than $6.

The current spend is about **$7/month** (one Render Starter web service; Neon
free, R2 free). This takes it to about **$13/month**, against `CLAUDE.md`'s
documented budget of **~US$20–30/month all-in**. It fits, with room left.

### One thing worth recording about today's setup

**We do not currently have backups.** Neon's history retention on this project is
**six hours**, and there is no dump anywhere else. So the move is a strict
improvement on that axis rather than a trade: Render Postgres includes
point-in-time recovery on every paid instance (D4).

---

## Scope

### Track A — connection and settings (code, small)

Almost nothing changes, which is the point: `DATABASE_URL` is already the single
seam (`config/settings/base.py`, `prod.py`), and `config/database.py` already
applies `connect_timeout` + keepalives to any Postgres URL.

1. **No settings change is required to connect.** Render's internal connection
   string is an ordinary `postgres://` URL; `env.db()` parses it and
   `database.harden_connection` hardens it exactly as it does Neon's.
2. `config/database.py` — the `DEFAULT_CONNECT_TIMEOUT_SECONDS` docstring is a
   five-paragraph argument about Neon cold resumes and is about to be false in
   its central claim. Rewritten, not deleted: the *bound* still matters, the
   *reason* changes (D2).

### Track B — backups: nothing to build

Point-in-time recovery is included on paid Render Postgres (D4), so this track
is a verification step, not an implementation one. The off-provider nightly dump
that an earlier draft of this plan made a precondition is **parked** — see
"Parked, deliberately".

### Track C — cutover (operational, no deploy)

`pg_dump` → `pg_restore` → verify (Track D) → swap `DATABASE_URL` in the Render
dashboard → `/readyz`. Mechanics in D7. Both ends are Postgres 18, so this is
the vendor-standard path with no cleverness in it.

### Track D — verification, before the swap and after it

Row counts per table, `Page.find_problems()`, the real reader pages rendered
against the new database, `migrate --check`, `/readyz`, and proof that recovery
actually exists. Spelled out in **Verification** below.

### Track E — docs made true again

A stale doc is a defect (lifecycle Stage 4). This change falsifies statements in
six places:

- **`CLAUDE.md`** — the Observability section's `/healthz` paragraph is argued
  from Neon's CU meter, and its corollary ("Neon cold resumes are real, so
  production needs `DB_CONNECT_TIMEOUT=15`") loses its premise. The *rule*
  survives on other grounds and must not be softened — see D3.
- **`config/database.py`** — as Track A.
- **`docs/deploying.md`** — the environments table names "Neon Postgres", the
  `/healthz` vs `/readyz` table explains itself in CU-hours, the
  `DB_CONNECT_TIMEOUT` table says `15` is "required in production … headroom for
  a Neon cold resume", and first-time setup step 1 is "create a Neon project".
- **`render.yaml`** — the header comment ("The database is **Neon Postgres** (a
  single, external, managed database), not a Render-managed one"), the
  `region: singapore` comment, and the `DATABASE_URL` comment. This file **is
  not reaching the live service** (2026-07-26), so editing it is documentation
  and the dashboard is where the change lands. Worth noting the blueprint could
  now legitimately *declare* the database, which it never could before.
- **`README.md`** — line 101 names the [Neon](https://neon.tech/) Postgres
  database. The repo is public, so this is the one publicly-readable mention.
- **`.claude/plans/README.md`** — this plan's row.

Separately noted, not fixed here: `render.yaml` never gained
`CACHE_PAGE_SECONDS` / `CACHE_DIR` when Plan 24 shipped them, so the blueprint
has drifted a third time.

---

## Decisions

**D1 — one Render Postgres Basic instance in **Singapore**, connected over
Render's **internal** connection string.**

The database goes in the same region as the web service, which is
`srv-d9ej48n41pts73f1i3p0`, read from the live service rather than from
`render.yaml`: **`region: singapore`**, `plan: starter`, `numInstances: 1`.
Region is immutable after creation for both services, so this is the one
irreversible choice in the plan — get it right at creation.

Use the **internal** URL, not the external one. Same provider and region means
Render offers private networking between them, so the traffic never leaves
Render's network and never crosses the public internet. That is worth stating as
the *reason* rather than a nicety, because it is also what deletes three
decisions an external host forced:

- no connection pooler, and so no session-vs-transaction mode to get wrong;
- no IPv6-vs-IPv4 egress problem;
- no public endpoint to firewall.

> **Historical note, so nobody re-derives it.** The Supabase draft of this plan
> needed a whole decision here: Supabase's direct connection is IPv6-only on new
> projects, the IPv4 add-on is Pro-plan and above, and Render has no IPv6
> egress — so the Supavisor **session-mode** pooler on 5432 was the only
> reachable endpoint, which happened also to be what Supabase's own migration
> guide recommends. If Supabase is ever unparked, that is the answer, and the
> reason transaction mode was rejected is *not* the prepared-statement hazard
> everyone cites (Django 5.2 already sets `prepare_threshold = None`,
> "*to keep connection poolers working*") but session state: Django issues
> `SET TIMEZONE` at connection init, which transaction mode does not guarantee
> to preserve.

**D2 — `DB_CONNECT_TIMEOUT` stays at 15 through the cutover; `CONN_MAX_AGE`
stays at 60. Neither changes in the same move as the host.**

The *reason* for 15 disappears — Plan 23 D5 raised it because Neon cold resumes
became real, and a Render Postgres instance is always on, so nothing resumes.
The new connect path is also strictly shorter: same region, private network, no
pooler hop. On the numbers this should be single-digit milliseconds.

But a connect timeout is a **ceiling, not a delay**: when connects are fast, 15
costs exactly nothing, and it stays comfortably inside gunicorn's `--timeout 120`
(confirmed present on the live service, so Plan 15 Track B3's protection is
genuinely in effect). Changing the host and tightening the bound on the same day
would leave us unable to attribute a 503 to either. So: leave it, read the real
number off `/readyz` traces in Sentry — which Plan 23 D7 deliberately left
sampled for exactly this purpose — and then clear the variable to take the code
default of 5. `parse_connect_timeout` soft-fails, so clearing it is safe.

`CONN_MAX_AGE=60` is kept for the same "change one thing" reason. With no CU
meter, connection churn no longer costs money, so 60 is now purely a latency
choice, and a good one: 0 would pay a handshake per request, much higher would
hold a server connection open for no gain.

**D3 — Plan 24's page cache stays, and `/healthz` still never touches the
database. Both keep their tests. The reasons change; the rules do not.**

The cache was built to keep Neon's compute asleep, and that reason is now gone.
Delete it anyway and three things are lost:

1. **Latency.** Measured in Plan 24 through the real app: a cold request costs
   16 database transactions, twenty warm ones cost **0**. A cache hit skips the
   view and Wagtail's entire page lookup.
2. **The public site keeps serving when the database does not.**
   `PageCacheMiddleware` is innermost, so a hit never reaches the view;
   `SessionMiddleware` and `AuthenticationMiddleware` are lazy and issue nothing
   for an anonymous visitor; `RedirectMiddleware` queries only on a 404. Plan 24
   verified this accidentally and precisely — two full page loads of `/en/`
   returned 200 in 0.66 s and 0.26 s **while the Neon compute was suspended**,
   with zero database contact. A managed database still has maintenance windows
   and incidents, so this is worth more than the billing argument that motivated
   it.
3. **A tested guard.** `apps/core/test_middleware.py`'s correctness rules (never
   a logged-in user's page, never a response that sets a cookie) are not
   something to casually re-derive.

Stated against itself: a cache **can mask** a database outage from a casual look
at the home page. That is what `/readyz` and Sentry are for, and it was already
true before this plan.

The same argument protects `/healthz`. Its zero-query rule now has no CU-hour
justification, but it keeps a better one: a liveness probe that depends on a
dependency cannot distinguish "the process is wedged" from "the database
blipped", and Render **restarts an instance that fails its health check** — so a
database hiccup would become an app restart, turning a blip into an outage.
`CLAUDE.md` must be edited to say *that*, because a rule whose only stated reason
has expired is a rule the next session deletes.

**D4 — backups: rely on Render's included point-in-time recovery. A 3-day window
is sufficient, and Render Pro is not needed.**

Verified in Render's own documentation: **PITR is included on every *paid* Render
Postgres instance**, and the recovery *window* is set by the **workspace billing
plan, not the instance size** — Hobby is **the past 3 days**, Pro or higher is 7.
This workspace (`tea-d9eiu4jbc2fs73847fqg`) is on **Hobby** — maintainer-confirmed
rather than measured, because Render's API exposes the workspace's *type* but not
its billing plan, so read it off the dashboard if it ever becomes load-bearing.
Three days is enough here:

- The database is written to by exactly one person, in bursts (a daily export
  upload, occasional Wagtail edits). There is no background process silently
  corrupting rows between backups.
- The realistic disaster is a bad publish, a mistaken delete, or a failed
  ingest — all of which are noticed the same day, well inside 3 days. Wagtail
  keeps its own revision history for the commonest case, so PITR is the second
  line, not the first.
- Render also keeps **downloadable logical backups for 7 days**, regardless of
  workspace plan, which covers "I want a copy in my hand" without a subscription
  change.

**Do not upgrade to Professional ($25/user/month) for this.** Recorded
explicitly so nobody does it on a guess: it would quadruple the hosting bill to
extend a window that the write pattern does not need.

Also recorded: **Render's free Postgres instance type gets no recovery at all**
(and expires 30 days after creation). That is a second, independent reason this
plan says Basic rather than free — not just uptime, but that free means no
backups, which is the position we are leaving.

**Parked, with its argument intact:** a nightly off-provider `pg_dump` to a
private Cloudflare R2 bucket. The honest case for it does not go away — backups
that live only with the host holding the data are a single point of failure, the
irreplaceable half of this database (Wagtail pages, revisions, newsletter bodies)
exists nowhere else, and a logical dump restores *anywhere*, including away from
Render. But it no longer **gates** anything, because it is no longer the
difference between having backups and having none. See "Parked".

**D5 — no keepalive, and nothing to keep alive.**

Recorded only because the Supabase draft needed a decision here: a Render
Postgres instance is always on and does not pause on inactivity, so the whole
question — Supabase free pauses a project after ~7 days of low activity —
evaporates. Deleted rather than adapted.

**D6 — the privacy notice will not name the data host. Maintainer decision, and
it is more defensible after this reversal than before it.**

Checked rather than assumed: "Neon" appears in **20 files**, among them
`CLAUDE.md`, `render.yaml`, `docs/deploying.md`, six plan files,
`config/database.py`, `config/observability.py`, `apps/core/middleware.py`,
`scripts/release.sh` and their tests — every occurrence engineering
documentation, a docstring or a code comment. Nothing rendered on the website
names it (no template matches; `apps/core/views.py`'s two mentions are in
docstrings, not in the `ROBOTS_TXT` body it serves). The one publicly-readable
mention is the repo's own `README.md`, which Track E updates.

**Plan 25 (`plan/25-privacy-notice`, branched off `main`, not yet merged)** is
the plan that could have changed that, and it interacts here in three ways —
read from that branch, not assumed:

1. **Its notice does not name the database host, deliberately.** Its "outside
   services involved" section enumerates *"four, and no more"* — Umami, Sentry,
   Cloudflare, and the Google Maps embed — and the template's own header comment
   scopes the section to *"the third parties a visitor's browser talks to"*. The
   section on what is kept describes the `DeidentifiedVisit` fields in detail and
   says nothing about where the rows sit. Only Sentry gets a region.
2. **Its guard test cannot catch a host change, and must not be trusted to.**
   `test_privacy_notice_names_exactly_the_third_parties_that_are_wired` scans
   `templates/**`, `apps/**/templates/**` and `config/settings/*.py` for
   installation markers — `cloud.umami.is`, `sentry_sdk.init`,
   `storages.backends.s3.S3Storage`, `map_embed_url` and six not-yet-wired
   trackers. A database host lives in an environment variable, matches no marker,
   and the test stays green in both directions.
3. **The maintainer's decision is not to name it**, and this reversal makes that
   an easier call rather than a harder one: the host is no longer a fourth-party
   at all. It becomes **Render**, which already runs the application, already
   holds every secret, and already processes every request — so there is no new
   organisation to disclose, and the visitor-browser scope Plan 25 chose covers
   it correctly. Region is unchanged either way: `aws-ap-southeast-1` → Render
   `singapore`.

Against `CLAUDE.md`'s invariants: no raw PHI is persisted anywhere, so no raw PHI
moves. What moves is `DeidentifiedVisit` (including the seven free-text clinical
columns), the aggregates, and all Wagtail content — from an external processor to
one already in the trust boundary, in the same region, with the same access model
(one secret in the Render dashboard). Invariant #2 is untouched: a database host
is not a model call. This is a **reduction** in the number of processors holding
this data, which is the rare migration that makes a privacy notice more true
rather than less.

**Mechanical note:** Plan 25 and this plan both add a row to
`.claude/plans/README.md`. Whichever merges second resolves a trivial conflict;
neither should rebase the other.

**D7 — cutover is `pg_dump` → `pg_restore` in a short window. Both ends are
Postgres 18, so this is the vendor-standard path.**

Render Postgres has defaulted to **PostgreSQL 18 for newly created databases**
since [2025-11-13](https://render.com/changelog/postgresql-18-is-now-available-for-render-postgres-databases),
and Neon reports `pg_version: 18`. **Same major version on both ends deletes the
hardest part of the earlier draft** — there is no downgrade, so `pg_restore`
works in the direction it is designed for and none of the plain-SQL or
schema-first machinery is needed.

```
pg_dump "$NEON_URL" --format=directory \
    --no-owner --no-privileges --no-subscriptions --file=tkc-dump/

pg_restore --dbname="$RENDER_INTERNAL_URL" --format=directory \
    --no-owner --no-privileges --verbose tkc-dump/
```

- `--format=directory` because that is what `pg_restore` reads and what the
  vendor guidance uses. The `--jobs` parallelism that guidance suggests is
  deliberately **not** carried over: at 41 MB a single-threaded dump takes
  seconds, and a maintenance-window command should have no flags in it that are
  not doing work.
- `--no-owner --no-privileges` because the roles differ between hosts and there
  is nothing to preserve: Django connects as one application role (see the
  caveats below).
- `--no-subscriptions` is kept from the vendor guidance even though this database
  has none — a no-op flag is free and stops the question being re-asked.
- **Confirm the new instance really reports 18 before dumping.** "18 is the
  default" is a changelog claim, and the version selector at creation time can be
  changed; one `select version()` converts it into a measured fact. If it comes
  back 17, **stop** — do not improvise a downgrade in a maintenance window. (This
  repo's own habit: Plan 23 D9 was wrong precisely because a framework's
  "should" was reasoned about instead of measured.)
- **No throwaway target is needed**, which is a genuine simplification over the
  Supabase draft: a second Render instance would cost money, and it is not
  needed, because a failed restore is recoverable in place —
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` and retry. The dump is
  read-only against Neon and can be re-taken freely.
- **The window:** the only writers are staff uploads and Wagtail edits, both
  behind a login; anonymous page views write nothing. So "do not upload or
  publish between the dump and the swap" is a sufficient control and no read-only
  mode needs building. **Anything written after the dump and before the swap is
  lost**, so the window is bounded by the swap, not the dump. Pick a
  Karachi-night hour and tell the one person who can write.
- **The swap:** update `DATABASE_URL` in the Render dashboard to the internal
  URL. Render auto-redeploys on an environment change (observed in Plan 23's own
  Phase 0), and `preDeployCommand` runs `migrate --no-input`, which is a free
  extra check: against a correctly restored database it is a **no-op**, and if it
  announces migrations to apply, the restore lost `django_migrations` and the
  swap should be reverted rather than reasoned about.

**Three caveats from Supabase's migration guide, checked against this repo and
still worth keeping**, because they are properties of *this codebase* rather than
of either host:

- **Extensions.** None needed: no migration in this repo creates one — all 45
  files in `apps/*/migrations/` checked, no `CreateExtension`, no `RunSQL` — and
  `WAGTAILSEARCH_BACKENDS` is `wagtail.search.backends.database`, Wagtail's
  built-in full-text backend, which needs no `pg_trgm` and no `unaccent`.
- **Users/roles are not migrated.** Fine: Django connects as one application
  role, sets no `search_path`, and uses no routers. The *application's* users
  live in `auth_user` and come across as ordinary rows.
- **RLS is not migrated.** Fine: this project uses no row level security. Wagtail
  and Django enforce authorisation in Python.

**D8 — rollback is putting the old `DATABASE_URL` back, and it has an expiry date
that decides the schedule.**

The Neon project is **not deleted** at cutover, and not for at least a full month
afterwards. But the rollback is only real while Neon can serve connections, and
its compute suspends the moment the allowance is gone:

- **Cut over before ~24 August** and the lever works — the reason to do this
  before the deadline rather than after it.
- **Between exhaustion and 1 September there is no rollback**, because the thing
  we would roll back to is off. Do not schedule the cutover into that window.
- **From 1 September the lever returns**, the quota having reset.

The second half is data, and it is honest rather than clean: writes made on
Render after the cutover are not on Neon. A day's export can be re-uploaded
(ingest is re-runnable and `recompute_daily_aggregates` is non-destructive, Plan
22 D2); Wagtail edits made in that window cannot. So rollback is cheap for the
first hours and expensive once someone publishes. Roll back fast or not at all.

**D9 — Render Postgres Basic at $6/month. Not Supabase free, not Neon Launch.**

This was the counter-argument in the Supabase draft of this plan and it won on
its own merits, so it is stated as the decision rather than retrofitted:

- **It deletes the operational surface instead of relocating it.** Supabase free
  would have required a connection-pooler decision, a nightly backup job we
  build and monitor, a restore drill, a 7-day-pause question, and a 500 MB
  ceiling to watch. Render Postgres has none of those, and every one of them was
  a decision this file had to make and a future session had to not get wrong.
- **Backups are included and managed** (D4), where Supabase free has **none** and
  says so, recommending you export your own.
- **Same provider, same region, private network** (D1), so the connection is
  shorter and simpler than either alternative and there is one less vendor
  relationship, one less dashboard, one less status page.
- **The real price gap was never $6.** Supabase free plus the $1/month Render
  cron job its backup story needed made the gap **$5/month** — $60 a year — for
  materially more risk and more moving parts.
- **Against Neon Launch ($19/month):** it needs no migration at all, which is
  genuinely attractive under a deadline, but it costs three times as much to keep
  the exact architecture whose billing model caused Plans 23, 24 and 26. Paying
  more to keep the problem is the worst of the three options. It stays parked as
  a one-month deadline valve.
- **Cost, plainly:** ~$7/month → ~$13/month, inside `CLAUDE.md`'s ~$20–30
  budget. The money is donated — this is a Zakat/Sadaqa-funded clinic — so the
  spend deserves the scrutiny it got; $6/month for managed, backed-up, always-on
  Postgres and the end of a recurring outage risk is a defensible use of it, and
  cheaper than the engineering time already spent avoiding it.

**D10 — no feature flag, deliberately.**
No user-visible surface and no partial state to flag. The rollback lever is an
environment variable and a redeploy (D8), which is what a flag would have
provided. Recorded so the choice is deliberate (lifecycle Stage 6), matching
Plan 23 D6.

**D11 — historical note: the data-only-load trap, recorded because it is a good
trap.**

Moot here — a full `pg_restore` into an empty database carries production's own
`auth_permission` and `django_content_type` rows **with their primary keys
intact**, so nothing can be renumbered. But the earlier draft needed a data-only
load (a major-version downgrade forced Django to build the schema itself), and
that path had a silent hazard worth remembering: `migrate` seeds
`django_content_type`, `auth_permission` and Wagtail's root page/site/collection/
groups, and those primary keys are referenced by the data being loaded. Since
Plan 21 deleted two page types, production's ID space has holes a fresh `migrate`
will not reproduce — so loading production's `auth_group_permissions` on top of
freshly numbered permissions would have **silently re-pointed the Editors and
Moderators groups at different permissions**, with row counts matching perfectly.
The fix was to truncate all of `public` inside the load transaction rather than
exclude tables. If a same-version restore is ever impossible again, start here.

**D12 — logical replication is not used, and here is the durable warning about
Neon that came out of evaluating it.**

Not needed: 41 MB, one writer, a maintenance window of minutes. But the
evaluation turned up two facts about Neon that are worth keeping regardless of
this migration, because they are the kind of thing someone reaches for
casually:

1. **An active logical-replication subscriber holds a Neon compute out of
   scale-to-zero.** [Neon's own docs](https://neon.com/docs/guides/logical-replication-neon)
   are explicit: the replication slot stays active, so the compute never goes
   idle. At the 0.25 CU floor that is 6.0 CU-hr/day (Plan 23's arithmetic) — with
   11.4 CU-hr left, under 48 hours to exhaustion. Anyone who wires a replica,
   a CDC pipeline or an analytics sync to a Neon free project has re-created
   Plan 23's bug in a new form.
2. **Enabling logical replication on a Neon project is irreversible.** The
   project reports `enable_logical_replication: false` and Neon states the
   setting **"cannot be reverted once enabled"**. It is not a thing to toggle
   exploratively, least of all on a database that is also a rollback target.

Also worth knowing, since it defeats the usual reason for reaching for it: it
replicates rows, **not DDL**, so the target's schema must already exist by other
means. It does not sidestep a version mismatch; it only replaces a one-off copy
with a continuous stream.

---

## Verification — what must be true before the swap, and after it

Specified here; run during Track C. Checks 1–4 run against the new database
**before** `DATABASE_URL` is swapped.

**1. Row counts per table, exact, both sides.** Not `pg_stat_user_tables`
estimates — `n_live_tup` is an approximation, and this is the check that proves
nothing was dropped. Generate the query from the catalogue so no table can be
forgotten:

```sql
SELECT format('SELECT %L AS t, count(*) FROM %I.%I', tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
```

Run the generated `UNION ALL` on both and diff. Pass condition: **identical,
every table, including the ones nobody thinks about** —
`wagtailcore_pagerevision`, `wagtailcore_pagelogentry`,
`wagtailredirects_redirect`, `django_content_type`, `auth_permission`,
`django_migrations`.

**2. `manage.py migrate --check`** against the new database. Run it with
`config.settings.dev` and `DATABASE_URL` pointed at the new instance, **not**
with prod settings: importing the prod module demands every production secret
(`SECRET_KEY`, `ALLOWED_HOSTS`, all five `MEDIA_*`) before it will boot — the
same property `config/database.py`'s docstring cites as its own reason for
existing. It must report nothing to apply.

**3. Wagtail page-tree integrity: `Page.find_problems()` must return empty.**
The precedent is Plan 21, where it caught `numchild` corruption from a cascade
nobody predicted. A dump/restore should not be able to break
`path`/`depth`/`numchild`, and this is how that stops being a belief.

**4. The real reader pages render, through a real server, against the new
database.** Not the test client — the lifecycle's rule is to exercise the change
through the entry point a real visitor uses. `runserver` against the new URL with
the page cache disabled (`CACHE_PAGE_SECONDS=0`) so every request actually
reaches Postgres, and fetch:

- `/en/` — the home page, including the live impact-stats band, which reads
  `DailyAggregate`;
- a **daily report page** — the deepest read path (aggregates, free-text summary,
  revenue surfaces);
- `/en/reports/` and `/en/reports/dashboard/` — the funding-mix chart and the
  range dashboard, both aggregating across many rows;
- `/en/newsletters/` and one issue — images and documents, which also proves the
  R2 media URLs survived;
- `/admin/` login, one page's edit view, and **saving a new page** — the write
  path, the only way to see that revisions came across, and the check that
  sequences are correct (a restored-but-unadvanced sequence shows up as a
  duplicate-key error on the first insert, and nothing in check 1 would catch
  it).

Paste the real output. A 200 with a silently empty stat band is a failure, so
compare the figures against what production shows for the same pages.

**5. `/readyz` returns 200 after the swap.** This is the gate that matters
because the tooling shares it: `scripts/release.sh` polls `/readyz` for up to 10
minutes as its post-deploy gate (Plan 23 D10 sized that window), so a database
the app cannot reach fails every future release, not just this one. Note that an
environment-variable swap is **not** a tagged release, so `release.sh` is not what
runs here — check `/readyz` by hand, then treat the *next* ordinary release as
the real end-to-end proof of the deploy path.

**6. Prove recovery exists, rather than assuming D4.** In the Render dashboard,
confirm the new instance shows a **point-in-time recovery** window (3 days on
Hobby) and that a **logical backup** can be downloaded. A backup capability
nobody has looked at is a belief, and this is the one check that turns D4 from a
documentation claim into an observed property of our own instance.

**7. After the swap, watch a week.** `/readyz` and page traces in Sentry for
connect latency over the internal network (D2's input), Render logs for
`OperationalError`, and the database's own metrics for connection count — it
should sit near one, given `numInstances: 1` and `CONN_MAX_AGE=60`.

---

## Parked, deliberately

- **Supabase free, the road not taken.** Fully worked out in this file's history
  (git shows the original draft): session-mode pooler, plain-SQL downgrade,
  truncate-and-reload, nightly dump, no pause keepalive. Unpark condition: if the
  $6 ever stops being spendable, or if Render Postgres proves unreliable in a way
  that makes leaving Render attractive. Whoever unparks it should read D1's and
  D11's historical notes first — the pooler and ID-renumbering traps are both
  live again the moment the destination changes.
- **The nightly off-provider `pg_dump` to a private R2 bucket.** No longer a
  precondition (D4), but the argument survives: backups that live only with the
  host holding the data are a single point of failure, and the irreplaceable half
  of this database — Wagtail pages, revisions, newsletter bodies — exists nowhere
  else. The maintainer has confirmed a **private R2 bucket is available** if this
  is unparked (it must never be the media bucket, which `docs/deploying.md`
  records as deliberately public). Cost would be $1/month for a Render cron job
  in Singapore, chosen over free GitHub Actions because this repo is **public**
  and a US runner would pull de-identified clinical text onto a machine that is
  not otherwise a processor here. Unpark if PITR is ever found not to cover a
  real incident, or before any change that could corrupt data wholesale (a bulk
  re-ingest, a destructive migration).
- **Render Professional ($25/user/month).** Would extend PITR from 3 days to 7.
  **Not needed** (D4) — recorded so nobody upgrades on a guess. Unpark only if
  the write pattern changes such that a fault could go unnoticed for more than
  three days.
- **Neon Launch at $19/month.** Zero-migration deadline valve for one month if
  the cutover cannot happen before ~24 August. Otherwise superseded by D9.
- **A Sentry cron monitor.** Only relevant if the nightly dump is unparked, and
  check-ins are a new Sentry event kind — `CLAUDE.md` requires asking what
  payload a new kind carries before enabling it.
- **Lowering `CACHE_PAGE_SECONDS` now that cost is not the reason for it.**
  Fresher content is a real benefit and compute is no longer the constraint, but
  publish-signal invalidation (Plan 24 D4) already handles the case people
  notice. Unpark if a content change is ever observed to lag.
- **`tcp_user_timeout` / server-side `statement_timeout`.** Still the open gap
  `config/database.py` names, still untouched. Cheaper to reason about now that
  the database is one private hop away.
- **Declaring the database in `render.yaml`.** Now possible for the first time
  (the blueprint previously could not describe an external database), but the
  file demonstrably does not reach the live service, so adding a `databases:`
  block would be documentation that looks like automation. Unpark with the
  question of *why* the blueprint doesn't sync, which was never established.

---

## Release plan

No flag (D10). This ships as **two changes with different mechanisms**: a
docs-and-comments PR that goes out with an ordinary tagged release, and a
dashboard change that is not a deploy at all.

| Phase | Action | Gate | Rollback trigger |
|---|---|---|---|
| 1 | Create **Render Postgres Basic** in **Singapore** (matching `srv-d9ej48n41pts73f1i3p0`), in workspace `tea-d9eiu4jbc2fs73847fqg`. Copy the **internal** connection string | Instance healthy; `select version()` reports **18** (D7 — a changelog claim until measured); region is Singapore; PITR window visible (Verification 6); note the plan's included storage and confirm 41 MB has real headroom (deliberately not guessed at in this file — read it at creation) | Reports 17, or region wrong → destroy and recreate. Region is immutable, so this is the phase to get right |
| 2 | Ship the docs/comment PR (Tracks A + E) as a normal tagged release, still pointing at Neon | `scripts/release.sh`'s `/readyz` gate; site renders | Redeploy previous tag |
| 3 | **Cutover** (D7): quiet Karachi-night hour, no uploads or publishes. `pg_dump` → `pg_restore` → Verification 1–4 → swap `DATABASE_URL` to the internal URL (leave `DB_CONNECT_TIMEOUT=15`, D2) | `/readyz` 200; the auto-redeploy's `migrate --no-input` is a **no-op**; home, a daily report and the dashboard render with the right numbers; a new page saves | Any check fails → restore the Neon `DATABASE_URL` and let it redeploy. A failed `pg_restore` is recoverable in place (`DROP SCHEMA public CASCADE`) with no second instance. **Only available while Neon has CU-hours (D8) — do not schedule into the 24 Aug → 1 Sep window** |
| 4 | Watch a week (Verification 7) | No `OperationalError`s; connect latency at internal-network levels; connections ≈ 1 | Sustained failures → revert `DATABASE_URL` (from 1 Sep, Neon is available again) |
| 5 | Clear `DB_CONNECT_TIMEOUT` to take the code default of 5 (D2), then **delete the Neon project** | A measured connect latency from `/readyz` traces, not a guess; a full week clean | Clearing it is a dashboard change, revert by setting 15 again |

**Keep the Neon project until at least a full week after Phase 4.** It is the
only rollback target that exists, and it costs nothing to leave alone.

**Who is informed:** the maintainer, who is also the only person who can write to
the database and therefore the only person Phase 3's window depends on. No
downstream operators or users. User-visible behaviour is unchanged, except that
the first page load after a quiet period gets *faster*, because nothing is
resuming from zero any more.

---

## Reference material

- Render — [PostgreSQL 18 is now available](https://render.com/changelog/postgresql-18-is-now-available-for-render-postgres-databases)
  (2025-11-13; default for newly created databases — the fact D7 rests on, and
  confirms at Phase 1), [Postgres backups and recovery](https://render.com/docs/postgresql-backups)
  (PITR on paid instances; window set by workspace plan — Hobby 3 days, Pro 7;
  logical backups downloadable, retained 7 days; **no recovery on free**), and
  [cron jobs](https://render.com/docs/cronjobs) ($1/month minimum — the parked
  backup job).
- Neon — [logical replication](https://neon.com/docs/guides/logical-replication-neon)
  (an active subscriber holds the compute out of scale-to-zero, and the setting
  cannot be un-enabled) — the durable warning in D12.
- Supabase, for the parked alternative — [migrating from Postgres](https://supabase.com/docs/guides/platform/migrating-to-supabase/postgres)
  (whose `--no-owner --no-privileges --no-subscriptions` flags and three caveats
  this plan still uses), [connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)
  and [dedicated IPv4](https://supabase.com/docs/guides/platform/ipv4-address)
  (why D1's historical note says session-mode pooler), and
  [backups](https://supabase.com/docs/guides/platform/backups) (no automated
  backups on Free — the fact that decided D9).
- In-repo — [Plan 23](23-healthz-scale-to-zero.md) (the cost model and the
  `/healthz` split), [Plan 24](24-crawler-load.md) (the cache, and what
  measurement did to two confident predictions), `config/database.py` (the
  connect-timeout argument this plan rewrites), `docs/deploying.md` (the deploy
  gate and every secret involved), and `plan/25-privacy-notice` (D6).
