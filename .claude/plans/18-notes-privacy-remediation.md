# Plan 18 — Free-text summary privacy remediation

**One line:** purge the free-text summaries that published below the N=3
k-anonymity floor, stop daily report pages being indexed, and keep the floor
at 3 going forward.

## Background

Stakeholder feedback, 2026-07-25 (Dawood, in the family WhatsApp group):
*"Don't think patient notes should be viewable on the website."* The site
never rendered raw notes — `DeidentifiedVisit`'s seven free-text columns are
"never rendered directly on a public page" (`apps/pipeline/models.py`). What
publishes is the Plan 14 per-group AI summary (male adults / female adults /
children) on `DailyReportPage`.

The maintainer then produced a live counterexample:
`https://thandkoiclinics.com/en/reports/2026-07-24/` carried a *children*
summary on a day with **one** child visit — reading "A child presented with
fever and pustular lesions on the head. Antipyretic and antibiotic
medications were prescribed."

Two distinct failures, both confirmed against production:

1. **The N=3 floor never ran on any published page.**
   `MIN_GROUP_VISITS_TO_SUMMARISE` (Plan 15 Track C3) is enforced in
   `report_publishing.publish_daily_report` at publish time only, with no
   backfill. It landed in commit 582a997 and deployed **2026-07-25 12:49
   UTC**. The 2026-07-24 report published **2026-07-25 04:20 UTC**; every
   other live report published earlier still. So the floor has never
   executed in production — the first report to get it will be the next
   upload.

   Audited against the production database: **14 sub-floor summaries live
   across 11 pages, 10 of them describing a group of exactly one patient.**

   | Date | Group | Patients |
   |---|---|---|
   | 2026-07-24 | children | 1 |
   | 2026-07-23 | male adults | 2 |
   | 2026-07-18 | female adults | 1 |
   | 2026-07-17 | children | 2 |
   | 2026-07-16 | female adults | 1 |
   | 2026-07-15 | female adults | 1 |
   | 2026-07-10 | male adults | 1 |
   | 2026-07-08 | children / female adults | 2 / 1 |
   | 2026-07-06 | children / female adults | 2 / 1 |
   | 2026-07-04 | children / male adults | 1 / 1 |
   | 2026-07-03 | female adults | 1 |

2. **The prompt-level guard is not a working control.**
   `_FREETEXT_SUMMARY_SYSTEM_PROMPT` instructs the model to use frequency or
   thematic language "rather than narrative sentences that read like a
   description of one visit". On 2026-07-24 it produced exactly such a
   sentence, combining a condition, a body site and the treatment given.
   The deterministic floor is therefore the **only** real control, which is
   why this plan hard-codes the remediation in Python and adds a regression
   test rather than tightening prompt wording again.

Separately, the site has no `robots.txt`, no sitemap and no `noindex`
anywhere, so these pages are eligible for Google's index and the Wayback
Machine — which converts "visible to family" into "retained indefinitely by
third parties".

## Decisions

**D1 (maintainer, 2026-07-25) — keep the floor at 3.** Group-size
distribution over the 123 group-days of real data: 23% have exactly one
patient, 11% exactly two, mean 3.9. A floor of 3 suppresses a third of all
group-days; a floor of 8 would suppress 88% and effectively delete the
feature. The maintainer weighed raising the floor and moving the narrative
to a monthly rollup (both proposed) and chose to keep N=3 and keep the
feature on the daily page. Recorded here so a future session does not
re-litigate it by analogy — the trade-off was made knowingly.

**D2 — remediate by deterministic blanking, not by republishing.**
`republish_daily_report` would also work (the floor blanks a sub-floor group
on re-publish), but it re-runs three AI calls per date and rewrites the
*eligible* groups' prose too, changing public content that has nothing wrong
with it — and re-rolling the dice on the very failure mode in #2 above. The
new command touches only sub-floor fields.

**D3 — scrub Wagtail revisions too, not just the live fields.** A page's
`Revision.content` carries its own copy of every field. Blanking only the
live model would leave the text in the database and let a future "publish
latest revision" in the admin restore it to the public page.

**D4 — `noindex` meta, and a `robots.txt` that does NOT disallow the report
pages.** These pull in opposite directions: a crawler must be *allowed* to
fetch a page to see its `noindex`. Disallowing `/reports/` in robots.txt
would leave already-indexed URLs stuck in the index with no way for Google
to learn they should drop out. So robots.txt covers the admin paths only,
and removal from the index is done by the meta tag.

## Scope

In scope:
- `scrub_subfloor_freetext_summaries` management command (with `--dry-run`).
- `noindex` on daily report pages only.
- A `robots.txt` view.
- A regression test that the floor is what blanks, not the prompt.

Out of scope (deliberately):
- Raising the floor, or moving the narrative to a monthly rollup — D1.
- The reports index and clinic dashboard stay indexable; neither renders
  free-text.
- Dawood's other two items (Sunday opening hours, Donate nav highlight) —
  separate, non-privacy, tracked outside this plan.

## Precedent map

| Element | Mirrors |
|---|---|
| Management command | `apps/pipeline/management/commands/republish_daily_report.py` — module docstring explaining *why the recovery path exists*, `BaseCommand`, `CommandError` on bad input, `self.style.SUCCESS` summary line |
| Floor logic | `apps.pipeline.freetext.count_visits_by_group` + `MIN_GROUP_VISITS_TO_SUMMARISE` — imported, never re-implemented, so the command and the publish path can never disagree |
| Group→field mapping | `report_publishing.FREETEXT_SUMMARY_GROUP_FIELDS` — reused rather than duplicated. Promoted from `_`-private to public in this plan: it now has a second consumer, and importing an underscore-private name across modules is the thing `factories.py`'s own comment warns against |
| `robots.txt` view | `apps.core.views.healthz` — a plain non-Wagtail view, registered above `wagtail_urls` in `config/urls.py`, unprefixed by `i18n_patterns` (infrastructure, not bilingual content) |
| `noindex` block | `{% block social_image_tags %}` in `templates/base.html` — a named head block a page template overrides |

## Feature flag

None. Consistent with every plan in this repo (see the index's flag note),
and a flag would be actively wrong here: this removes published PHI-derived
text, which is not something to roll out gradually or leave half-applied.

## Release plan

1. Merge, then deploy via the existing manual deploy hook.
2. Run `python manage.py scrub_subfloor_freetext_summaries --dry-run` in
   production and check it reports the 14 rows in the table above.
3. Run it for real.
4. Verify `https://thandkoiclinics.com/en/reports/2026-07-24/` no longer
   renders a children card, and that `/robots.txt` serves.
5. Request removal of the affected URLs in Google Search Console if any are
   found to be indexed.

**Gating check:** the dry run's count matching the audit.
**Rollback:** none needed — the command only ever blanks, and any wrongly
blanked group can be regenerated with `republish_daily_report`.
**Informed:** Dawood, who raised it.
