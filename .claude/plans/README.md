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
| 03.5 | [Design system enhancements & page layout components](03.5-design-enhancements.md) — reusable page-body kit (hero, stat band, card grid, feature split, CTA band, media grid, section rhythm) on top of the merged Plan 03 chrome | 📝 Drafted |
| 04 | [Core content pages](04-core-content-pages.md) — Home, About, Team/Management, Our Work/Services, Contact | 📝 Drafted |
| 05 | [Donate placeholder](05-donate-placeholder.md) — Zakat/Sadaqa message + bank/contact config | 📝 Drafted |
| 06 | [Newsletters, Camp Reports & Gallery](06-newsletters-camps-gallery.md) — archive content types, consent-gated photo gallery | 📝 Drafted |
| 07 | [Accounts & roles](07-accounts-roles.md) — uploaders/approvers | 📝 Drafted |
| 08 | [Data pipeline](08-data-pipeline.md) — intake, parser registry, aggregate-and-discard, daily report page | 📝 Drafted |
| 09 | [AI monthly newsletter](09-ai-monthly-newsletter.md) — Anthropic SDK, deterministic-numbers guardrail, draft → review | 📝 Drafted |

**Legend:** ⬜ Not started · 📝 Drafted (plan written, not implemented) · 🚧 In progress · ✅ Done

## Out of scope (for now)

Deferred by decision on 2026-07-19; revisit after the core is live:

- **Assistants** — public site helper (RAG over published pages) and internal
  "ask your data" chat over aggregates.
- **New export types via agentic schema inference** — model-assisted onboarding
  of unfamiliar Excel formats. Until then, new formats get a hand-written parser.
- **Bilingual generation** — Urdu (and Pashto) translation/drafting of site
  content and AI-generated newsletters/reports.
- **Ops hardening** — deploy hardening, backups, monitoring, funding-export
  tooling.
