# Build Plans

We plan each build step here, commit the plan, then implement it — **one plan at
a time**. Each plan is a self-contained step with its own PR. Website-first.

See [CLAUDE.md](../../CLAUDE.md) for the non-negotiable privacy invariants and
[docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md) for
the overall design.

## Roadmap

| # | Plan | Status |
|---|------|--------|
| 01 | [Project foundation](01-project-foundation.md) — Django + Wagtail scaffold, settings, Postgres, deploy target, CI, secrets | ✅ Done |
| 02 | [Development lifecycle & environments](02-development-lifecycle.md) — staging/production split, CD pipeline, testing strategy, privacy-guardrail tests, mocked-vs-live AI in CI | 📝 Drafted |
| 03 | [Design system & base templates](03-design-system.md) — brand tokens, self-hosted type, base templates, nav/footer, bilingual (EN/UR) routing + RTL, accessibility | 📝 Drafted |
| 04 | [Core content pages](04-core-content-pages.md) — Home, About, Team/Management, Our Work/Services, Contact | 📝 Drafted |
| 05 | [Donate placeholder](05-donate-placeholder.md) — Zakat/Sadaqa message + bank/contact config | 📝 Drafted |
| 06 | [Newsletters, Camp Reports & Gallery](06-newsletters-camps-gallery.md) — archive content types, consent-gated photo gallery | 📝 Drafted |
| 07 | Accounts & roles — uploaders/approvers | ⬜ Not started |
| 08 | Data pipeline — intake, parser registry, aggregate-and-discard, daily report page | ⬜ Not started |
| 09 | AI monthly newsletter — Anthropic SDK, deterministic-numbers guardrail, draft → review | ⬜ Not started |
| 10 | Bilingual generation — Urdu (and Pashto) | ⬜ Not started |
| 11 | Ops — deploy hardening, backups, monitoring, funding-export | ⬜ Not started |

**Legend:** ⬜ Not started · 📝 Drafted (plan written, not implemented) · 🚧 In progress · ✅ Done

## Out of scope (for now)

Deferred by decision on 2026-07-19; revisit after the core is live:

- **Assistants** — public site helper (RAG over published pages) and internal
  "ask your data" chat over aggregates.
- **New export types via agentic schema inference** — model-assisted onboarding
  of unfamiliar Excel formats. Until then, new formats get a hand-written parser.
