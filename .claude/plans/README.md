# Build Plans

We plan each build step here, commit the plan, then implement it — **one plan at
a time**. Each plan is a self-contained step with its own PR. Website-first.

See [CLAUDE.md](../../CLAUDE.md) for the non-negotiable privacy invariants and
[docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md) for
the overall design.

## Plan structure

Each drafted plan follows the development lifecycle in `~/.claude/CLAUDE.md`.
Alongside goal / scope / decisions / task-checklist / acceptance-criteria, every
plan from 03.5 onward carries three lifecycle sections:

- **Precedent map** (Stage 7) — for each element, the in-repo file/pattern it
  mirrors, or — where this greenfield repo has none yet — the authoritative
  reference (Wagtail/Django idiom, the brand guide, a maintainer decision) it's
  grounded against. Gaps with no precedent are flagged as best-practice grounding,
  never invention.
- **Feature flag** (Stage 6) — the deliberate flag decision and why. This is a
  brand-new, pre-launch repo, so **no plan uses a runtime flag** — there are no
  existing users a partial slice could reach. The natural gates do the work
  (Wagtail's own draft/publish, the `can_upload_export` permission, and a phased
  staging-first rollout for the PHI pipeline). The decision is still recorded per
  plan, so adding a flag later — if the site is live and one becomes warranted —
  stays a deliberate choice rather than an afterthought.
- **Release plan** (Stage 10) — how it ships, who gets access, who's informed, the
  gating check, and the rollback trigger.

## Roadmap

