# Plan 19 — "The Family Network" WhatsApp feedback triage (July 2026)

**One-line:** triage the open feature requests and bug reports left in the
family WhatsApp group ("The Family Network") between 2026-07-19 and
2026-07-28 into tracked, sequenced work — a backlog to slice into follow-up
plans (Stage 6), not a single-PR plan itself. Same shape as
[Plan 11](11-stakeholder-feedback-2026-07.md), scoped to this one chat and
this one review round.

## Background — why now

The maintainer's family/stakeholder group ("The Family Network") reviewed the
early site drafts, the June newsletter, and the new clinic dashboard over
several days and left feedback inline in WhatsApp — a mix of bug reports,
feature requests, and content corrections, plus a lot of unrelated family
chatter (birthdays, an anniversary, condolences) that's excluded here as
noise.

**Source:** WhatsApp Web, group "The Family Network", read back to
2026-07-19 (skill: `whatsapp-feedback`, cursor advanced to 2026-07-28 — see
`.claude/state/whatsapp-feedback-log.csv`, gitignored). Treat the chat as a
point-in-time capture, same rule as Plan 11's Google Doc — this plan is the
durable, structured version; the chat itself is not re-read going forward
for these items.

**Grounding pass done before filing tracks below (Stage 3):** checked the
current repo state for each item before assuming it's still open, rather
than filing the whole raw list blind. Two items turned out to be *already
resolved* by merged work the chat itself doesn't reflect (the family was
reacting to a since-updated live site):

- The 2026-07-25 "patient notes shouldn't be viewable" concern (Saturday,
  Dawood) is exactly the re-identification gap **Plan 18
  ([`18-notes-privacy-remediation.md`](18-notes-privacy-remediation.md))**
  fixed the same day — merged, deployed, scrub confirmed. No action here.
- The "Donate menu item stays highlighted and misleads people about where
  they clicked" concern (Saturday, Dawood) matches **Plan 18
  ([`18-mobile-menu-and-dashboard-responsive.md`](18-mobile-menu-and-dashboard-responsive.md))
  Track A** — "Donate moved out of the page list into its own CTA block."
  Merged. No action here.

Both are referenced only for completeness; they are not tracks below.

## Milestones by track

### Track A — Home page: About / founders section

- [ ] **A1.** The home page "starts very abruptly" (Dawood, 2026-07-19) —
      needs an About-style section and a short note from the founders before
      pivoting into the existing service/impact content.
      **Grounding (Stage 3):** confirmed against
      `apps/core/templates/core/home_page.html` — the page is composed
      entirely from the Plan 03.5 StreamField block kit (hero → live-impact
      band → StreamField body → report/newsletter teasers), with no About or
      founders-note section anywhere in it or in `apps/core/templates/`
      (`grep -rli "founder"` returns nothing). This is a real, confirmed gap,
      not a stale complaint about an old draft.
      **Precedent map:** the standalone `AboutPage` type already exists
      (`apps/core/migrations/0002_..._aboutpage_..._and_more.py`) with its own
      content — this track is about **surfacing a short teaser/excerpt of it
      on the home page**, mirroring the existing "latest report" /
      "latest newsletter" `feature_split.html` teaser pattern in
      `home_page.html` rather than inventing new markup. A "note from the
      founders" reads as a pull-quote variant of that same partial.
      **Priority: P1** — first-impression content gap on the live public
      site, flagged independently by a stakeholder.

### Track B — Home page: upcoming events / camps column

- [ ] **B1.** "Can we place a column on side to upload our events? Like the
      upcoming camp on 6 August" → "On the landing page" (Amanullah,
      2026-07-28, most recent item in the chat).
      **Grounding (Stage 3):** confirmed no events/upcoming-camp concept
      exists anywhere yet — `grep -rli "upcoming|event"` across
      `apps/core/templates/` and `templates/` returns nothing but an
      unrelated hit in `templates/partials/nav.html`. There is no `EventPage`
      or camp-calendar model in `apps/core/models.py` today (camps currently
      only show up after the fact, as camp *reports* via the pipeline —
      Plan 06/08 — not as upcoming announcements). This is new scope, not a
      surfacing job like Track A.
      **Open design question to settle before slicing into a task (Stage 2):**
      is this a lightweight, admin-editable list (e.g. a small
      `UpcomingEvent` snippet/model with date + title + optional link,
      rendered as a sidebar card on the home page) or does it need its own
      page type? Given the maintainer's own steer elsewhere in this chat
      toward *not* opening new tabs/pages for small things (see Track C), a
      snippet-backed card list is the better first cut — mirrors the
      existing `ContactBankSettings`-style singleton/snippet pattern rather
      than a full page type. Needs a maintainer decision, not an invented
      one, before a task file is written.
      **Priority: P0 within this plan** — time-sensitive (the camp
      Amanullah named is 2026-08-06, so this has a real deadline attached).

### Track C — Contact / Zakat: expandable inline details

