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
        if options["clinic_date"]:
            try:
                dates = [datetime.date.fromisoformat(options["clinic_date"])]
            except ValueError as exc:
                raise CommandError(f"Invalid --date: {exc}") from exc
        else:
            dates = list(
                DeidentifiedVisit.objects.order_by()
                .values_list("visit_date", flat=True)
                .distinct()
            )

        if not dates:
            self.stdout.write("No dates to recompute.")
            return

        for clinic_date in sorted(dates):
            recompute_daily_aggregate(clinic_date)
            self.stdout.write(self.style.SUCCESS(f"  recomputed  {clinic_date}"))

        self.stdout.write(self.style.SUCCESS(f"Recomputed {len(dates)} date(s)."))
