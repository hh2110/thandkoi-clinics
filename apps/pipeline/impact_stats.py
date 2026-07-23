"""All-time home-page impact totals, summed straight from ``DailyAggregate``.

A different unit of aggregation from ``monthly_rollup.py`` (calendar-month
rollups) — this is a single, ever-growing all-time total, so it gets its own
small module rather than overloading that one (Plan 11 Track F2 planning doc,
"Data layer" decision).

Unlike ``compute_monthly_rollup`` (which pulls every matching row into memory
and sums in Python), this sums DB-side with a single ``Sum()`` aggregate
query — one round trip, no per-row materialisation. At this clinic's scale
(at most one ``DailyAggregate`` row per calendar day) a plain ``Sum()`` is a
trivial sequential scan; no index or caching is warranted (see the planning
doc's "No new index needed now" / "No caching needed now" sections).

2026-07-23 correction to the Track F2 planning doc (``.claude/plans/
11-f2-live-impact-stats-planning.md``): that doc was drafted against a
``DailyAggregate.report_kind`` field distinguishing "daily" vs "camp" rows,
with a camp-only total and a +187 pre-pipeline offset. PR #95, merged four
minutes before that doc, removed ``report_kind`` and the entire camp-upload
pipeline entirely — there is no camp ``DailyAggregate`` data left to query,
so the camp figure and the 187 offset are dropped (maintainer decision,
2026-07-23). This module only computes the two totals that still have a real
data source.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db.models import Max, Sum

from apps.pipeline.models import DailyAggregate


@dataclass(frozen=True)
class AlltimeImpactStats:
    """All-time totals summed across every ``DailyAggregate`` row.

    ``as_of`` is the most recent ``clinic_date`` folded into the totals —
    how current the figures are — mirroring ``ImpactStatsBlock``'s own
    "updated at" convention (Plan 11 D2), but computed rather than
    hand-typed. ``None`` until any ``DailyAggregate`` row exists.
    """

    total_visits: int
    zakat_beneficiary_patients: int
    as_of: datetime.date | None


def compute_alltime_impact_stats() -> AlltimeImpactStats:
    """Sum ``total_visits`` and ``zakat_beneficiary_patients`` across all time.

    One DB-side aggregate query — Postgres does the summing, Django never
    materialises per-row objects (unlike ``compute_monthly_rollup``'s
    ``list(...)``).
    """
    totals = DailyAggregate.objects.aggregate(
        total_visits=Sum("total_visits"),
        zakat_beneficiary_patients=Sum("zakat_beneficiary_patients"),
        as_of=Max("clinic_date"),
    )
    return AlltimeImpactStats(
        total_visits=totals["total_visits"] or 0,
        zakat_beneficiary_patients=totals["zakat_beneficiary_patients"] or 0,
        as_of=totals["as_of"],
    )
