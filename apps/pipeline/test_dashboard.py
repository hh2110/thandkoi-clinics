"""Plan 16 task 16.2 — the clinic dashboard's range aggregation module.

Mirrors ``test_impact_stats.py``'s shape: plain, deterministic assertions
about DB-side sums over ``DailyAggregate``, with no page, template or view
involved. Every figure asserted here is one this module computed from real
rows — nothing is copied from the design handoff's prototypes, whose numbers
are all invented sample data (Plan 16 D11).

Dates are fixed rather than relative to "today" wherever the assertion is
about calendar structure. ``2026-01-05`` is a Monday, which is what makes the
90/91 and 400/401 slot-boundary ranges below land exactly on their thresholds.
"""

from __future__ import annotations

import datetime

import pytest

from apps.pipeline.dashboard import (
    DEFAULT_RANGE_DAYS,
    GRAIN_DAY,
    GRAIN_MONTH,
    GRAIN_WEEK,
    MAX_RANGE_DAYS,
    DateRange,
    FootfallBucket,
    bucket_footfall,
    compute_dashboard_stats,
    default_range,
    has_revenue,
    parse_range,
    reporting_gap_dates,
    select_grain,
)
from apps.pipeline.factories import DailyAggregateFactory
from apps.pipeline.footfall_chart import build_footfall_chart

TODAY = datetime.date(2026, 7, 25)
MONDAY = datetime.date(2026, 1, 5)


def day(offset: int) -> datetime.date:
    """``offset`` days after :data:`MONDAY`."""
    return MONDAY + datetime.timedelta(days=offset)


# --- Range parsing and clamping (Plan 16 D10) ------------------------------


def test_default_range_is_the_last_30_days_ending_today():
    result = default_range(TODAY)

    assert result.start == datetime.date(2026, 6, 26)
    assert result.end == TODAY
    assert result.days == DEFAULT_RANGE_DAYS


def test_parse_range_honours_both_params():
    result = parse_range("2026-03-01", "2026-03-31", today=TODAY)

    assert result == DateRange(datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
    assert result.days == 31


def test_parse_range_collapses_end_before_start_to_a_one_day_range():
    result = parse_range("2026-03-31", "2026-03-01", today=TODAY)

    assert result == DateRange(datetime.date(2026, 3, 31), datetime.date(2026, 3, 31))
    assert result.days == 1


def test_parse_range_keeps_a_genuine_one_day_range():
    result = parse_range("2026-03-01", "2026-03-01", today=TODAY)

    assert result.start == result.end == datetime.date(2026, 3, 1)
    assert result.days == 1


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, None),  # no params at all — the plain /dashboard/ URL
        ("2026-03-01", None),  # half a range, only reachable by hand-editing
        (None, "2026-03-31"),
        ("", ""),  # a form submitted with both date inputs left blank
        ("not-a-date", "2026-03-31"),
        ("2026-03-01", "not-a-date"),
        ("2026-13-45", "2026-03-31"),  # parseable shape, impossible date
        ("2026/03/01", "2026/03/31"),  # wrong separator
    ],
)
def test_parse_range_falls_back_to_the_default_silently(start, end):
    """Garbage and missing params both give the default, with no error state.

    Silently is the decision (Plan 16 D10, maintainer 2026-07-25) — the
    module has no way to signal "we didn't understand that range" because
    the page deliberately shows no such message.
    """
    assert parse_range(start, end, today=TODAY) == default_range(TODAY)


def test_parse_range_accepts_a_range_exactly_at_the_five_year_cap():
    end = datetime.date(2026, 3, 1) + datetime.timedelta(days=MAX_RANGE_DAYS - 1)

    result = parse_range("2026-03-01", end.isoformat(), today=TODAY)

    assert result.days == MAX_RANGE_DAYS
    assert result.start == datetime.date(2026, 3, 1)


def test_parse_range_falls_back_when_the_range_exceeds_the_five_year_cap():
    end = datetime.date(2026, 3, 1) + datetime.timedelta(days=MAX_RANGE_DAYS)

    result = parse_range("2026-03-01", end.isoformat(), today=TODAY)

    assert result == default_range(TODAY)


def test_parse_range_cap_is_checked_after_the_end_before_start_collapse():
    """A wildly backwards range collapses to one day rather than tripping the cap."""
    result = parse_range("2026-03-01", "1990-01-01", today=TODAY)

    assert result == DateRange(datetime.date(2026, 3, 1), datetime.date(2026, 3, 1))


# --- Grain selection (Plan 16 D3) ------------------------------------------


@pytest.mark.parametrize(
    ("slot_count", "expected"),
    [
        (0, GRAIN_DAY),
        (1, GRAIN_DAY),
        (90, GRAIN_DAY),
        (91, GRAIN_WEEK),
        (400, GRAIN_WEEK),
        (401, GRAIN_MONTH),
    ],
)
def test_select_grain_boundaries(slot_count, expected):
    assert select_grain(slot_count) == expected


