# Plan 21 — Retire the camp-report page type

**Status:** ✅ Done · **Date:** 2026-08-10

One-line summary: remove `CampReportPage` / `CampReportIndexPage` and every
surface that feeds them, after converting the one remaining camp report into a
newsletter issue — camps become newsletter issues, full stop.

## Why

Maintainer decision, 2026-08-10. Camp reports and newsletter issues turned out
to be the same thing wearing different clothes, and the newsletter is the
better-designed of the two: it has a masthead, an impact stat band, highlights
and "In focus" photo splits, while `CampReportPage` has a date, a location and
a rich-text blob.

This came to a head in [Plan 20](20-sugar-camp-report-and-july-newsletter.md).
The Sugar Camp was published as a camp report, the maintainer asked for the
newsletter's format, and the cheapest route was to republish it as a
`NewsletterPage` — which worked so well it made the camp-report type look
redundant. Rather than maintain two archives, retire one.

## The correction this plan exists to handle

> **Corrected 2026-08-10, after task 1 ran.** The table and D1/D2 below were
> written on the assumption that the Inauguration Report still needed
> converting into a *new* `NewsletterPage`. It was converted — and then the
> conversion was **reverted**, because the maintainer pointed out that the
> existing newsletter **"A new chapter begins" (page 52) already *is* the
> inauguration report**: it carries the inauguration, the free camp, the 64%
> Zakat figure and the May–June 2026 photos. So **no new page was created**
> (the short-lived `NewsletterPage` id 78 was created and deleted again), and
> the actual pre-code state was the one in the next section. One loose end
> nobody has reconciled: page 52 says the camp served **379** patients while
> the retired camp report said **384**. Deliberately not touched here.

The maintainer's framing was "the current camp report we have, we've already
converted into a newsletter". **That was true of one of the two, not both:**

| Page | State *as this plan was drafted* |
|---|---|
| Free Sugar Camp (6 Aug 2026) | ✅ already a `NewsletterPage` (id 77); old camp URL 301s across. The `CampReportPage` (id 76) is unpublished but still exists |
| **Inauguration Report** (16 May 2026) | ❌ **still a live `CampReportPage`** at `/en/camp-reports/inauguration-report/` |

### State after task 1, verified read-only against production 2026-08-10

| Object | ID | State |
|---|---|---|
| `CampReportIndexPage` "Camp Reports" | 9 | **live** but empty, `/en/camp-reports/`, 2 children, 1 revision |
| `CampReportPage` "Inauguration Report" | 15 | unpublished, 1 revision, still holds `report_document` (Document 1) |
| `CampReportPage` "Free Sugar Camp Report" | 76 | unpublished, 2 revisions |
| `NewsletterPage` "Free Sugar Camp" | 77 | live, `/en/newsletters/free-sugar-camp/` |
| `NewsletterPage` "A new chapter begins" | 52 | live, `/en/newsletters/a-new-chapter-begins/` |
| Redirect 1 | — | `/en/camp-reports/free-sugar-camp-report` → page **77**, permanent |
| Redirect 2 | — | `/en/camp-reports/inauguration-report` → page **52**, permanent |

Both retired URLs therefore already redirected before any code shipped. The
one gap the code PR had to close was the **archive index itself**: nothing
redirected `/en/camp-reports/`, and page 9 was still live, so it would start
404ing the moment the migration deleted it.

## Decisions to confirm before building

| # | Question | Resolved |
|---|---|---|
| D1 | What happens to the two existing `CampReportPage` rows? | **Both deleted**, along with the index page and the models. No conversion was needed in the end — the Sugar Camp was already a `NewsletterPage` (id 77) and the Inauguration Report's content already existed as page 52. Both pages were unpublished before deletion and both URLs already redirected. |
| D2 | Where does the Inauguration Report's attached PDF go? | **Resolved as a content op, 2026-08-10, no code.** Page 52's body now ends with a paragraph block carrying `<a linktype="document" id="1">Download the full inauguration report (PDF)</a>`, resolving to `/documents/1/The_Thandkoi_Clinics_final_V15.pdf`. `NewsletterPage` gained no new field. That paragraph is the **only** link to that document on the site — don't sweep it. |
| D3 | Do the newsletter issues keep the camp framing? | Yes, via `issue_label` — the Sugar Camp already uses `issue_label = "Camp Report"`, so the masthead reads "AUGUST 2026 · CAMP REPORT". Costs nothing and keeps camps findable. |
| D4 | Does `/reports/` keep a camp section? | No — the camp teaser goes with the type. But `/reports/` gains a line noting its figures exclude camps (Plan 20 Track C, already agreed) and can link to Newsletters instead. |
| D5 | Migration strategy | **Reversed during implementation — schema first, data second.** The proposal (data migration deletes the page rows, then a schema migration drops the models) cannot work once the model classes are gone from `models.py`, and both variants of it were shown to break a local replica of production. See "What the migration order had to become" below. |

## Scope

**In scope**

1. ~~**Convert the Inauguration Report** to a `NewsletterPage`~~ — **done
   differently** (see the correction above): no new page was needed, because
   the existing "A new chapter begins" (page 52) already was the inauguration
   report. Its PDF was linked into that page's body, and a redirect for the
   old camp URL points at it.
2. **Delete the models** `CampReportPage` and `CampReportIndexPage` from
   `apps/core/models.py`, plus:
   - `apps/core/templates/core/camp_report_page.html`
   - `apps/core/templates/core/camp_report_index_page.html`
   - `CampReportIndexPageFactory` / `CampReportPageFactory` in
     `apps/core/factories.py`
   - the `core.CampReportIndexPage` entry in `HomePage.subpage_types`
     (`models.py:136`)
