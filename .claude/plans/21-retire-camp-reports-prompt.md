# Kickoff prompt — Plan 21: retire the camp-report page type

Hand the section below to a fresh Claude Code session in this repo. Everything
above the rule is instructions for *you*, the human, and is not part of the
prompt.

**Before you start the session, answer D2** (where the Inauguration Report's
PDF goes) — the first task is blocked on it. The prompt asks again if you
haven't.

**Do it in two sessions, not one.** Task 1 is a production content operation
with no code; tasks 2–7 are a code PR. Mixing them means a half-finished model
deletion sitting next to a live-content write. The prompt is written to stop
after task 1 and check in.

---

## Prompt

Implement **Plan 21 — retire the camp-report page type**.

### Read first, in this order

1. `.claude/plans/21-retire-camp-reports.md` — the plan. Its decisions D1–D5
   and its "Risks" section are binding.
2. `CLAUDE.md` — privacy invariants and workflow conventions. Note especially:
   review before a PR ever opens, PRs stay draft, label by Conventional-Commit
   type, and content changes are not code changes.
3. `docs/content-operations.md` — the SSH path task 1 uses.
4. `~/.claude/CLAUDE.md` — the development lifecycle.

### The one thing most likely to go wrong

**The Inauguration Report is still a live `CampReportPage`.** Only the Sugar
Camp was converted (Plan 20). Do not delete any model until the Inauguration
Report has been converted and verified, or you will take a live, externally
linked page off the site.

Current production state:

| Object | ID | State |
|---|---|---|
| `CampReportIndexPage` "Camp Reports" | 9 | live, `/en/camp-reports/` |
| `CampReportPage` "Inauguration Report" | 15 | **live**, `/en/camp-reports/inauguration-report/`, has `report_document` (Document id 1) |
| `CampReportPage` "Free Sugar Camp Report" | 76 | unpublished, superseded |
| `NewsletterPage` "Free Sugar Camp" | 77 | live, `/en/newsletters/free-sugar-camp/` |

Verify these IDs with a read-only query before writing anything — they were
accurate on 2026-08-10 and production content can move.

### Task 1 — convert the Inauguration Report (content op, no code, no PR)

Create a `NewsletterPage` under the Newsletters index carrying the Inauguration
Report's content, then unpublish (**never delete**) `CampReportPage` id 15 and
add a permanent redirect from its URL to the new page.

Mirror exactly what Plan 20 did for the Sugar Camp — same shape, same
guardrails:

- `issue_date` `2026-05-16`; `issue_label` `"Camp Report"` so the masthead
  reads "MAY 2026 · CAMP REPORT".
- Its verified figures, which are already published on the existing page:
  **384 patients served, 260 female, 174 children aged 0–17, 245 Zakat
  beneficiaries (64%)**. Do not recompute or "improve" these — they are the
  published historical record of that day, not pipeline data.
- The `report_document` (Document id 1) per **D2** — ask the maintainer if
  they haven't already told you which way.
- Use Wagtail's own API over SSH (`page.add_child()`,
  `save_revision().publish()`), never raw SQL against page tables.
- Read before you write; make the script idempotent so a re-run can't create a
  duplicate.
- Verify over HTTP afterwards: the new page renders, and the old URL returns
  **301**. Beware `WebFetch`'s 15-minute per-URL cache — if you fetched the URL
  earlier in the session, add a cache-busting query string or you will read a
  stale copy and think the change failed.

**Stop here and report.** Do not start task 2 in the same session.

### Tasks 2–7 — the code PR

Branch `plan/21-retire-camp-reports` off `main`.

**2. Data migration** — delete the two remaining `CampReportPage` rows (15, 76)
and the `CampReportIndexPage` (9) through Wagtail's `Page` API, not raw
deletes. These are treebeard nodes with `path`/`depth`/`numchild` bookkeeping
plus revisions; raw SQL corrupts the tree.

**3. Delete the models and their surfaces.** Verified against `main` at
`ede407d`:

- `apps/core/models.py` — `CampReportIndexPage` (~949), `CampReportPage`
  (~983), the `"core.CampReportIndexPage"` entry in `HomePage.subpage_types`
  (~136), and the docstring references at ~19, ~307, ~755, ~767.
- `apps/core/templates/core/camp_report_page.html` and
  `camp_report_index_page.html` — delete both.
- `apps/core/factories.py` — imports (19–20) and both factories (218–228).
- `apps/core/management/commands/seed_initial_content.py` — import (34) and
  the `(CampReportIndexPage, "Camp Reports", "camp-reports")` row (57).
- `apps/core/test_seed_initial_content.py` — 15, 31, 67.

**4. Unwire the `/reports/` camp teaser.**

- `apps/pipeline/models.py` — the import (33), `camp_reports_intro` field
  (~383) and its panel (~391), the `get_context` block (~441–444), and the
  docstring references at ~362, ~370, ~558. The field drop needs a migration.
- `apps/pipeline/templates/pipeline/report_index_page.html` — the camp section
  at ~134–149, and the file's own header comment at ~6.
- **Leave the "figures exclude camps" line in `daily_reports_intro` alone.**
  It is admin-entered content, still true, and not part of the teaser.

**5. Redirects** for `/en/camp-reports/` and
`/en/camp-reports/inauguration-report/`. The Sugar Camp's already exists.

**6. Tests.** Remove the camp-report tests (`apps/core/tests.py` ~1667, ~1687,
~1709, ~1771, ~1923; the index-template case at ~800). Before deleting
`test_camp_report_photo_block_requires_consent` (~1923), confirm the consent
gate stays covered — `test_consent_block_requires_confirmation` (~1094) and
`test_newsletter_body_photo_block_requires_consent` (~1940) cover the same
block, so coverage survives. **Verify that by breaking the gate deliberately
and watching those tests go red**, rather than assuming from the names.

**7. Docs.** `docs/content-operations.md`, Plan 06's entry, `CLAUDE.md` if it
names the type, and — in the same PR, not a follow-up — flip Plan 21's row in
`.claude/plans/README.md` to ✅ Done. (Plan 20 needed a second PR for that;
don't repeat it.)

### Out of scope

The `og-camps.jpg` social card and its entry in `scripts/generate_og_cards.py`
become dead weight but are harmless — sweep separately. `GalleryPage` and
`ConsentedImageBlock` are independent; do not touch them.

### Verification and process

- Restore a copy of production locally and run the data migration against it.
  The risk here is the migration, not the code.
- Run the full suite (`pytest`, ~464 tests) and `ruff`, and report real output.
- Both retired URLs must return **301**; `/reports/` must render with no camp
  section and no template errors.
- Give each worktree its own database (`thandkoi_<slug>`); copy `.env` from the
  main checkout, since a fresh worktree has no untracked files.
- Run the `code-review-tc` skill and work the loop **before** `gh pr create`.
  Scope re-reviews to the files a fix touched, not the whole diff again.
- Open the PR as a **draft** and label it (`feat`→`enhancement`,
  `fix`→`bug`, `chore`→`chore`). Only the maintainer marks it ready.
- After merge: run `cleanup-worktrees`.

### Rollback

The pages are gone once the migration runs, so restoring them means re-entering
content — which is exactly why task 1 happens first, separately, and is
verified before any code ships.
