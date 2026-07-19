# Plan 07 — Accounts & Roles

_Status: Drafted · Depends on: 01 Project foundation (03 Design system only lightly — see note) · Next: 08 Data pipeline_

## Goal

The small set of logins the clinic actually needs, and the permissions attached
to each — specifically the two roles the pipeline and the AI workflow depend on:
an **Uploader** who can hand a raw Excel export to the system but never sees
patient data rendered back, and an **Approver** who reviews and publishes
AI-drafted content. This is the plan that turns CLAUDE.md invariant #4
("human-in-the-loop — every AI-generated page is a draft a person approves
before publish") from a stated intention into an actual permission boundary:
the "publish" button belongs to a named human role and to nobody else.

Per [architecture-and-ai-brief.md §2](../../docs/architecture-and-ai-brief.md),
the whole system has **≤ 20 people, most of whom are viewers of public pages
and need no login at all** — only 2–4 people ever authenticate. So this is
deliberately a *small* plan: no public accounts, no self-signup, no custom auth
framework. It is mostly about assigning the right subset of Wagtail's existing
permissions to two or three groups.

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
- Three Wagtail **Groups** — Uploader, Approver, Administrator — with a
  documented, minimal permission set each.
- One custom Django permission (`can_upload_export`) that Plan 08's upload view
  will require. Defined here so the group exists before the view that needs it.
- The account-provisioning process: how the ~2–4 real accounts get created and
  assigned to groups (by an Administrator, in the admin — no self-signup).
- Making the **publish** permission on content page types belong to Approver /
  Administrator only, so AI-drafted drafts (Plan 09) can be *created* by
  automation but only *published* by a human. This is the enforcement point for
  CLAUDE.md invariant #4.

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

## The three roles

| Role (Wagtail Group) | What they can do | What they explicitly cannot do |
|---|---|---|
| **Uploader** | Log into `/admin/`; reach **only** the Plan 08 upload view (via the `can_upload_export` permission); upload a raw export. | Add/edit/publish any page; view or edit images, documents, or content; **see any patient data rendered back** — the upload view returns only a success/aggregate summary, never the parsed rows (a Plan 08 design constraint, noted here because it's a role expectation). |
| **Approver** | Everything an editor does — create/edit content — **plus publish**. Reviews AI-drafted newsletter/report drafts and clicks publish. This is the human-in-the-loop role. | Manage other users/groups; change site settings; upload raw exports (unless also in the Uploader group). |
| **Administrator** | Full Wagtail admin: manage users and groups, site settings, everything the other two roles can do. The maintainer. | — (this is the trusted role; kept to the fewest people possible). |

Roles are **groups, not user subclasses** — a person can hold more than one
(e.g. the maintainer is realistically Administrator + Uploader + Approver). The
groups are defined independently so that *separation of duties is possible* if
the clinic wants it (a data-entry person who only uploads, a senior clinician
who only approves), even if in practice one or two people wear several hats at
launch. Whether uploading and approving must be different people is an open
question below.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Auth foundation | Django auth + **Wagtail Groups & permissions**, no custom framework | Reuses what Wagtail already enforces everywhere; see "Why not a custom auth system." |
| User model | Stay on Django's **default `auth.User`** (Plan 01 didn't introduce a custom one, and it's now migrated/"Done") | Roles are expressed as group membership, not user fields, so `AbstractUser` buys nothing here and swapping it post-Plan-01 is a disruptive migration. Flagged as an open question in case the maintainer wants the retrofit while the user table is still empty. |
| Roles | Three groups: **Uploader, Approver, Administrator** | Provisioned as a **data migration** (so the groups + their permission sets are version-controlled and reproducible, not hand-clicked per environment). Uploader/Approver roughly parallel Wagtail's stock Editors/Moderators, but named for this project and pared down. |
| Upload permission | One **custom Django permission** `can_upload_export` (on a Plan 08 model, or a dedicated permission-holder model), assigned to the Uploader (and Administrator) group | The only custom piece. Plan 08's upload view does `@permission_required` on it; no page-permission fits an upload. |
| Uploader admin surface | Uploader gets **`access_admin`** but **no** page/image/document/settings permissions | Result: they log in and see essentially just the Upload menu item — the smallest possible admin footprint, and structurally unable to browse content or data. A Wagtail admin hook hides menu items they lack permission for. |
| Publish = human only | The **publish** permission on every publishable content type (Newsletter, Camp Report, Daily/Monthly Report, core pages) is granted to **Approver + Administrator only** | This *is* the human-in-the-loop gate. Plan 09's AI code will call `save_revision()` (create a draft), which needs no publish permission — so automation can draft but is structurally incapable of publishing. Matches Plan 02's and Plan 06's stated reliance on the draft/publish workflow. |
| Account provisioning | Administrator creates each account in the Wagtail admin (Settings → Users), assigns groups, user sets their own password on first login via Django's password-reset flow | No self-signup, no seeded passwords in the repo or in fixtures. ~2–4 accounts total, created by hand — automating this isn't worth it at this scale. |
| Password policy | Django's `AUTH_PASSWORD_VALIDATORS` (length, common-password, numeric) enabled; HTTPS-only session cookies | Baseline already available from Django; just confirm it's on in prod settings. |
| 2FA | Proposed **optional but recommended** via `wagtail-2fa` for Approver/Administrator | These accounts can publish public content and reach the upload view. Flagged as an open question — worth it for so few, privileged accounts, but adds a dependency and a login step. |

## What gets built (code — this plan's PR)

The deliverable is small and mostly declarative:

1. **A groups/permissions data migration** — creates the Uploader, Approver, and
   Administrator groups and attaches each group's permission set (Approver/Admin
   get publish; Uploader gets only `access_admin` + `can_upload_export`). Being a
   migration, every environment (local, CI, prod) gets identical, reviewable
   roles with no manual clicking.
2. **The `can_upload_export` custom permission** — declared in `Meta.permissions`
   on a small model owned by this plan (or Plan 08's ingest model if sequencing
   makes that cleaner; if the model lands in Plan 08, this plan declares the
   permission's *intent* and the migration references it). Plan 08's view is the
   only consumer.
3. **A Wagtail admin menu hook** — hide admin menu items a user's group lacks
   permission for, so an Uploader sees a near-empty admin (just Upload), not a
   wall of sections they can't use.
4. **Prod settings confirmation** — password validators on, secure/`HttpOnly`
   session + CSRF cookies, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` true in
   prod (a quick audit, likely already true from Plan 01).
5. **Tests** — see acceptance criteria; the important ones assert the *negative*
   permissions (an Uploader cannot publish, cannot reach content editing; a
   non-Approver cannot publish a draft).

## Account setup checklist (post-deploy, via Wagtail admin — not part of this PR)

Once the migration above has created the groups, an Administrator:

1. Creates each real person's account (Settings → Users), assigns the right
   group(s). Confirm the actual list with the maintainer (brief §8 open item:
   "Confirm the list of admin accounts (uploaders/approvers)").
2. Sends each new user through the password-reset flow to set their own password
   (no shared or seeded passwords).
3. (If 2FA is adopted) walks Approver/Administrator accounts through enrolment.

## Acceptance criteria

- The three groups exist after migration, in every environment, with the
  documented permission sets — no manual admin clicking required to reproduce.
- A user in **Uploader only** can log into `/admin/`, reach the (Plan 08) upload
  view, and **cannot** add, edit, or publish any page, nor browse images,
  documents, or content — verified by tests, not just by the menu being hidden.
- A user in **Approver** can publish a content page; a user **not** in
  Approver/Administrator **cannot** publish, only draft — verified by a test that
  attempts a publish and asserts it's denied.
- The `can_upload_export` permission exists and gates the upload path (the test
  can be a placeholder assertion until Plan 08's view lands, then tightened).
- No credentials, seeded passwords, or real account emails are committed; the
  groups migration contains permissions only, no users.
- `ruff check` and `pytest` pass in CI.

## Privacy / security guardrails to bake in now

- The Uploader role is defined by *exclusion*: it starts from zero permissions
  and is granted only the two it needs, rather than starting from an editor and
  removing things — so a future new content type doesn't accidentally become
  Uploader-visible.
- "Publish" is a scarce, human-held permission by construction, which is what
  makes CLAUDE.md invariant #4 enforceable rather than aspirational.
- Session/CSRF cookies secure + HTTP-only in prod; password validators on.

## Open questions for the maintainer

- **Who are the actual people, and how many hold each role?** (brief §8's
  standing open item.) Specifically: is there anyone who should be Uploader-only
  (data entry, never publishes), or does everyone who uploads also approve?
- **Separation of duties** — should the person who uploads a day's export be
  *forbidden* from also being the one who approves/publishes content derived
  from it, or is one trusted person doing both acceptable at this scale?
- **2FA** — adopt `wagtail-2fa` for the privileged (Approver/Administrator)
  accounts, or rely on strong passwords + HTTPS for now given how few accounts
  there are?
- **Custom user model** — retrofit `AbstractUser` now while the user table is
  effectively empty (cheap now, painful later), or commit to Django's default
  `auth.User` since roles are group-based and don't need extra user fields?