- [ ] **C1.** "We can turn these into expandable options. Like you click
      contact and it displays our number underneath. Or when you click zakat
      it gives the details underneath — like you don't open a new link or
      tab" (Mubarika Y, 2026-07-19), plus "All of you will be looking at it
      on your phone too" as the stated reason (mobile-first).
      **Grounding (Stage 3):** confirmed against
      `apps/core/templates/core/contact_page.html` (current, post-redesign)
      and `templates/partials/nav.html` — Contact and Zakat & Sadaqa are
      still plain nav links to full pages/sections, no inline
      expand/disclosure behaviour exists. Real, still-open gap.
      **Precedent map:** a plain HTML/CSS `<details>`/`<summary>` disclosure
      pattern already exists and is well-documented — `templates/partials/nav.html`
      (the mobile nav menu, and its nested `.nav-dropdown__details` flyout)
      plus the matching rules in `static/css/components.css`. No JS beyond
      the browser's native `<details>` toggle. Mirror that exact pattern for
      the Contact/Zakat disclosures instead of inventing a new one or
      reaching for a JS toggle — it's the named precedent Stage 7 asks for,
      not a grounding gap.
      **Priority: P2** — UX polish, not a bug; explicitly framed by the
      requester as a nice-to-have for phone users.

### Track D — Housekeeping / verify-before-build

- [ ] **D1.** "It has the wrong & sign here" (Dawood, 2026-07-19, on the
      *very first* draft link shared that day). **Likely stale** — the site
      has been redesigned and re-released multiple times since (newsletter
      launch, dashboard launch, v2026.07.25-8, Plan 18's mobile-menu pass).
      No specific page/location was given, so this can't be grounded to a
      file. **Action: don't file a fix task blind.** Next time the home page
      or nav is touched (e.g. as part of Track A or C above), do a quick
      pass for stray literal `&` vs `&amp;` rendering as a side check; if it
      still reproduces, it'll surface then. Not worth its own branch on this
      little evidence.
- [ ] **D2.** "Within menu option contact there's another contact and other
      buttons that are not clickable" (Dawood, 2026-07-19).
      **Grounding (Stage 3):** the *current* `contact_page.html` (read in
      full above) is a clean three-card layout (Get in touch / Zakat &
      Sadaqa / Follow) with no duplicate contact block and no dead buttons —
      it reads as already fixed by a subsequent redesign the chat doesn't
      mention. **Action:** verify live on a phone (matches the "look at it
      on your phone too" note from the same thread) before closing outright;
      don't assume from source alone given this is exactly the kind of
      claim Stage 8 says to verify by running the real thing, not reading
      the diff. If confirmed fixed, close with no branch.
- [ ] **D3.** "Don't use emdash (—) at all" (Dawood, 2026-07-19). Not a code
      change — a content/copy style rule. **Action:** add as a line to
      [`docs/content-operations.md`](../../docs/content-operations.md) (the
      doc that already governs how content gets published) so it's applied
      consistently by whoever drafts future newsletters/pages, AI-assisted
      or not — rather than opening a branch for it.

## Sequencing

No hard cross-track dependencies. Suggested order, given B1's external
deadline (2026-08-06 camp) and D-track being near-zero-cost:

1. **D3** (docs-only, five minutes) and **D1/D2 verification** (no branch
   unless something reproduces) — clear the housekeeping first since it
   costs almost nothing.
2. **B1** — has an actual date attached; settle the design question (snippet
   vs. page type) with the maintainer first (Stage 2), then slice into a
   task file. Highest real priority in this plan.
3. **A1** — teaser-of-existing-AboutPage pattern, well-precedented, can run
   independently of B1.
4. **C1** — polish, no deadline pressure; fine to land last or get bumped to
   a later plan if the queue is long.

Each track becomes its own branch/PR per Stage 6 (one task = one PR) once
sliced: names indicative, confirm at branch-creation time —
`feat/home-founders-section` (A1), `feat/home-upcoming-events` (B1),
`feat/contact-zakat-expandable` (C1), `docs/no-emdash-style-rule` (D3).

## Feature flags (Stage 6)

Same standing decision as every other plan in this repo (see
[README.md](README.md) "Plan structure"): no runtime flag on any of these.
A1 and C1 are presentation-only changes to already-live pages with no
partial-slice risk; B1 is new but low-traffic (a small home-page card list)
and ships via Wagtail's own draft/publish gate, which is the natural gate
here.

## Release plan (Stage 10)

- **How it ships:** each track's PR merges independently to `main` via
  Render's existing auto-deploy on merge (per
  [docs/deploying.md](../../docs/deploying.md)); no phased rollout needed —
  these are presentation changes on a low-traffic pre-launch site, not
  data/pipeline changes.
- **Who gets access, and when:** no access changes.
- **Who is informed:** the maintainer posts each shipped item back to "The
  Family Network" as they've been doing throughout this thread (e.g. the
  v2026.07.25-8 release-notes link) — informal but consistent with how this
  group has operated the whole time; B1 in particular should be confirmed
  live before 2026-08-06 given the camp date it's meant to serve.
- **Gating check / rollback:** standard — `/code-review` clean, CI green,
  Render deploy health check; rollback is redeploying the previous
  `vYYYY.MM.DD`-style tag per the personal lifecycle doc's dated-tag
  convention.