3. **Unwire the `/reports/` camp teaser** — `ReportIndexPage.camp_reports_intro`
   (a model field, so a migration), its `get_context` block
   (`apps/pipeline/models.py:441–444`), the import at `models.py:33`, and the
   template section at `report_index_page.html:134–149`.
4. **Seeding** — drop the `(CampReportIndexPage, "Camp Reports", "camp-reports")`
   row from `seed_initial_content.py:57` and its assertions in
   `test_seed_initial_content.py`.
5. **Redirects** for both retired URLs (the Sugar Camp's already exists).
6. **Tests** — remove camp-report tests; keep and adapt any that assert the
   *consent gate*, which must not be lost with the type (it also guards
   newsletter photos and the Gallery).
7. **Docs** — `docs/content-operations.md`, Plan 06's entry, the plans index,
   and `CLAUDE.md` if it names the type.

**Out of scope**

- The `og-camps.jpg` social card and `scripts/generate_og_cards.py`'s entry for
  it — dead weight afterwards, but harmless; sweep separately.
- `GalleryPage` and `ConsentedImageBlock`, which are independent of this type.
- Plan 20's Track B (the July graphic).

## Risks

- **Deleting a Wagtail page type is not a normal migration.** Page rows live in
  `wagtailcore_page` with treebeard `path`/`depth`/`numchild` bookkeeping plus
  revisions. Deleting model rows without going through Wagtail's own API can
  corrupt the tree. The data migration must delete via `Page` methods, and the
  schema migration must run after.
- **Two live URLs disappear.** Both need redirects, and the inauguration one is
  the older, more likely to be linked externally.
- **Don't lose the consent gate.** `CampReportPage.photos` is one of
  `ConsentedImageBlock`'s load-bearing users (Plan 06). Removing it must not
  quietly reduce the test coverage that proves an unconsented photo can't
  publish.
- **Revisions.** Both pages have revision history that dies with them. If any
  of it matters, export first.

## What the migration order had to become (2026-08-10)

D5's proposed order — data migration first, schema migration second — is the
normal convention and it is wrong here. Both ways of writing it were tried
against a local replica of production's page tree, and both broke it:

- **Delete the page rows first, via the `Page` API.** Fails outright.
  Django's cascade collector walks the *live app registry*, and by the time
  these migrations run the model classes are already gone from
  `apps/core/models.py`. Deleting a `wagtailcore_page` row therefore never
  reaches the concrete `core_campreportpage` row hanging off it, and the
  deferred foreign key blows up at COMMIT: *"still referenced from table
  core_campreportpage"*.
- **Delete the concrete rows first, via the migration-state model.** Worse,
  because it *appears* to work. A historical model of a multi-table-
  inheritance child cascades **upward**: `CampReportPage.objects.all()
  .delete()` takes the parent `wagtailcore_page` row with it as a plain
  Django delete, with no `treebeard` bookkeeping at all. The pages vanish and
  the home page is left claiming a child it no longer has (`numchild=2`, one
  actual child) — exactly the silent tree corruption this plan's Risks
  section warns about, caught only by `Page.find_problems()`.

**What shipped:** `core/0020` drops the tables, then `core/0021` deletes the
now-orphaned page rows through Wagtail's own `Page` API. Wagtail tolerates
the intermediate state deliberately — `Page.get_specific()` degrades to the
base page when a content type has no model behind it — and the tree
bookkeeping all lives on `wagtailcore_page`, which the `Page` API maintains
correctly. `0021` finds its pages **by content type, never by id**, and
refuses to run if any `Redirect` points at a page it is about to delete
(`Redirect.redirect_page` is `CASCADE`, so such a redirect would be silently
destroyed).

Verified on the replica: pages gone, both redirects still resolving to their
live newsletter targets, `Page.find_problems()` clean, tables and
`camp_reports_intro` dropped. The fresh-install path no-ops, and the redirect
guard was exercised deliberately — it refuses with an actionable message,
rolls back atomically, and the documented repoint-and-re-run recovers.

## Release plan

- **How it ships:** content work first (no deploy), then one PR: schema
  migration → data migration → template/seed/test cleanup (order corrected,
  above). Verified against a local replica of production's page tree, since
  the risk is in the migration, not the code.
- **One post-deploy content op, required.** `/en/camp-reports/` (the archive
  index) has **no redirect** — the other two URLs already do, but nothing
  covers the index, and page 9 stops existing the moment this deploys. Add it
  over SSH right after the deploy, pointing at the newsletter archive, the
  same way redirects 1 and 2 were created:

  ```python
  from wagtail.contrib.redirects.models import Redirect
  from apps.core.models import NewsletterIndexPage

  target = NewsletterIndexPage.objects.live().first()
  Redirect.objects.get_or_create(
      old_path="/en/camp-reports",  # Wagtail normalises: no trailing slash
      defaults={"redirect_page": target, "is_permanent": True},
  )
  ```

  Deliberately a content op rather than part of the data migration: a
  migration creating it would have to cope with fresh installs where the
  target page doesn't exist yet, and redirects live in the production
  database as content anyway.
- **Gating check:** all three retired URLs resolve — the two existing
  redirects still `301`, and `/en/camp-reports/` no longer 404s once the
  content op above has run; `/reports/` renders with no camp section and no
  template errors; the consent test still goes red when consent is removed
  (see [[feedback-mutation-test-retargeted-guards]] — prove the guard still
  fails, don't assume). Verify the URLs with `curl`, not `WebFetch`, which
  caches per URL for 15 minutes.
- **Rollback:** revert the PR; the pages are gone, so restoring them means
  re-entering content — which is why the conversion happens first and
  separately.
- **Who's informed:** the other Administrators — "Camp Reports" disappears from
  the admin page-type menu.
