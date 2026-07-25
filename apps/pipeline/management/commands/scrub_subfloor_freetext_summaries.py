"""Blank every published free-text summary that sits below the N=3 floor.

Plan 18. ``MIN_GROUP_VISITS_TO_SUMMARISE`` (Plan 15 Track C3) is enforced in
``report_publishing.publish_daily_report`` *at publish time only*, and nothing
backfills it. That floor deployed on 2026-07-25 at 12:49 UTC, by which point
every live ``DailyReportPage`` had already been published — so the floor had
never actually run against anything public, and 14 summaries covering groups
of one or two patients were live across 11 pages.

This command is the backfill. It walks every ``DailyReportPage``, recomputes
each group's visit count from the persisted ``DeidentifiedVisit`` rows using
the same helper the publish path uses, and blanks any group's summary field
that is non-empty while its group is below the floor. It is idempotent: a
second run finds nothing to do.

Deliberately *not* implemented by re-running ``republish_daily_report`` for
the affected dates (Plan 18 D2). That would work — the floor blanks a
sub-floor group on re-publish — but it also re-runs three AI calls per date
and rewrites the *eligible* groups' prose, churning public content that is
not at fault and re-rolling the dice on the model's own failure mode (on
2026-07-24 it wrote a single-visit narrative in direct contradiction of the
prompt). This touches sub-floor fields and nothing else.

    uv run python manage.py scrub_subfloor_freetext_summaries --dry-run
    uv run python manage.py scrub_subfloor_freetext_summaries
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.pipeline import freetext
from apps.pipeline.models import DailyReportPage, DeidentifiedVisit
from apps.pipeline.report_publishing import FREETEXT_SUMMARY_GROUP_FIELDS


def find_subfloor_summaries(page: DailyReportPage) -> list[tuple[str, str]]:
    """``(group, field_name)`` for each of ``page``'s sub-floor summaries.

    A group qualifies when it is below :data:`freetext.MIN_GROUP_VISITS_TO_SUMMARISE`
    *and* its field currently holds text — a group that is below the floor but
    already blank needs no work, which is what makes the command idempotent.

    The visit counts come from :func:`freetext.count_visits_by_group`, the same
    helper ``publish_daily_report`` uses, rather than a re-implementation here:
    the two must never be able to disagree about what "below the floor" means.

    This fails closed on purpose. A page whose date has no surviving
    ``DeidentifiedVisit`` rows at all counts as zero in every group, so any
    summary it still carries is blanked — we cannot demonstrate that such a
    summary clears the floor, and an unverifiable summary is exactly the thing
    this command exists to remove.
    """
    visits = DeidentifiedVisit.objects.filter(visit_date=page.report_date)
    counts = freetext.count_visits_by_group(visits)
    return [
        (group, field_name)
        for group, field_name in FREETEXT_SUMMARY_GROUP_FIELDS.items()
        if counts[group] < freetext.MIN_GROUP_VISITS_TO_SUMMARISE
        and getattr(page, field_name).strip()
    ]


def _scrub_revisions(page: DailyReportPage, field_names: list[str]) -> int:
    """Blank ``field_names`` in every stored revision of ``page``.

    Plan 18 D3. ``Revision.content`` carries its own serialised copy of every
    field, so blanking the live model alone would leave the text sitting in the
    database and let a later "publish this revision" in the Wagtail admin put it
    straight back on the public page. Returns the number of revisions changed.
    """
    changed = 0
    for revision in page.revisions.all():
        content = revision.content
        touched = False
        for field_name in field_names:
            if content.get(field_name):
                content[field_name] = ""
                touched = True
        if touched:
            revision.content = content
            revision.save(update_fields=["content"])
            changed += 1
    return changed


class Command(BaseCommand):
    help = (
        "Blank every published free-text summary whose demographic group is "
        "below the k-anonymity floor (Plan 18 backfill of Plan 15 Track C3)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be blanked without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        pages_changed = 0
        summaries_blanked = 0
        revisions_changed = 0

        for page in DailyReportPage.objects.order_by("report_date"):
            subfloor = find_subfloor_summaries(page)
            if not subfloor:
                continue

            pages_changed += 1
            summaries_blanked += len(subfloor)
            for group, _field_name in subfloor:
                self.stdout.write(f"{page.report_date}: {group}")

            if dry_run:
                continue

            field_names = [field_name for _group, field_name in subfloor]
            with transaction.atomic():
                for field_name in field_names:
                    setattr(page, field_name, "")
                page.save(update_fields=field_names)
                revisions_changed += _scrub_revisions(page, field_names)

        verb = "would blank" if dry_run else "blanked"
        message = f"{verb} {summaries_blanked} summaries across {pages_changed} pages"
        if not dry_run:
            message += f" ({revisions_changed} revisions scrubbed)"
        self.stdout.write(self.style.SUCCESS(message + "."))
