# Plan 24 — Cut the crawler load that still keeps Neon awake

**One line:** Plan 23 removed the health check's `SELECT 1` and cut compute burn
by 70%, but the free tier will still be exhausted around 23 August, because
~740 crawler page-loads a day each wake the database for five minutes; cache
public pages so repeat crawls never reach Postgres, and tell the crawlers we
can influence to slow down.

---

## Background — measured, 2026-08-16

Plan 23 shipped on 13 August. Three days of clean data, taken from the Neon
projects API (a control-plane call — unlike SQL it does not wake the compute):

| | 13 Aug 18:11 | 16 Aug 16:33 |
|---|---|---|
| `cpu_used_sec` | 292,404 | 312,683 |
| `active_time` | 1,094,247 s | 1,172,847 s |

Using the identity confirmed against the console dashboard on 13 Aug
(**CU-hrs = `cpu_used_sec` / 3600** — a 3,641 s delta matched the dashboard's
80.2 → 81.22 exactly):

- **+5.63 CU-hr over 2.93 days = 1.92 CU-hr/day** (was 6.38 before Plan 23)
- Compute **awake 31% of the time** (was 100%) — Plan 23 delivered a real
  **70% cut**
- Average compute size 0.258 CU, i.e. sitting at the 0.25 floor and **not**
  autoscaling, so there is no headroom to reclaim there

**It is still not enough.** At ~86.9/100 CU-hr used, 13.1 CU-hr remain for
15.3 days — an affordable **0.86 CU-hr/day** against an actual **1.92**. On
this trajectory the allowance is exhausted around **23 August**, roughly nine
days before the 1 September reset. Exhausting compute on the free plan
suspends the compute, and every page on this site reads Postgres, so that is a
site outage — not a billing footnote.

### What the load actually is — and why the previously-planned fix is wrong

Plan 23's parked follow-up was "a DB-free 404 for scanner paths". **That would
now be nearly useless.** Sentry, last 3 days:

| Transaction | Count | Touches DB? |
|---|---|---|
| `/en/{var}` | **2,219** (~740/day), **all HTTP 200** | yes |
| `/` | 192 | yes |
| `/static/*` (all variants) | ~555 | no (WhiteNoise) |
| `/robots.txt` | 52 | no |
| `/admin/login/`, `/admin/.*/` | 96 | yes |
| `/wp-admin/install.php` | 42 | yes |
| `wlwmanifest.xml` (~10 variants) | ~70 | yes |

The WordPress scanners are **noise**: ~112 requests in three days against
2,219 successful page loads. Roughly **85% of the database load is now
ordinary 200-OK page traffic**, so blocking 404 paths would barely move the
number. Umami measures ~15 *human* page views a day, so ~740/day is about 50×
that — non-JS crawlers Umami cannot see.

The individual events show bursts (9 hits inside 75 seconds) separated by real
gaps of 17–60 minutes. That burst-and-gap shape is exactly why the compute
manages 31% idle rather than 0%, and it is also why caching should work well:
within a burst, the first request pays for the database and the rest are free.

### The grounding gap, stated rather than guessed

**We cannot currently identify these crawlers.** Sentry does not retain a user
agent for these spans, and gunicorn runs without `--access-logfile`, so
Render has no request logs either. Every option that means "block the bad
bots" is therefore un-groundable today — which is why this plan does the
things that are safe without that knowledge, and adds the visibility needed to
decide the rest (Track C).

---

## Scope

### Track A — cache public page responses (the 85%)

A narrow, hand-rolled middleware that caches anonymous `GET` responses for the
public page tree, so a crawler re-fetching a page it already fetched costs zero
database queries.

- `apps/core/middleware.py` — the middleware plus pure, testable predicates.
- `apps/core/apps.py` — invalidate on publish (Wagtail signals).
- `config/settings/base.py` — `CACHES`, the middleware entry.
- Tests, including the guards below being proven to go red.

### Track B — tell the crawlers we can influence to back off

`apps/core/views.py`'s `ROBOTS_TXT` gains `Crawl-delay` and `Disallow` for the
AI/scraper agents that publish a token, **never** for Googlebot or Bingbot.
Advisory only, and honest about that (D6).

### Track C — make the next decision groundable

Attach the user agent to Sentry events so that in a week we can say *which*
crawlers these are, and decide Track D on evidence.

### Track D — upstream blocking (maintainer, parked)

Putting Cloudflare in front would let its verified-bot list do the work without
us identifying anything by hand. It needs a DNS/nameserver change on
`thandkoiclinics.com`, which is the maintainer's action, not this repo's. See
"Parked".

---

## Decisions

