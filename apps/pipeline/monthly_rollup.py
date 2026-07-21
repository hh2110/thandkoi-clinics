"""Aggregate ``DailyAggregate`` rows into a calendar-month rollup (Plan 09).

This is a pure reader of Plan 08's derived-cache table — never a re-parse of
any export and never a direct read of ``DeidentifiedVisit`` (that table is out
of reach for this plan's tools by design; see
``.claude/plans/09-ai-monthly-newsletter.md`` "Data interface consumed").
``MonthlyRollup`` is the shape ``apps.pipeline.newsletter_tools.get_month_stats``
hands to the model — every field here is a count summed or merged from
``DailyAggregate``, so it is safe to serialise into an AI payload the same way
``DailyAggregate.as_dict()`` already is (invariant #2).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from apps.pipeline.models import DailyAggregate


def first_of_month(month: datetime.date) -> datetime.date:
    """Normalise any date to the first day of its calendar month."""
    return month.replace(day=1)


def previous_calendar_month(month: datetime.date) -> datetime.date:
    """The first day of the calendar month before ``month``."""
    first = first_of_month(month)
    last_day_of_prior_month = first - datetime.timedelta(days=1)
    return first_of_month(last_day_of_prior_month)


def _merge_category_counts(rows) -> dict[str, dict[str, int]]:
    """Sum each ``DailyAggregate.category_counts`` breakdown across the month.

    Every row's ``category_counts`` has the same top-level shape
    (``by_department``/``by_diagnosis_category``/``by_age_band``); this merges
    matching keys across days rather than letting a later day's dict clobber
    an earlier one's.
    """
    merged: dict[str, dict[str, int]] = {}
    for row in rows:
        for breakdown_name, counts in row.category_counts.items():
            bucket = merged.setdefault(breakdown_name, {})
            for key, count in counts.items():
                bucket[key] = bucket.get(key, 0) + count
    return {name: dict(sorted(counts.items())) for name, counts in merged.items()}


@dataclass(frozen=True)
class MonthlyRollup:
    """One calendar month's totals, summed from ``DailyAggregate`` rows.

    Contains only counts — never a patient row — so it is safe to serialise
    into an AI tool-result payload the same way ``DailyAggregate.as_dict()``
    already is.
    """

    month: datetime.date
    day_count: int
    total_visits: int = 0
    male_patients: int = 0
    female_patients: int = 0
    other_or_unknown_sex_patients: int = 0
    new_patients: int = 0
    follow_up_patients: int = 0
    unknown_patient_type_patients: int = 0
    zakat_beneficiary_patients: int = 0
    paying_patients: int = 0
    unknown_payment_type_patients: int = 0
    category_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Plain, JSON-serialisable representation — the AI tool-result shape."""
        return {
            "month": f"{self.month:%Y-%m}",
            "day_count": self.day_count,
            "total_visits": self.total_visits,
            "male_patients": self.male_patients,
            "female_patients": self.female_patients,
            "other_or_unknown_sex_patients": self.other_or_unknown_sex_patients,
            "new_patients": self.new_patients,
            "follow_up_patients": self.follow_up_patients,
            "unknown_patient_type_patients": self.unknown_patient_type_patients,
            "zakat_beneficiary_patients": self.zakat_beneficiary_patients,
            "paying_patients": self.paying_patients,
            "unknown_payment_type_patients": self.unknown_payment_type_patients,
            "category_counts": dict(self.category_counts),
        }


_SUMMED_FIELDS = (
    "total_visits",
    "male_patients",
    "female_patients",
    "other_or_unknown_sex_patients",
    "new_patients",
    "follow_up_patients",
    "unknown_patient_type_patients",
    "zakat_beneficiary_patients",
    "paying_patients",
    "unknown_payment_type_patients",
)


def compute_monthly_rollup(month: datetime.date) -> MonthlyRollup:
    """Sum every ``DailyAggregate`` row for ``month``'s calendar month.

    Queries only ``DailyAggregate`` (Plan 08's derived cache) — never
    ``DeidentifiedVisit`` — so this can never surface a row-level value.
    """
    target = first_of_month(month)
    rows = list(
        DailyAggregate.objects.filter(
            clinic_date__year=target.year, clinic_date__month=target.month
        )
    )
    totals = {name: sum(getattr(row, name) for row in rows) for name in _SUMMED_FIELDS}
    return MonthlyRollup(
        month=target,
        day_count=len(rows),
        category_counts=_merge_category_counts(rows),
        **totals,
    )


def compute_month_over_month_trend(month: datetime.date) -> dict[str, object]:
    """Compare ``month``'s rollup against the calendar month before it.

    Both sides come from :func:`compute_monthly_rollup` — a Python-computed
    ``DailyAggregate`` query, never a value the model supplies.
    """
    this_month = compute_monthly_rollup(month)
    prior_month = compute_monthly_rollup(previous_calendar_month(month))
    return {
        "month": this_month.as_dict(),
        "previous_month": prior_month.as_dict(),
        "total_visits_delta": this_month.total_visits - prior_month.total_visits,
        "new_patients_delta": this_month.new_patients - prior_month.new_patients,
        "zakat_beneficiary_patients_delta": (
            this_month.zakat_beneficiary_patients
            - prior_month.zakat_beneficiary_patients
        ),
    }