| # | Plan | Status |
|---|------|--------|
| 01 | [Project foundation](01-project-foundation.md) — Django + Wagtail scaffold, settings, Postgres, deploy target, CI, secrets | ✅ Done |
| 02 | [Development lifecycle & environments](02-development-lifecycle.md) — staging/production split, CD pipeline, testing strategy, privacy-guardrail tests, mocked-vs-live AI in CI | 🚧 In progress |
| 03 | [Design system & base templates](03-design-system.md) — brand tokens, self-hosted type, base templates, nav/footer, bilingual (EN/UR) routing + RTL, accessibility | ✅ Done |
| 03.5 | [Design system enhancements & page layout components](03.5-design-enhancements.md) — reusable page-body kit (hero, stat band, card grid, feature split, CTA band, media grid, section rhythm) on top of the merged Plan 03 chrome | 🚧 In progress |
| 04 | [Core content pages](04-core-content-pages.md) — Home, About, Team/Management, Our Work/Services, Contact | 🚧 In progress |
| 05 | [Donate placeholder](05-donate-placeholder.md) — Zakat/Sadaqa message + bank/contact config | 🚧 In progress |
| 06 | [Newsletters, Camp Reports & Gallery](06-newsletters-camps-gallery.md) — archive content types, consent-gated photo gallery | 🚧 In progress |
| 07 | [Accounts & roles](07-accounts-roles.md) — uploaders/approvers | 🚧 In progress |
| 08 | [Data pipeline](08-data-pipeline.md) — intake, parser registry, aggregate-and-discard, daily report page | 🚧 In progress |
| 09 | [AI monthly newsletter](09-ai-monthly-newsletter.md) — Anthropic SDK, deterministic-numbers guardrail, draft → review | 🚧 In progress |
| 10 | [Media object storage](10-media-object-storage.md) — serve/persist Wagtail uploads from S3-compatible object storage (Cloudflare R2); prod media was 404ing on ephemeral disk | 🚧 In progress |
| 11 | [Stakeholder feedback triage (July 2026)](11-stakeholder-feedback-2026-07.md) — backlog of report/admin/content/process items from the maintainer's review round, sorted into tracks and priorities, to be sliced into follow-up plans. Track E's options review: [E1/E2 research](11-e1-e2-research-2026-07.md). Track F2's planning pass: [live impact-stats planning](11-f2-live-impact-stats-planning.md) | 🚧 In progress |
| 12 | [Observability](12-observability.md) — Sentry error tracking + uptime alerting on `/healthz` (Track A), Umami Cloud traffic analytics (Track B); the "monitoring" item deferred below, now being addressed. Track B merged (PR #116, maintainer account/website-ID setup still pending); Track A in progress | 🚧 In progress |
| 13 | [Reports index: funding-mix trend chart](13-reports-funding-mix-chart.md) — rolling 30-day Zakat-vs-Regular stacked bar chart on `/reports/`, server-rendered SVG, no daily-page chart, no department/diagnosis breakdown | 🚧 In progress |
| 14 | [Freetext summary split by demographic group](14-freetext-summary-by-demographic-group.md) — daily report's free-text summary split into male adults / female adults / children, 30 words each, approximate age-band cutoff, three-column layout | ✅ Done |
| 15 | [Code-review remediation (July 2026)](15-code-review-remediation-2026-07.md) — fixes from two whole-codebase review passes, sequenced by risk into four PRs: Sentry PHI leak + prod-settings CI gate (P0), report-publishing re-ingest data integrity (P1), guardrail/injection/k-anonymity/supply-chain hardening (P2), correctness/perf/i18n/docs polish (P3), structured outputs (follow-on) | 🚧 In progress (Tracks A–D implemented; Track E deferred) |
| 16 | [Clinic dashboard (range view) + entry points](16-clinic-dashboard.md) — `/reports/dashboard/` totalling any reader-chosen date range (KPIs, bucketed footfall chart, funding/gender/age splits, reporting gaps), plus entry points 1a (reports index) and 1c (home impact band). Phase 1 ships without revenue data; revenue surfaces are gated on data presence, not a flag. Design handoff: [`docs/design/clinic-dashboard-handoff.md`](../../docs/design/clinic-dashboard-handoff.md). All four tasks landed: 16.1 chart-geometry extraction (PR #131), 16.2 range aggregation module (PR #132), 16.3 page + template + CSS (PR #134), 16.4 entry points 1a + 1c. Phase 2 (revenue) is parked in the plan file, waiting on the clinic software's fee columns | ✅ Done |
| 17 | [Observability round 2](17-observability-round-2.md) — performance tracing (response times) + `WARNING` structured logs in Sentry, the `before_send_transaction` PHI hook tracing newly requires, scrub hooks extracted to a testable `config/observability.py`, and one custom "Service health" dashboard. Explicit reversal of Plan 12's parked APM decision. Tracks A–C merged (PR #135) and live in production; Track D's dashboard is built, its uptime monitor is awaiting a maintainer decision on data residency | ✅ Done |
| 18 | [Free-text summary privacy remediation](18-notes-privacy-remediation.md) — stakeholder feedback (2026-07-25) surfaced that the Plan 15 N=3 k-anonymity floor runs at publish time only and deployed *after* every live report was published, so 14 sub-floor summaries (10 of them describing a single patient) were public. Adds a `scrub_subfloor_freetext_summaries` backfill command, `noindex` on daily report pages, and a `robots.txt`. Floor stays at 3 (D1, maintainer decision) | 🚧 In progress |

| 18 | [Mobile menu + dashboard responsive revision](18-mobile-menu-and-dashboard-responsive.md) — Track A: the nav drawer's current-page marker (new `--color-nav-current` token, invisible in dark mode before), Donate moved out of the page list into its own CTA block, and the Donate label back to dark ink on amber. Track B: the clinic dashboard's revised range controls (preset tile grid + date card, approved mobile option 1c) and its full-width revenue layout, replacing the page's media queries with auto-fitting grids. Both from one updated design handoff: [`clinic-dashboard-handoff.md`](../../docs/design/clinic-dashboard-handoff.md) (revised) and [`mobile-menu-handoff.md`](../../docs/design/mobile-menu-handoff.md) (new) | ✅ Done |

**Legend:** ⬜ Not started · 📝 Drafted (plan written, not implemented) · 🚧 In progress · ⏸ Paused/parked (work stopped, not abandoned) · ✅ Done

## Out of scope (for now)

Deferred by decision on 2026-07-19; revisit after the core is live:

- **Assistants** — public site helper (RAG over published pages) and internal
  "ask your data" chat over aggregates.
- **New export types via agentic schema inference** — model-assisted onboarding
  of unfamiliar Excel formats. Until then, new formats get a hand-written parser.
- **Bilingual generation** — Urdu (and Pashto) translation/drafting of site
  content and AI-generated newsletters/reports.
- **Ops hardening** — deploy hardening, backups, funding-export tooling.
  (Monitoring, one of the four original items here, is no longer deferred —
  see [Plan 12](12-observability.md), drafted 2026-07-24.)
