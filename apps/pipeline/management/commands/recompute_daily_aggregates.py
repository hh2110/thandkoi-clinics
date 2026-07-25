"""Rebuild ``DailyAggregate`` rows from the canonical ``DeidentifiedVisit`` table.

``DailyAggregate`` is a derived cache, not a source of truth (maintainer
decision, PR #15 — see ``.claude/plans/08-data-pipeline.md`` "Recompute
path"). When a metric definition changes, this command rebuilds every
affected date's aggregate from the row-level table — no re-upload needed.

    uv run python manage.py recompute_daily_aggregates            # every date
    uv run python manage.py recompute_daily_aggregates --date 2026-07-20
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.ingest import recompute_daily_aggregate
from apps.pipeline.models import DailyAggregate, DailyReportPage, DeidentifiedVisit
from apps.pipeline.report_publishing import publish_daily_report


class Command(BaseCommand):
    help = "Rebuild DailyAggregate from DeidentifiedVisit (the derived-cache contract)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="clinic_date",
            help="Recompute only this date (YYYY-MM-DD). Default: every date "
            "that has any DeidentifiedVisit rows.",
        )

    def handle(self, *args, **options):
        visits = DeidentifiedVisit.objects.order_by()
        aggregates = DailyAggregate.objects.order_by()
        if options["clinic_date"]:
            try:
                clinic_date = datetime.date.fromisoformat(options["clinic_date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {exc}") from exc
            visits = visits.filter(visit_date=clinic_date)
            aggregates = aggregates.filter(clinic_date=clinic_date)

        # Union with existing DailyAggregate rows, not just remaining visit
        # rows: if every DeidentifiedVisit for a date was deleted (e.g. a
        # data correction), that date drops out of `visits` entirely, but its
        # DailyAggregate row is now stale (still showing the pre-deletion
        # totals) and an explicit `--date` recompute must still reset it to
        # zero, not silently no-op.
        dates = set(visits.values_list("visit_date", flat=True).distinct()) | set(
            aggregates.values_list("clinic_date", flat=True).distinct()
        )

        if not dates:
            self.stdout.write("No dates to recompute.")
            return

        republished = 0
        for clinic_date in sorted(dates):
            recompute_daily_aggregate(clinic_date)
            self.stdout.write(self.style.SUCCESS(f"  recomputed  {clinic_date}"))

            # Plan 15 Track B4: the published page reads its *numbers* live
            # from the aggregate, so those refresh for free — but the
            # auto-published AI prose (summary sentence + per-group free-text
            # summaries) was drafted against the pre-recompute figures and is
            # now frozen text that may quote numbers this recompute has since
            # changed. Re-publish so the prose is redrafted against the new
            # aggregate. Only for dates that already have a page — recompute
            # must not conjure a report page for a date that never published
            # one (that's `republish_daily_report`'s job, Track B3).
            if DailyReportPage.objects.filter(report_date=clinic_date).exists():
                publish_daily_report(clinic_date)
                republished += 1
                self.stdout.write(self.style.SUCCESS(f"  republished {clinic_date}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed {len(dates)} date(s); republished {republished}."
            )
        )
