"""Plan 11 Track F2 — all-time home-page impact totals.

Mirrors ``test_newsletter.py``'s aggregation-test shape (plain, deterministic
assertions about a DB-side sum over ``DailyAggregate``). See
``apps/pipeline/impact_stats.py``'s module docstring for why this only
computes two totals, not the three ("Camp patients") the Track F2 planning
doc originally proposed.
"""

from __future__ import annotations

import datetime

from apps.pipeline.factories import DailyAggregateFactory
from apps.pipeline.impact_stats import compute_alltime_impact_stats


def test_compute_alltime_impact_stats_sums_every_dailyaggregate_row(db):
    DailyAggregateFactory(
        clinic_date=datetime.date(2026, 7, 1),
        total_visits=10,
        zakat_beneficiary_patients=6,
    )
    DailyAggregateFactory(
        clinic_date=datetime.date(2026, 7, 2),
        total_visits=5,
        zakat_beneficiary_patients=3,
    )
    DailyAggregateFactory(
        clinic_date=datetime.date(2026, 8, 1),
        total_visits=7,
        zakat_beneficiary_patients=1,
    )

    stats = compute_alltime_impact_stats()

    assert stats.total_visits == 22
    assert stats.zakat_beneficiary_patients == 10


def test_compute_alltime_impact_stats_with_no_rows_returns_zero(db):
    stats = compute_alltime_impact_stats()

    assert stats.total_visits == 0
    assert stats.zakat_beneficiary_patients == 0
