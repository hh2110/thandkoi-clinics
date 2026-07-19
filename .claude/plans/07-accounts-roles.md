# Plan 07 — Accounts & Roles

_Status: Drafted · Depends on: 01 Project foundation (03 Design system only lightly — see note) · Next: 08 Data pipeline_

## Goal

The small set of logins the clinic actually needs, and the permissions attached
to each — specifically the two capabilities the pipeline and the AI workflow
depend on: **uploading** a raw Excel export (without ever seeing patient data
rendered back) and **publishing** reviewed content. Per the maintainer's PR #15
decision both capabilities are held by a single **Administrator** role (below),
but the plan still turns CLAUDE.md invariant #4 ("human-in-the-loop — every
AI-generated page is a draft a person approves before publish") from a stated
intention into an actual permission boundary: the AI/automation code holds **no
publish permission**, so every AI-generated page is a draft that a human
Administrator must review and publish.

Per [architecture-and-ai-brief.md §2](../../docs/architecture-and-ai-brief.md),
the whole system has **≤ 20 people, most of whom are viewers of public pages
and need no login at all** — only 2–4 people ever authenticate. So this is
deliberately a *small* plan: no public accounts, no self-signup, no custom auth
framework. It is mostly about assigning the right subset of Wagtail's existing
permissions to the small set of logins the clinic needs.

## Maintainer decisions (confirmed on PR #15)

These were the plan's open questions; the maintainer has now answered them, so
they are settled decisions rather than proposals:

- **One admin role, no separation of duties.** There is a single privileged role
  — **Administrator** — held by every real account. There is *no* Uploader-only
  or Approver-only person; the same trusted people upload exports and publish
  content. At this scale (a small, family-run clinic) the Uploader/Approver split
  is unnecessary, so it is not enforced. The distinct capabilities still exist in
  the permission model, but they are all granted to the one Administrator group.
- **The accounts.** Three accounts, all Administrators, provisioned by hand (see
  the account-setup checklist): `hikmatyarhasan@gmail.com`,
  `dramanullah07@gmail.com`, `syeddawood.shah93@gmail.com`. These are named in
  this plan for provisioning only — **no user rows, emails, or passwords are
  seeded into any migration or fixture** (see acceptance criteria).
