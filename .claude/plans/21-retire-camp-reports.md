# Plan 21 — Retire the camp-report page type

**Status:** 📝 Drafted · **Date:** 2026-08-10

**Kickoff prompt:** [21-retire-camp-reports-prompt.md](21-retire-camp-reports-prompt.md)

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

The maintainer's framing was "the current camp report we have, we've already
converted into a newsletter". **That is true of one of the two, not both:**

| Page | State |
|---|---|
| Free Sugar Camp (6 Aug 2026) | ✅ already a `NewsletterPage` (id 77); old camp URL 301s across. The `CampReportPage` (id 76) is unpublished but still exists |
| **Inauguration Report** (16 May 2026) | ❌ **still a live `CampReportPage`** at `/en/camp-reports/inauguration-report/` |

So this plan's first real task is converting the Inauguration Report. Deleting
the models before that would take a live, linked page off the site.

The Inauguration Report also has something the Sugar Camp doesn't: an attached
`report_document` (a PDF, document id 1). `NewsletterPage` has **no document
field**, so that attachment needs somewhere to go — see D2.

## Decisions to confirm before building

| # | Question | Proposed |
|---|---|---|
| D1 | What happens to the two existing `CampReportPage` rows? | Convert Inauguration Report to a `NewsletterPage`, then delete both page objects and the models. Redirects preserve both URLs. |
| D2 | Where does the Inauguration Report's attached PDF go? | Simplest: a link to the `Document` in the issue's body prose. `NewsletterPage` gains no new field. Alternative — add a `report_document` field to `NewsletterPage` — is more code for one page. |
| D3 | Do the newsletter issues keep the camp framing? | Yes, via `issue_label` — the Sugar Camp already uses `issue_label = "Camp Report"`, so the masthead reads "AUGUST 2026 · CAMP REPORT". Costs nothing and keeps camps findable. |
| D4 | Does `/reports/` keep a camp section? | No — the camp teaser goes with the type. But `/reports/` gains a line noting its figures exclude camps (Plan 20 Track C, already agreed) and can link to Newsletters instead. |
| D5 | Migration strategy | Data migration converts + deletes page rows, then a schema migration drops the models. Must be one deploy, ordered, and must not orphan `wagtailcore_page` rows. |

## Scope

**In scope**

1. **Convert the Inauguration Report** to a `NewsletterPage` (content op,
   before any code ships) — stat band from its own figures (384 patients, 260
   women, 174 children, 245 Zakat / 64%), its narrative as prose, its PDF
   linked per D2. Add a redirect for its old URL.
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

## Release plan

- **How it ships:** content conversion first (no deploy), then one PR:
  data migration → schema migration → template/seed/test cleanup. Verify on a
  local DB restored from production, since the risk is in the data migration,
  not the code.
- **Gating check:** both retired URLs return `301` to their newsletter
  equivalents; `/reports/` renders with no camp section; the consent test still
  goes red when consent is removed (see [[feedback-mutation-test-retargeted-guards]]
  — prove the guard still fails, don't assume).
- **Rollback:** revert the PR; the pages are gone, so restoring them means
  re-entering content — which is why the conversion happens first and
  separately.
- **Who's informed:** the other Administrators — "Camp Reports" disappears from
  the admin page-type menu.
