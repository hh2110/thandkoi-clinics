---
name: route-change-request
description: Classify a plain-English website change request into the right existing workflow (code change, Wagtail draft, or publish action) and hand it off. Use when the maintainer describes a site change in prose ("relabel X", "add a donor entry for Y", "publish the July newsletter") rather than naming a file or branch directly.
---

Plan 11 Track E1's design sketch (`.claude/plans/11-e1-e2-research-2026-07.md`)
found that every destination this skill routes into already exists in the
repo. This skill adds no new machinery — it only classifies a request and
hands it to the right existing path.

## Step 1 — gather context before classifying

Load, in order:

1. `CLAUDE.md` — privacy invariants, stack, workflow conventions. These
   constrain every route below and always win.
2. `.claude/plans/README.md` plus a grep of open items across
   `.claude/plans/*.md` — if the request matches an already-planned item,
   route it *and* cross-reference that item instead of treating it as
   freestanding.
3. The Wagtail page models (`apps/core/models.py`, `apps/pipeline/models.py`)
   and a targeted grep for the request's subject (page title, field name,
   template string) across `apps/*/templates` and `apps/*/models.py`. This is
   what decides "is this a template/model constant or an editable page
   field" — never guess it.

## Step 2 — classify into one of three routes

| Signal in the request | Route | Handoff |
|---|---|---|
| Names a bug, a behavior, or a template/style/logic change — anything needing a `.py`/template/CSS edit | **Code change** | Branch per CLAUDE.md naming (`feat/`, `fix/`, `chore/`, `docs/`), implement mirroring named precedent, tests + lint, `code-review-tc` loop until clean, `gh pr create --draft`. No shortcut on review. |
| Names copy, a page's text/images/ordering, or "add/update an entry on page X" where X is a real Wagtail page/model field | **Wagtail draft** | Load the target page in a Django shell (`python manage.py shell`) and call `page.save_revision()` **only** — never `.publish()`. Mirrors `apps/pipeline/newsletter_drafting.py`'s rule exactly. Leaves an editor-visible draft revision for the maintainer to review and publish themselves in the Wagtail admin. |
| Explicitly asks to make something live — "publish the July newsletter draft" (content) or "ship this / deploy" (code) | **Publish action** | Content: tell the maintainer to review and click Publish in the Wagtail admin themselves; only drive it yourself after an explicit in-session "yes, publish" for that specific page. Code: hand off to `scripts/release.sh` — it owns every precondition and confirmation gate already. |

## Step 3 — ambiguity handling

If Step 1's grep doesn't land on a single unambiguous file/field (e.g. a
figure could be a hand-typed template constant or a database field — see
Plan 11's D2 open question), say so and ask which one the maintainer means.
Don't guess. A maintainer typing a request is already in the loop, so
checking is cheap.

## Step 4 — safety rails (non-negotiable)

- Never call `.publish()` on editorial content from this skill. The one
  established exception — auto-creating an empty singleton structural
  container (an index page) and publishing it immediately — belongs to
  `report_publishing.py` / `newsletter_drafting.py`, not to requests routed
  through this skill.
- Never skip the `code-review-tc` loop before a code-change PR is opened.
- If the request's subject is `CLAUDE.md` or a privacy-relevant model, that
  is always a **code change** (so it gets full review), never a Wagtail
  draft — regardless of how the request is phrased.

## Examples

**"Relabel 'Our impact so far' to include the as-of date."**
Grep finds `ImpactStatBlock` (`apps/core/blocks.py`) is a `StructBlock` of
hand-typed `CharBlock` fields, not a page field a draft revision could touch
on its own — the heading text lives in a template. → **Code change**: edit
the template, branch `feat/impact-label-date`, tests/lint, `code-review-tc`,
draft PR.

**"Add a new donor entry for the Ali family — they donated a water cooler."**
Grep finds `DonorsPartnersPage` (`apps/core/models.py`) is a real Wagtail
page with an orderable `donors` `InlinePanel`. → **Wagtail draft**: script
that loads the page, appends the new `Donor` child object, calls
`save_revision()`. Reported back to the maintainer as "a draft is waiting
for you in the Wagtail admin" — never published automatically.

**"Publish the July newsletter draft."**
Explicit publish ask on content. → **Publish action**: confirm which draft
revision, then either point the maintainer at the Wagtail admin's Publish
button or, only after an explicit "yes, publish this one" reply, publish
that specific revision — never a bulk or inferred target.

**"Deploy what's on main."**
Explicit publish ask on code. → **Publish action**: hand off to
`scripts/release.sh`; do not reimplement its confirmation prompt here.

**"How is impact so far calculated?"**
Not a change request at all — a question. → No route. Answer directly from
the grep in Step 1 (this exact question is Plan 11's open question #1,
already answered: it isn't computed, it's hand-typed).

**"Fix the dark-mode stat ribbon."**
Names a specific visual bug in existing code. → **Code change**, same as
Plan 11's B2.