def test_slot_count_and_grain_at_the_90_91_boundary(db):
    """15 whole weeks from a Monday is exactly 90 Mon–Sat slots; one more flips it.

    Counted with an empty database on purpose: a slot is reserved for every
    Mon–Sat date whether or not it reported, which is the whole distinction
    D3 draws between "slots" and "reporting days".
    """
    fifteen_weeks = compute_dashboard_stats(DateRange(MONDAY, day(104)))
    assert fifteen_weeks.slot_count == 90
    assert fifteen_weeks.grain == GRAIN_DAY

    one_more_day = compute_dashboard_stats(DateRange(MONDAY, day(105)))
    assert one_more_day.slot_count == 91
    assert one_more_day.grain == GRAIN_WEEK


def test_slot_count_and_grain_at_the_400_401_boundary(db):
    """66 whole weeks plus Mon–Thu is 400 slots; the Friday after flips to month."""
    to_thursday = compute_dashboard_stats(DateRange(MONDAY, day(465)))
    assert to_thursday.slot_count == 400
    assert to_thursday.grain == GRAIN_WEEK

    to_friday = compute_dashboard_stats(DateRange(MONDAY, day(466)))
    assert to_friday.slot_count == 401
    assert to_friday.grain == GRAIN_MONTH


def test_a_sunday_that_reported_adds_a_slot(db):
    """Sundays get no slot unless they have a row — Plan 13's rule, reused here."""
    sunday = day(6)
    assert sunday.weekday() == 6

    without = compute_dashboard_stats(DateRange(MONDAY, sunday))
    assert without.slot_count == 6

    DailyAggregateFactory(clinic_date=sunday)
    with_sunday = compute_dashboard_stats(DateRange(MONDAY, sunday))
    assert with_sunday.slot_count == 7


# --- Totals (Plan 16 acceptance criterion 4) -------------------------------


def test_totals_sum_only_the_rows_inside_the_range(db):
    DailyAggregateFactory(clinic_date=day(0), total_visits=10)  # before
    DailyAggregateFactory(
        clinic_date=day(1),
        total_visits=10,
        zakat_beneficiary_patients=6,
        paying_patients=4,
        female_patients=7,
        male_patients=3,
    )
    DailyAggregateFactory(
        clinic_date=day(2),
        total_visits=5,
        zakat_beneficiary_patients=1,
        paying_patients=4,
        female_patients=2,
        male_patients=3,
    )
    DailyAggregateFactory(clinic_date=day(3), total_visits=99)  # after

    stats = compute_dashboard_stats(DateRange(day(1), day(2)))

    assert stats.total_visits == 15
    assert stats.zakat_beneficiary_patients == 7
    assert stats.paying_patients == 8
    assert stats.female_patients == 9
    assert stats.male_patients == 6
    assert stats.reporting_days == 2
    assert stats.total_days == 2


def test_days_with_no_row_are_excluded_from_totals_not_counted_as_zero(db):
    """A missing day must not drag the per-reporting-day average down."""
    DailyAggregateFactory(clinic_date=day(1), total_visits=10)
    DailyAggregateFactory(clinic_date=day(3), total_visits=20)

    stats = compute_dashboard_stats(DateRange(day(1), day(5)))

    assert stats.total_days == 5
    assert stats.reporting_days == 2
    assert stats.total_visits == 30
    assert stats.visits_per_reporting_day == 15.0


def test_an_empty_range_returns_zeros_and_no_average(db):
    """No rows at all: zeros everywhere, no NaN, no ZeroDivisionError."""
    stats = compute_dashboard_stats(DateRange(day(1), day(5)))

    assert stats.total_visits == 0
    assert stats.zakat_beneficiary_patients == 0
    assert stats.paying_patients == 0
    assert stats.reporting_days == 0
    assert stats.visits_per_reporting_day is None
    assert [row["pct"] for row in stats.funding_rows] == [0, 0]
    assert [row["pct"] for row in stats.gender_rows] == [0, 0]
    assert [band["pct"] for band in stats.age_bands] == [0, 0, 0, 0]
    assert [band["bar_pct"] for band in stats.age_bands] == [0, 0, 0, 0]


def test_a_one_day_range_totals_that_single_day(db):
    DailyAggregateFactory(
        clinic_date=day(1),
        total_visits=8,
        zakat_beneficiary_patients=5,
        paying_patients=3,
    )

    stats = compute_dashboard_stats(DateRange(day(1), day(1)))

    assert stats.total_days == 1
    assert stats.reporting_days == 1
    assert stats.total_visits == 8
    assert stats.visits_per_reporting_day == 8.0
    assert stats.grain == GRAIN_DAY


