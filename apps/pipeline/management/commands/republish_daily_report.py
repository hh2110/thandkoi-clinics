"""Re-publish one clinic-date's ``DailyReportPage`` from its persisted aggregate.

Plan 15 Track B3. The daily-report publish (``publish_daily_report``) runs
*after* each date's DB transaction commits, never inside it (see
``apps.pipeline.ingest.persist_parsed_export``) — a slow or failing AI call
must not hold the row/aggregate write open. The cost of that ordering is that
a publish which fails *after* the commit (the page write itself errors, or the
worker is killed between commit and publish) leaves the date's aggregate
persisted but its page never written — and re-uploading the same export is
recognised as an exact-content duplicate (content-hash dedup in
``_ingest_one_date``), so the ingest path silently skips the publish and the
date stays stranded.

This command is the recovery path: it re-runs ``publish_daily_report`` for a
date directly from the already-persisted ``DailyAggregate`` and
``DeidentifiedVisit`` rows, with no re-upload and no dedup in the way. It is
idempotent — running it for a date that already has a live page just
regenerates it from the same aggregates.

    uv run python manage.py republish_daily_report 2026-07-20
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.pipeline.models import DailyAggregate
from apps.pipeline.report_publishing import publish_daily_report


class Command(BaseCommand):
    help = (
        "Re-publish a clinic-date's DailyReportPage from its persisted "
        "aggregate (recovery for a publish that failed post-commit)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "clinic_date",
            help="The clinic-date to republish (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        try:
            clinic_date = datetime.date.fromisoformat(options["clinic_date"])
        except ValueError as exc:
            raise CommandError(f"Invalid date: {exc}") from exc

        if not DailyAggregate.objects.filter(clinic_date=clinic_date).exists():
            raise CommandError(
                f"No DailyAggregate exists for {clinic_date} — nothing to "
                "republish. Ingest that date's export first (or run "
                "recompute_daily_aggregates if the rows exist but the "
                "aggregate does not)."
            )

        page = publish_daily_report(clinic_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Republished daily report for {clinic_date} (slug: {page.slug})."
            )
        )