**D1 — hand-roll the middleware; do not add `wagtail-cache`.**
`pyproject.toml` pins every dependency with an upper bound and CI runs a
separate supply-chain gate, so a new runtime dependency is not free here. More
importantly the failure modes — serving a logged-in editor's rendered page to
the public, or serving withdrawn content after an unpublish — are exactly the
kind of thing that must be explicit and directly testable rather than emergent
from Django's `Vary: Cookie` semantics. The repo already prefers this shape:
`apps/pipeline/middleware.py`, `config/observability.py` and
`config/database.py` are all hand-written, heavily-commented, unit-tested
modules in place of a library.

**D2 — `FileBasedCache`, not `LocMemCache`.**
Gunicorn runs multiple workers and `LocMemCache` is per-process, so each worker
would hold its own copy and the hit rate would be divided by the worker count —
directly undermining the only thing this plan is for (fewer database wakes).
A file-based cache is shared by every worker on the instance, needs no new
service, and costs nothing. Render's disk is ephemeral per deploy, which is
fine: a cold cache after a deploy is a correctness non-event.

**D3 — cache only anonymous `GET` 200s, by explicit test, and never a response
that sets a cookie.**
The middleware refuses to cache unless *all* hold: method is `GET`, the user is
not authenticated, the path is not under `/admin/`, `/django-admin/` or
`/documents/`, the status is 200, and the response carries no `Set-Cookie`.
That last one is doing real work — it is what keeps any response that
establishes a session or CSRF cookie out of a shared cache, without having to
reason about `Vary` at all.

Verified precondition, checked rather than assumed: **the public site has no
forms at all** — no `<form>` outside the admin templates and no `csrf_token` in
any template. So the usual "cached page serves a stale CSRF token" hazard does
not exist here. If a public form is ever added, this decision has to be
revisited, and that is written into the middleware's docstring.

**D4 — invalidate the whole cache on any publish, rather than by key.**
Publishing is rare on this site and correctness is worth far more than a
precise eviction. Clearing everything on `page_published` / `page_unpublished`
cannot leave a stale page behind through some path the author of a partial
invalidation did not think of.

**D5 — TTL is env-dialable, defaulting to 3 hours.**
Same posture as `DB_CONNECT_TIMEOUT` and `SENTRY_TRACES_SAMPLE_RATE`: a knob
that can be turned from the Render dashboard with no deploy, soft-failing to
the default on a bad value. TTL is the safety net for content that changes
*without* a page publish — a snippet or a settings object — which D4's signals
do not catch. It is also the main lever on how much compute this saves: at a
3-hour TTL a crawler that returns hourly pays the database only every third
visit.

**D6 — `robots.txt` never blocks Googlebot or Bingbot.**
A not-for-profit clinic wants to be findable; suppressing search indexing to
save compute would be trading the site's purpose for its hosting bill. Only
agents that exist to scrape rather than to refer traffic are disallowed, and
`Crawl-delay` is added for everyone else. This is **advisory** — a crawler
that ignores `robots.txt` is unaffected, and the ones burning the most compute
may well be exactly those. Track B is a cheap partial, not the fix, and Plan 18's
existing reasoning about *not* disallowing `/reports/` is untouched.

**D7 — add user-agent visibility before deciding anything harsher.**
Every "block the bots" option is currently a guess (see the grounding gap
above). One Sentry tag turns the next decision into a measurement. Chosen over
enabling gunicorn access logs because it is an in-repo, testable change in the
module that already owns Sentry policy, rather than a dashboard edit to the
service's start command.

**D8 — no feature flag, but the cache is switchable.**
`CACHE_PAGE_SECONDS=0` disables caching outright from the dashboard with no
deploy, which is the rollback lever a flag would otherwise provide.

---

## Parked, deliberately

- **Cloudflare in front of the site (Track D).** Would let Cloudflare's own
  verified-bot classification do the work, allowing Googlebot through while
  challenging scrapers, with no user-agent list to maintain. Needs a
  nameserver change on `thandkoiclinics.com` — maintainer action. Revisit once
  Track C says who the traffic actually is.
- **Upgrading to Neon Launch ($19/mo) or moving to Render Postgres.** The
  straightforward way to make the cap irrelevant. Deliberately not the first
  move: this plan should be tested first, because if it works the spend is
  unnecessary. Revisit immediately if the burn rate has not dropped below
  ~0.8 CU-hr/day within a few days of deploying, because the deadline is hard.
- **Per-key cache invalidation.** See D4.

---

## Release plan

| Phase | Action | Gate | Rollback |
|---|---|---|---|
| 1 | Deploy Tracks A–C | `scripts/release.sh`'s `/readyz` check; site renders; an editor publish visibly clears the cache | `CACHE_PAGE_SECONDS=0` in the dashboard, no deploy |
| 2 | Sample `cpu_used_sec` daily | Burn rate drops below **0.86 CU-hr/day** | If not, take the parked upgrade — the 23 Aug deadline is hard |
| 3 | Read the user-agent breakdown after ~a week | Names the top crawlers | Decides Track D on evidence |

**Deadline is real:** if Phase 2 has not clearly worked by ~21 August, upgrade
rather than keep tuning, because running out means the site goes down until
1 September.