# --- Funding / gender / age-band rows (Plan 16 D5) -------------------------


def test_funding_percentages_are_of_total_visits_and_may_fall_short_of_100(db):
    """Unknown-payment visits are shown by omission, not as a third category."""
    DailyAggregateFactory(
        clinic_date=day(1),
        total_visits=10,
        zakat_beneficiary_patients=6,
        paying_patients=2,
        unknown_payment_type_patients=2,
    )

    stats = compute_dashboard_stats(DateRange(day(1), day(1)))

    assert [row["count"] for row in stats.funding_rows] == [6, 2]
    assert [row["pct"] for row in stats.funding_rows] == [60, 20]
    assert sum(row["pct"] for row in stats.funding_rows) == 80
    assert [row["label"] for row in stats.funding_rows] == ["Zakat", "Regular"]


def test_gender_rows_mirror_the_daily_report_page_shape(db):
    """Female then Male, bar scaled to the larger — the daily page's own rule."""
    DailyAggregateFactory(
        clinic_date=day(1),
        total_visits=10,
        female_patients=6,
        male_patients=3,
        other_or_unknown_sex_patients=1,
    )

    stats = compute_dashboard_stats(DateRange(day(1), day(1)))

    assert stats.gender_rows == [
        {"label": "Female", "count": 6, "pct": 100},
        {"label": "Male", "count": 3, "pct": 50},
    ]


def test_age_bands_sum_category_counts_across_the_range(db):
    DailyAggregateFactory(
        clinic_date=day(1),
        total_visits=10,
        category_counts={"by_age_band": {"0-5": 2, "19-55": 6, "unknown": 2}},
    )
    DailyAggregateFactory(
        clinic_date=day(2),
        total_visits=10,
        category_counts={"by_age_band": {"6-18": 4, "56+": 6}},
    )

    stats = compute_dashboard_stats(DateRange(day(1), day(2)))

    assert [band["label"] for band in stats.age_bands] == [
        "0–5",
        "6–18",
        "19–55",
        "56+",
    ]
    assert [band["count"] for band in stats.age_bands] == [2, 4, 6, 6]
    # pct is of total_visits (20) — the two unknown-age visits are the
    # shortfall from 100, left implicit per D5.
    assert [band["pct"] for band in stats.age_bands] == [10, 20, 30, 30]
    assert sum(band["pct"] for band in stats.age_bands) == 90
    # bar_pct scales to the largest band (6), which the design fills to 100%.
    assert [band["bar_pct"] for band in stats.age_bands] == [33, 67, 100, 100]


def test_age_bands_tolerate_a_missing_or_empty_category_counts(db):
    DailyAggregateFactory(clinic_date=day(1), total_visits=4, category_counts={})

    stats = compute_dashboard_stats(DateRange(day(1), day(1)))

    assert [band["count"] for band in stats.age_bands] == [0, 0, 0, 0]


# --- Reporting gaps --------------------------------------------------------


def test_gap_detection_skips_sundays(db):
    """Friday–Monday with only Friday and Monday reported: Saturday is the gap.

    The Sunday between them is not a gap — the clinic is closed, so its
    absence is expected rather than missing.
    """
    friday, saturday, sunday, monday = day(4), day(5), day(6), day(7)
    assert [d.weekday() for d in (friday, saturday, sunday, monday)] == [4, 5, 6, 0]
    DailyAggregateFactory(clinic_date=friday)
    DailyAggregateFactory(clinic_date=monday)

    stats = compute_dashboard_stats(DateRange(friday, monday))

    assert stats.gap_dates == [saturday]


def test_a_sunday_with_no_row_is_never_a_gap_even_across_a_full_week(db):
    for offset in range(7):
        if day(offset).weekday() != 6:
            DailyAggregateFactory(clinic_date=day(offset))

    stats = compute_dashboard_stats(DateRange(MONDAY, day(6)))

    assert stats.gap_dates == []
    assert stats.reporting_days == 6


def test_every_unreported_mon_sat_date_is_a_gap(db):
    stats = compute_dashboard_stats(DateRange(MONDAY, day(6)))

    assert stats.gap_dates == [day(o) for o in range(6)]


def test_reporting_gap_dates_is_pure():
    """The gap helper takes the reported dates; it does not fetch them."""
    reported = {day(0), day(2)}

    assert reporting_gap_dates(reported, DateRange(MONDAY, day(3))) == [day(1), day(3)]


# --- Chart bucketing (Plan 16 D3/D16) --------------------------------------


class Row:
    """A duck-typed stand-in for ``DailyAggregate``, same as the chart takes."""

    def __init__(self, clinic_date, total_visits, zakat, regular):
        self.clinic_date = clinic_date
        self.total_visits = total_visits
        self.zakat_beneficiary_patients = zakat
        self.paying_patients = regular