- **No 2FA.** Rely on strong passwords (Django's password validators) + HTTPS.
  `wagtail-2fa` is not adopted; the dependency isn't worth it for three trusted
  accounts.
- **Default user model.** Stay on Django's default `auth.User`. No `AbstractUser`
  retrofit — roles are group membership, so the default buys everything needed.

Note on invariant #4 with one role: collapsing the human roles does **not**
weaken CLAUDE.md invariant #4. The human-in-the-loop gate is a boundary between
**people and automation**, not between two kinds of person — the AI code (Plan
09) runs with **no publish permission**, so anything it generates is always a
draft that a (now Administrator) human reviews and publishes. See "How invariant
#4 is enforced" below.

## A note on the Plan 03 dependency

This plan lives almost entirely inside the **Wagtail admin** (`/admin/`), which
ships its own styling and layout — it does not consume Plan 03's public design
system. The only place the two could touch is if the login screen gets brand
styling (logo, colours). That's cosmetic and optional, so Plan 07 is built to
stand on Plan 01 alone; treat Plan 03 as a soft, presentation-only dependency,
not a blocker. Nothing here needs a public-facing template.

## Why not a custom auth system

Wagtail is built on Django's auth, and already ships the exact primitives this
needs: **Users**, **Groups**, and per-model / per-page-type **permissions**,
all editable from the admin under Settings. It even ships two starter groups
("Editors" and "Moderators") that map closely to what we want. Building a custom
role system on top of that would mean re-implementing group membership and
permission checks that Django/Wagtail already enforce everywhere — for no gain,
and with the risk of a home-grown check being subtly weaker than the framework's.

There is exactly **one** real gap where stock Wagtail isn't enough, and this
plan fills it narrowly: the "can upload a raw export" capability isn't a
page-permission (there's no Wagtail page involved in an upload), so it needs a
single **custom Django permission** to gate Plan 08's upload view. That's the
whole extent of the custom code — one permission, not an auth system.

## Scope

**In scope**
- A single Wagtail **Administrator** group (maintainer decision, PR #15) holding
  every capability the real accounts need: admin access, content **publish**, and
  the custom `can_upload_export` permission. The Uploader/Approver split is not
  enforced (see Maintainer decisions).
- One custom Django permission (`can_upload_export`) that Plan 08's upload view
  will require. Defined here so it exists before the view that needs it.
- The account-provisioning process: how the 2–3 real accounts get created and
  assigned to the Administrator group (by an Administrator, in the admin — no
  self-signup).
- Keeping the **publish** capability with humans only where it matters for
  invariant #4: the AI/automation code (Plan 09) holds **no** publish permission,
  so AI-drafted pages can be *created* by automation but only *published* by a
  human. The Plan 08 daily report page is exempt — its numbers are
  deterministic, and its one AI-written summary sentence falls under CLAUDE.md's
  narrow, explicit invariant #4 exception (2026-07-19) — so the page may publish
  automatically (see "How invariant #4 is enforced").

**Out of scope** (later plans / never)
- The upload view itself, and everything it does with a file → **Plan 08**. This
  plan only defines the *permission* that guards it, not the view.
- AI drafting into content models → **Plan 09**. This plan guarantees the
  human-approval gate that plan relies on; it doesn't write any AI code.
- **Public / donor accounts, self-signup, social login, SSO** — the site has no
  logged-in public users by design (brief §2). Not built, not planned.
- Password *entry* automation, account creation on anyone's behalf, or storing
  credentials in the repo — out by CLAUDE.md and by this assistant's operating
  rules regardless. Accounts are created by a human admin in the running app.

## The role

Per the maintainer's PR #15 decision there is **one** privileged role, held by
all real accounts:

| Role (Wagtail Group) | What they can do | What they explicitly cannot do |
|---|---|---|
| **Administrator** | Full Wagtail admin: log into `/admin/`, upload a raw export (via `can_upload_export`), create/edit/**publish** all content, manage users/groups and site settings. Reviews AI-drafted newsletter/report drafts and clicks publish — this is the human-in-the-loop role. | Nothing is withheld from this role by design; it is the single trusted role, kept to the fewest people possible (three at launch). |

**Why one role is safe for invariant #4.** The invariant is a boundary between
**people and automation**, not between an "uploader" and an "approver" person. It
holds because the AI/automation code never receives publish permission (see
below), *not* because some humans lack it. Collapsing to one human role therefore
changes nothing about the guarantee.

**Why the Uploader-never-sees-data property survives.** It was never really a
*permission* — it is a Plan 08 design constraint: the upload view returns only a
success/aggregate summary, never parsed rows, and raw PHI is discarded in-memory
(invariants #1/#2). That holds regardless of how many roles exist, so dropping the
Uploader-only role does not expose patient data to anyone.

The role is a **group, not a user subclass**. The permission model still lets the
clinic re-introduce a narrower Uploader-only or Approver-only group later if it
ever wants separation of duties — but none is enforced now.

## How invariant #4 is enforced

CLAUDE.md invariant #4 is: *"Every AI-generated page is a draft that a person
reviews and approves before it is published."* With a single human role it is
enforced by two facts, one unchanged and one clarified on PR #15:

1. **Automation cannot publish AI content.** The AI code (Plan 09) only ever calls
   `save_revision()` — it creates a draft and is never given publish permission.
   So any *AI-generated* page can only reach the public site after a human
   Administrator opens it and clicks publish. This is the human-in-the-loop gate,
   and it does not depend on splitting the humans into roles.
2. **The Plan 08 daily report page has a narrow, explicit exception, not a
   blanket exemption.** Its numbers render from a **committed, code-reviewed
   parser** (invariant #3) — that part was always out of scope for invariant #4,
   since it's not AI-generated. The maintainer confirmed (PR #15) these pages
   publish straight to production without a draft step. On 2026-07-19 the
   maintainer additionally decided the page's one short AI-written summary
   sentence may *also* auto-publish, and CLAUDE.md invariant #4 was amended with
   an explicit, narrow exception to allow it — conditioned on a fixed-template
   prompt, an aggregates-only payload, mocked-in-CI testing with a payload
   guardrail, and never blocking the numbers if the AI call fails (see Plan 08's
   "The AI summary sentence" for the full conditions). This exception is scoped
   to that one sentence; it is not a precedent for AI content generally skipping
   review. Plan 09's newsletter narrative still reverts to the draft/approve
   path in (1).

## Decisions (confirmed on PR #15)

| Choice | Decision | Notes |
|---|---|---|
| Auth foundation | Django auth + **Wagtail Groups & permissions**, no custom framework | Reuses what Wagtail already enforces everywhere; see "Why not a custom auth system." |
| User model | Stay on Django's **default `auth.User`** | **Confirmed by maintainer** — no `AbstractUser` retrofit. Roles are group membership, not user fields, so the default buys everything needed and avoids a disruptive migration. |
| Roles | **One group: Administrator**, held by all real accounts | **Confirmed by maintainer** — no separation of duties. Provisioned as a **data migration** (version-controlled, reproducible, not hand-clicked per environment). The permission model can be re-split into Uploader/Approver groups later if ever wanted. |
| Upload permission | One **custom Django permission** `can_upload_export` (on a Plan 08 model, or a dedicated permission-holder model), assigned to the **Administrator** group | The only custom piece. Plan 08's upload view does `@permission_required` on it; no page-permission fits an upload. |
| Admin surface | Administrators get the **full** Wagtail admin | With one full-admin role there is no minimal-surface Uploader to build for, so the menu-hiding hook (previously proposed to pare an Uploader's admin down to just Upload) is **not needed**. |
| Publish gate for invariant #4 | **AI/automation code holds no publish permission**; humans (Administrators) publish AI content | The human-in-the-loop gate. Plan 09's AI code calls `save_revision()` (create a draft), which needs no publish permission — so automation can draft but is structurally incapable of publishing AI-generated pages. **Narrow exception (CLAUDE.md, 2026-07-19):** the Plan 08 daily report page — deterministic numbers from a committed & code-reviewed parser, plus one AI-written summary sentence from a fixed template over an aggregates-only payload — may publish automatically under the conditions in Plan 08's "The AI summary sentence." This is scoped to that one sentence, not a general AI-content exemption. See "How invariant #4 is enforced." |
| Account provisioning | Administrator creates each account in the Wagtail admin (Settings → Users), assigns the Administrator group, user sets their own password on first login via Django's password-reset flow | No self-signup, no seeded passwords in the repo or in fixtures. 3 accounts total, created by hand — automating this isn't worth it at this scale. |
| Password policy | Django's `AUTH_PASSWORD_VALIDATORS` (length, common-password, numeric) enabled; HTTPS-only session cookies | Baseline already available from Django; just confirm it's on in prod settings. |
| 2FA | **Not adopted** (maintainer decision) — rely on strong passwords + HTTPS | `wagtail-2fa` is not added; the extra dependency and login step aren't worth it for three trusted accounts. |

## What gets built (code — this plan's PR)

The deliverable is small and mostly declarative:

1. **A groups/permissions data migration** — creates the single **Administrator**
   group and attaches its permission set (`access_admin`, publish on all content
   types, `can_upload_export`, user/group and settings management). Being a
   migration, every environment (local, CI, prod) gets an identical, reviewable
   role with no manual clicking. **No user rows are created** — accounts are
   provisioned by hand afterwards.
2. **The `can_upload_export` custom permission** — declared in `Meta.permissions`
   on a small model owned by this plan (or Plan 08's ingest model if sequencing
   makes that cleaner; if the model lands in Plan 08, this plan declares the
   permission's *intent* and the migration references it). Plan 08's view is the
   only consumer.
3. **Prod settings confirmation** — password validators on, secure/`HttpOnly`
   session + CSRF cookies, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` true in
   prod (a quick audit, likely already true from Plan 01).
4. **Tests** — see acceptance criteria; the important one asserts the invariant-#4
   boundary: automation calling `save_revision()` creates a draft and **cannot**
   publish an AI-generated page, while an Administrator can.

(No admin menu-hiding hook is built — with one full-admin role there is no
reduced surface to hide, unlike the earlier Uploader-only draft.)

## Account setup checklist (post-deploy, via Wagtail admin — not part of this PR)

Once the migration above has created the Administrator group, an Administrator:

1. Creates each real person's account (Settings → Users) and assigns it to the
   **Administrator** group. The three accounts (maintainer-confirmed on PR #15):
   - `hikmatyarhasan@gmail.com`
   - `dramanullah07@gmail.com`
   - `syeddawood.shah93@gmail.com`
2. Sends each new user through the password-reset flow to set their own password
   (no shared or seeded passwords).

## Acceptance criteria

- The **Administrator** group exists after migration, in every environment, with
  the documented permission set — no manual admin clicking required to reproduce.
- An Administrator can publish a content page; the **AI/automation code path**
  (calling `save_revision()` without publish permission) creates a draft and
  **cannot** publish — verified by a test that attempts an automated publish and
  asserts it's denied. This is the invariant-#4 gate for AI-generated content.
- The `can_upload_export` permission exists and gates the upload path (the test
  can be a placeholder assertion until Plan 08's view lands, then tightened).
- No credentials or seeded passwords are committed, and **the migration creates no
  user rows** (permissions/groups only). Real account emails appear only in this
  plan's provisioning checklist above — never in a migration, fixture, or settings
  file.
- `ruff check` and `pytest` pass in CI.

## Privacy / security guardrails to bake in now

- **Publish permission is withheld from automation by construction.** The AI code
  (Plan 09) never receives publish permission, so an AI-generated page is always a
  draft a human Administrator must approve — this is what makes CLAUDE.md invariant
  #4 enforceable rather than aspirational. Deterministic, AI-free pages (Plan 08's
  daily report) are the only auto-published pages, and they carry no AI content.
- **The Administrator permission set is built additively from a data migration**,
  so it is version-controlled and reviewable rather than hand-clicked per
  environment.
- Session/CSRF cookies secure + HTTP-only in prod; password validators on.

## Resolved questions (answered by the maintainer on PR #15)

All four of the plan's open questions have been settled — see "Maintainer
decisions" at the top:

- **Who holds each role / separation of duties** → one Administrator role held by
  all three named accounts; no separation of duties.
- **2FA** → not adopted; strong passwords + HTTPS only.
- **Custom user model** → stay on Django's default `auth.User`.
