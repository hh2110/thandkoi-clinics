"""Rebuild ``DailyAggregate`` rows from the canonical ``DeidentifiedVisit`` table.

``DailyAggregate`` is a derived cache, not a source of truth (maintainer
decision, PR #15 — see ``.claude/plans/08-data-pipeline.md`` "Recompute
path"). When a metric definition changes, this command rebuilds every
affected date's aggregate from the row-level table — no re-upload needed.

Iterates ``(clinic_date, report_kind)`` pairs, not dates alone (camp-upload
flow, 2026-07-22): a camp upload and the clinic's own daily activity can
share a calendar date but must never be aggregated together (see
``IngestRun.report_kind``'s docstring) — rebuilding by date alone would
recompute only one of the two kinds and silently leave the other's aggregate
stale.

    uv run python manage.py recompute_daily_aggregates            # every date
    uv run python manage.py recompute_daily_aggregates --date 2026-07-20
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.ingest import recompute_daily_aggregate
from apps.pipeline.models import DeidentifiedVisit


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
        if options["clinic_date"]:
            try:
                clinic_date = datetime.date.fromisoformat(options["clinic_date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {exc}") from exc
            visits = visits.filter(visit_date=clinic_date)

        date_kind_pairs = list(
            visits.values_list("visit_date", "ingest_run__report_kind").distinct()
        )

        if not date_kind_pairs:
            self.stdout.write("No dates to recompute.")
            return

        for clinic_date, report_kind in sorted(date_kind_pairs):
            recompute_daily_aggregate(clinic_date, report_kind=report_kind)
            self.stdout.write(
                self.style.SUCCESS(f"  recomputed  {clinic_date} ({report_kind})")
            )

        self.stdout.write(
            self.style.SUCCESS(f"Recomputed {len(date_kind_pairs)} date/kind pair(s).")
        )
