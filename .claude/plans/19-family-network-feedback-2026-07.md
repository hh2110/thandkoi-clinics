# Plan 19 — Upcoming events card (The Family Network feedback, July 2026)

**One-line:** add an "upcoming events" card to the home page, so camps and
other announced events (e.g. the 2026-08-06 camp) can be surfaced before
they happen — the one open item left from a wider feedback triage of the
family WhatsApp group ("The Family Network").

## Background — why now

The maintainer's family/stakeholder group ("The Family Network") reviewed
the early site drafts, the June newsletter, and the new clinic dashboard
over several days and left feedback inline in WhatsApp. Most of it has since
been resolved:

- The home-page About/founders section and the expandable inline
  Contact/Zakat details are **done and merged** (maintainer confirmed
  2026-07-29) — no longer tracked here.
- The 2026-07-25 "patient notes shouldn't be viewable" concern is the
  re-identification gap **Plan 18
  ([`18-notes-privacy-remediation.md`](18-notes-privacy-remediation.md))**
  fixed the same day — merged, deployed, scrub confirmed.
- The "Donate menu item stays highlighted" concern matches **Plan 18
  ([`18-mobile-menu-and-dashboard-responsive.md`](18-mobile-menu-and-dashboard-responsive.md))
  Track A** — merged.
- Small housekeeping items (a stray `&` character, a since-redesigned
  contact-page duplicate, a "no em-dash" content-style note) were either
  stale or content-only and aren't code work.

**The one remaining item:** "Can we place a column on side to upload our
events? Like the upcoming camp on 6 August" → "On the landing page"
(Amanullah, 2026-07-28, WhatsApp).

**Grounding (Stage 3):** confirmed against the repo — no events/upcoming-camp
concept exists anywhere yet. There is no `EventPage` or camp-calendar model
in `apps/core/models.py`; camps currently only show up *after* the fact, as
camp reports via the data pipeline (Plan 06/08), never as forward-looking
announcements. `apps/core/templates/core/home_page.html` is composed
entirely from the Plan 03.5 StreamField block kit (hero → live-impact band →
StreamField body → report/newsletter teasers) with no events slot. This is
new scope, not a surfacing job.

## Design status

**Currently in progress:** a design pass for this card is starting
separately (see the design-agent brief below) before any task file or
branch is opened. Per Stage 3/Stage 5, this settles the open design question
— lightweight admin-editable snippet vs. a full page type, and where exactly
the card sits in the home page's existing section order — before
implementation, rather than guessing.

## Milestones

- [ ] **1. Design pass.** Produce a handoff (spec + interactive prototype +
      light/dark screenshots), matching the format of the existing
      `docs/design/clinic-dashboard-handoff.md` /
      `docs/design/mobile-menu-handoff.md` bundles, for an "Upcoming events"
      card on the home page. Not started — design agent brief below.
- [ ] **2. Task file + implementation**, once the design handoff lands:
      data model (leaning admin-editable snippet — date, title, optional
      link/description — per the existing `ContactBankSettings`-style
      singleton/snippet pattern rather than a full page type, pending the
      design pass confirming placement), template, and the home-page slot
      itself.
- [ ] **3. Content:** the maintainer adds the 2026-08-06 camp as the first
      real entry once the feature ships.

**Priority: P0** — time-sensitive; the camp this was raised about is
2026-08-06.

## Sequencing

Design (1) blocks implementation (2), which blocks content (3). Single
branch/PR once the design handoff lands and a task file is written:
`feat/home-upcoming-events` (indicative, confirm at branch-creation time).

## Feature flags (Stage 6)

No runtime flag — standing decision for this repo (see
[README.md](README.md) "Plan structure"). This is new but low-traffic (a
small home-page card list) and ships via Wagtail's own draft/publish gate,
which is the natural gate here.

## Release plan (Stage 10)

- **How it ships:** merges to `main` via Render's existing auto-deploy on
  merge (per [docs/deploying.md](../../docs/deploying.md)); no phased
  rollout needed for a presentation-only addition on a low-traffic
  pre-launch site.
- **Who gets access, and when:** no access changes.
- **Who is informed:** the maintainer posts the shipped feature back to "The
  Family Network," consistent with how this group has operated throughout.
  Must be confirmed live **before 2026-08-06** given the camp date it's
  meant to serve.
- **Gating check / rollback:** standard — `/code-review` clean, CI green,
  Render deploy health check; rollback is redeploying the previous
  `vYYYY.MM.DD`-style tag per the personal lifecycle doc's dated-tag
  convention.