def test_day_grain_bucketing_is_a_pass_through():
    """Day grain must reproduce exactly what the existing chart already draws."""
    rows = [Row(day(0), 10, 6, 4), Row(day(2), 5, 1, 4)]
    date_range = DateRange(MONDAY, day(6))

    result = bucket_footfall(rows, date_range, GRAIN_DAY)

    # Six slots (Sunday excluded), two of them filled — so day(1) and the
    # rest render as the visible gaps the chart already shows.
    assert result.slots == [day(o) for o in range(6)]
    assert result.buckets == [
        FootfallBucket(day(0), 10, 6, 4),
        FootfallBucket(day(2), 5, 1, 4),
    ]
    # …and the buckets feed straight into the existing chart with no
    # adapter, because they carry exactly the attributes it reads.
    chart = build_footfall_chart(result.buckets, date_range.start, date_range.end)
    assert [bar["date"] for bar in chart["bars"]] == [day(0), day(2)]


def test_week_grain_folds_rows_into_mondays():
    rows = [
        Row(day(0), 10, 6, 4),  # Monday, week 1
        Row(day(5), 4, 1, 3),  # Saturday, week 1
        Row(day(6), 2, 2, 0),  # Sunday, week 1 — folds in, not dropped
        Row(day(8), 7, 3, 4),  # Tuesday, week 2
    ]

    result = bucket_footfall(rows, DateRange(MONDAY, day(13)), GRAIN_WEEK)

    assert result.slots == [MONDAY, day(7)]
    assert result.buckets == [
        FootfallBucket(MONDAY, 16, 9, 7),
        FootfallBucket(day(7), 7, 3, 4),
    ]


def test_a_week_with_no_rows_keeps_its_slot_and_gets_no_bucket():
    """A gap must stay a gap at week grain, not become a zero-height bar."""
    rows = [Row(day(0), 10, 6, 4), Row(day(14), 5, 2, 3)]

    result = bucket_footfall(rows, DateRange(MONDAY, day(20)), GRAIN_WEEK)

    assert result.slots == [MONDAY, day(7), day(14)]
    assert [bucket.clinic_date for bucket in result.buckets] == [MONDAY, day(14)]


def test_week_slots_start_on_the_monday_before_a_mid_week_range_start():
    wednesday = day(2)

    result = bucket_footfall([], DateRange(wednesday, day(9)), GRAIN_WEEK)

    assert result.slots == [MONDAY, day(7)]


def test_month_grain_folds_rows_into_calendar_months():
    rows = [
        Row(datetime.date(2026, 1, 6), 10, 6, 4),
        Row(datetime.date(2026, 1, 20), 5, 2, 3),
        Row(datetime.date(2026, 3, 2), 8, 4, 4),
    ]

    result = bucket_footfall(
        rows,
        DateRange(datetime.date(2026, 1, 5), datetime.date(2026, 3, 31)),
        GRAIN_MONTH,
    )

    assert result.slots == [
        datetime.date(2026, 1, 1),
        datetime.date(2026, 2, 1),
        datetime.date(2026, 3, 1),
    ]
    # February kept its slot and got no bucket — a visible gap, same rule.
    assert result.buckets == [
        FootfallBucket(datetime.date(2026, 1, 1), 15, 8, 7),
        FootfallBucket(datetime.date(2026, 3, 1), 8, 4, 4),
    ]


def test_month_slots_cross_a_year_boundary():
    result = bucket_footfall(
        [],
        DateRange(datetime.date(2026, 11, 15), datetime.date(2027, 2, 3)),
        GRAIN_MONTH,
    )

    assert result.slots == [
        datetime.date(2026, 11, 1),
        datetime.date(2026, 12, 1),
        datetime.date(2027, 1, 1),
        datetime.date(2027, 2, 1),
    ]


def test_bucketing_ignores_rows_outside_the_range():
    rows = [Row(day(-7), 99, 99, 0), Row(day(0), 10, 6, 4), Row(day(70), 99, 99, 0)]

    result = bucket_footfall(rows, DateRange(MONDAY, day(13)), GRAIN_WEEK)

    assert result.buckets == [FootfallBucket(MONDAY, 10, 6, 4)]


def test_bucketing_rejects_an_unknown_grain():
    with pytest.raises(ValueError, match="Unknown footfall grain"):
        bucket_footfall([], DateRange(MONDAY, day(6)), "fortnight")


# --- Revenue gate (Plan 16 D6) ---------------------------------------------


def test_has_revenue_is_false_until_the_column_exists(db):
    """Gated on data, not a flag — and there is no revenue column yet (D6/D13)."""
    rows = [DailyAggregateFactory(clinic_date=day(1), total_visits=10)]

    assert has_revenue(rows) is False
    assert has_revenue([]) is False
