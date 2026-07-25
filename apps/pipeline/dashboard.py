"""Range aggregation for the clinic dashboard (Plan 16, task 16.2).

Everything ``ClinicDashboardPage`` (task 16.3) needs to render a
reader-chosen date range, computed and tested on its own with no template,
no view and no page type in sight. Mirrors ``impact_stats.py``'s shape — its
own small module, a DB-side ``Sum()`` aggregate, frozen dataclass returns —
rather than growing another method on a page model.

**Every figure here comes from ``DailyAggregate``** (Plan 16 D11). The design
handoff's prototypes are full of invented sample numbers; none of them is
hardcoded anywhere in this module. **No AI call** (D12): the dashboard reads
de-identified counts and nothing else, so it adds no surface to CLAUDE.md's
privacy invariants.

Two queries, deliberately. The named integer columns sum DB-side in one
``.aggregate(Sum(...))`` (impact_stats' precedent — Postgres does the adding
and never ships those columns to Python), and a second pass materialises only
``clinic_date`` and ``category_counts`` via ``values_list``, because the age
bands live in JSON that SQL can't sum for us and the gap/slot logic needs the
dates. That is strictly less data than fetching whole rows once would be. No
caching and no new index (Plan 16's "Out of scope" — one row per calendar
day makes the scan trivial, the same reasoning ``impact_stats.py`` records).

Days with no ``DailyAggregate`` row are **excluded** from every total, never
counted as zero — ``Sum()`` only sees rows that exist, and
``reporting_days`` counts rows rather than calendar days. Their absence is
reported separately, as gap dates and as empty chart slots.

**Bucketing lives here, chart layout does not** (decision D16, 2026-07-25 —
see the plan file). ``bucket_footfall`` folds daily rows into week/month
buckets and returns the ordered slot list beside them; teaching
``footfall_chart.build_footfall_chart`` to lay out a caller-supplied slot
list is task 16.3's job, since 16.3 is the first caller that renders a
chart. The buckets are duck-typed to exactly what that module reads off a
row, so they need no adapter when 16.3 gets there.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.pipeline.footfall_chart import SUNDAY_WEEKDAY, slot_dates
from apps.pipeline.models import DailyAggregate, DeidentifiedVisit

#: Default window when the reader supplies no usable range: the last 30 days
#: **ending today**, inclusive — so 25 Jul 2026 defaults to 26 Jun – 25 Jul.
#: Distinct from ``ReportIndexPage.FUNDING_MIX_WINDOW_DAYS``, which is a
#: rolling *offset* (30 days back) rather than an inclusive day count.
DEFAULT_RANGE_DAYS = 30

#: Server-side safety cap (Plan 16 D10): a longer range falls back to the
#: default. Deliberately a plain day count rather than a calendar-exact five
#: years — leap days are not added back, because this bounds how much the
#: page will scan, it is not a figure any reader sees.
MAX_RANGE_DAYS = 5 * 365

GRAIN_DAY = "day"
GRAIN_WEEK = "week"
GRAIN_MONTH = "month"

#: Slot-count thresholds for the chart grain (Plan 16 D3). Keyed off **chart
#: slots** — Mon–Sat days in range plus any Sunday that reported — not off
#: reporting days as the handoff's table words it, because the thing that
#: overflows the card is the number of bars, and a Mon–Sat day with no report
#: still reserves one (Plan 13's gap rule).
DAY_GRAIN_MAX_SLOTS = 90
WEEK_GRAIN_MAX_SLOTS = 400

#: The four display bands, in order. Same four (and the same en-dash labels)
#: ``DailyReportPage.get_context`` renders; ``AGE_BAND_UNKNOWN`` is shown by
#: omission, per Plan 16 D5.
DISPLAY_AGE_BANDS = [
    (DeidentifiedVisit.AGE_BAND_0_5, "0–5"),
    (DeidentifiedVisit.AGE_BAND_6_18, "6–18"),
    (DeidentifiedVisit.AGE_BAND_19_55, "19–55"),
    (DeidentifiedVisit.AGE_BAND_56_PLUS, "56+"),
]


# --- Range parsing and clamping (Plan 16 D10) ------------------------------


@dataclass(frozen=True)
class DateRange:
    """An inclusive ``start``–``end`` calendar range."""

    start: datetime.date
    end: datetime.date

    @property
    def days(self) -> int:
        """Calendar days in the range, counting both ends."""
        return (self.end - self.start).days + 1


def default_range(today: datetime.date | None = None) -> DateRange:
    """The last :data:`DEFAULT_RANGE_DAYS` days, ending ``today`` inclusive."""
    today = today or timezone.localdate()
    return DateRange(today - datetime.timedelta(days=DEFAULT_RANGE_DAYS - 1), today)


def parse_range(
    start_param: str | None,
    end_param: str | None,
    today: datetime.date | None = None,
) -> DateRange:
    """Turn the ``?start=``/``?end=`` query params into a usable range.

    Plan 16 D10, in full:

    * Missing or unparseable params fall back to :func:`default_range`
      **silently** — no error page, no "we didn't understand that range"
      message (maintainer decision, 2026-07-25). Both params must parse for
      the reader's range to be honoured; a half-supplied range (only
      reachable by hand-editing the URL, since the presets and the form
      always emit both) gets the default rather than a guessed other end.
    * ``end`` earlier than ``start`` collapses ``end`` to ``start``, giving
      a one-day range rather than an empty one.
    * A range longer than :data:`MAX_RANGE_DAYS` falls back to the default.
      Checked *after* the collapse above, since a collapsed range is one day
      long and can never trip the cap.

    Dates are read with :meth:`datetime.date.fromisoformat`, so the
    ``YYYY-MM-DD`` value an ``<input type="date">`` submits round-trips
    exactly.
    """
    today = today or timezone.localdate()
    start = _parse_date(start_param)
    end = _parse_date(end_param)
    if start is None or end is None:
        return default_range(today)
    if end < start:
        end = start
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        return default_range(today)
    return DateRange(start, end)


def _parse_date(value: str | None) -> datetime.date | None:
    """``value`` as a date, or ``None`` if it is missing or not a date."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None


# --- Range aggregation -----------------------------------------------------


@dataclass(frozen=True)
class DashboardStats:
    """Every figure the dashboard page shows, for one range.

    ``funding_rows``/``gender_rows``/``age_bands`` mirror the shape
    ``DailyReportPage.get_context`` already builds — a list of dicts with
    ``label``, ``count`` and ``pct``, so 16.3's template can reuse the daily
    report's bar markup. One deliberate difference in what ``pct`` *means*,
    which follows the design rather than being an inconsistency to tidy away:

    * ``funding_rows`` and ``age_bands`` — ``pct`` is the share of
      ``total_visits`` (Plan 16 D5). Zakat% + Regular%, and the four
      age-band percentages, can therefore legitimately sum to **under 100**
      when the range holds unknown-payment or unknown-age visits. That
      shortfall is left implicit: no fourth "unknown" category is added, and
      the counts beside each bar stay authoritative.
    * ``gender_rows`` — ``pct`` is the share of the *larger* of Female/Male,
      byte-for-byte what ``DailyReportPage.get_context`` computes, because
      the design gives the gender card a bar scaled to the larger figure and
      no "% of visits" text at all.

    ``age_bands`` carries a second key, ``bar_pct``, for the same reason in
    reverse: its card shows both a "% of visits" figure *and* a fill scaled
    to the largest band, so it needs both numbers. Template paths (the daily
    page's ``icon_template``) are deliberately not set here — this is a data
    module, and picking icons is 16.3's presentation call.
    """

    start: datetime.date
    end: datetime.date

    #: Calendar days in the range, counting both ends.
    total_days: int
    #: ``DailyAggregate`` rows in the range — days that actually reported.
    reporting_days: int
    #: Mon–Sat dates in range with no row, ascending.
    gap_dates: list[datetime.date]

    #: Bars the chart would draw at day grain, and the grain that follows.
    slot_count: int
    grain: str

    total_visits: int
    zakat_beneficiary_patients: int
    paying_patients: int
    female_patients: int
    male_patients: int

    #: ``Σ total_visits / reporting_days``, 1 dp — the "9.5 per reporting
    #: day" KPI sub-line. ``None`` when nothing reported, which the page
    #: renders as "No data" rather than as a zero or a NaN.
    visits_per_reporting_day: float | None

    funding_rows: list[dict]
    gender_rows: list[dict]
    age_bands: list[dict]


def compute_dashboard_stats(date_range: DateRange) -> DashboardStats:
    """Total every ``DailyAggregate`` row in ``date_range``.

    Safe on a range that holds nothing at all: every total comes back zero,
    ``visits_per_reporting_day`` comes back ``None``, and every percentage
    is zero rather than a division by zero.
    """
    rows = DailyAggregate.objects.filter(
        clinic_date__range=(date_range.start, date_range.end)
    )
    totals = rows.aggregate(
        total_visits=Sum("total_visits"),
        zakat_beneficiary_patients=Sum("zakat_beneficiary_patients"),
        paying_patients=Sum("paying_patients"),
        female_patients=Sum("female_patients"),
        male_patients=Sum("male_patients"),
    )
    total_visits = totals["total_visits"] or 0
    zakat = totals["zakat_beneficiary_patients"] or 0
    regular = totals["paying_patients"] or 0
    female = totals["female_patients"] or 0
    male = totals["male_patients"] or 0

    # Second pass, over the JSON column SQL can't sum for us. Only the two
    # columns the pass actually reads are materialised.
    reported_dates: set[datetime.date] = set()
    age_counts = dict.fromkeys((band for band, label in DISPLAY_AGE_BANDS), 0)
    for clinic_date, category_counts in rows.values_list(
        "clinic_date", "category_counts"
    ):
        reported_dates.add(clinic_date)
        by_age = (category_counts or {}).get("by_age_band") or {}
        for band in age_counts:
            age_counts[band] += by_age.get(band, 0) or 0

    slot_count = len(slot_dates(reported_dates, date_range.start, date_range.end))
    largest_age_band = max(age_counts.values(), default=0)
    gender_max = max(female, male)

    return DashboardStats(
        start=date_range.start,
        end=date_range.end,
        total_days=date_range.days,
        reporting_days=len(reported_dates),
        gap_dates=reporting_gap_dates(reported_dates, date_range),
        slot_count=slot_count,
        grain=select_grain(slot_count),
        total_visits=total_visits,
        zakat_beneficiary_patients=zakat,
        paying_patients=regular,
        female_patients=female,
        male_patients=male,
        visits_per_reporting_day=(
            round(total_visits / len(reported_dates), 1) if reported_dates else None
        ),
        funding_rows=[
            {"label": _("Zakat"), "count": zakat, "pct": _share(zakat, total_visits)},
            {
                "label": _("Regular"),
                "count": regular,
                "pct": _share(regular, total_visits),
            },
        ],
        gender_rows=[
            {"label": _("Female"), "count": female, "pct": _share(female, gender_max)},
            {"label": _("Male"), "count": male, "pct": _share(male, gender_max)},
        ],
        age_bands=[
            {
                "label": label,
                "count": age_counts[band],
                "pct": _share(age_counts[band], total_visits),
                "bar_pct": _share(age_counts[band], largest_age_band),
            }
            for band, label in DISPLAY_AGE_BANDS
        ],
    )


def _share(count: int, total: int) -> int:
    """``count`` as a whole-number percentage of ``total``; 0 if ``total`` is 0.

    Rounded to an integer, matching ``DailyReportPage.get_context``. The
    counts are always rendered beside the bars, so the rounding never costs
    the reader a real figure (Plan 16 D5).
    """
    return round(count / total * 100) if total else 0


def reporting_gap_dates(reported_dates, date_range: DateRange) -> list[datetime.date]:
    """Mon–Sat dates in ``date_range`` with no ``DailyAggregate`` row, ascending.

    Sundays are never a gap: the clinic is closed, so their absence is
    expected rather than missing (the same rule ``footfall_chart.slot_dates``
    encodes for chart slots). A Sunday that *did* report is not a gap either
    — it has a row.
    """
    gaps = []
    day = date_range.start
    while day <= date_range.end:
        if day.weekday() != SUNDAY_WEEKDAY and day not in reported_dates:
            gaps.append(day)
        day += datetime.timedelta(days=1)
    return gaps


def select_grain(slot_count: int) -> str:
    """Chart grain for a range that would draw ``slot_count`` day-grain bars.

    Plan 16 D3: ≤ 90 slots → one bar per day, 91–400 → one bar per week
    starting Monday, > 400 → one bar per calendar month.
    """
    if slot_count <= DAY_GRAIN_MAX_SLOTS:
        return GRAIN_DAY
    if slot_count <= WEEK_GRAIN_MAX_SLOTS:
        return GRAIN_WEEK
    return GRAIN_MONTH


# --- Chart bucketing (Plan 16 D3/D16) --------------------------------------


@dataclass(frozen=True)
class FootfallBucket:
    """One chart bar's figures, whatever grain produced it.

    Duck-typed to exactly the four attributes
    ``footfall_chart.build_footfall_chart`` reads off a row — so a list of
    these can be handed straight to it, with no adapter and no change to how
    it reads its input. ``clinic_date`` is the bucket's **first** date (the
    day itself, the week's Monday, or the month's 1st), which is what the
    caption labels the bar with.
    """

    clinic_date: datetime.date
    total_visits: int
    zakat_beneficiary_patients: int
    paying_patients: int


@dataclass(frozen=True)
class BucketedFootfall:
    """``rows`` folded to ``grain``, plus the slots those buckets sit in.

    ``slots`` is every bucket position in the range, in order, **including
    the empty ones**; ``buckets`` holds only those with at least one
    reporting day. Keeping them apart is what preserves Plan 13's two rules
    at every grain: a slot with no bucket renders as a visible gap rather
    than as a zero-height bar the tooltip would report as a real zero, and a
    Sunday still gets no slot of its own at day grain (at week and month
    grain the question dissolves — a Sunday that reported folds into its
    bucket like any other date).
    """

    grain: str
    slots: list[datetime.date]
    buckets: list[FootfallBucket]


def bucket_footfall(rows, date_range: DateRange, grain: str) -> BucketedFootfall:
    """Fold ``rows`` into one bucket per chart slot at ``grain``.

    ``rows`` is duck-typed the same way ``footfall_chart`` takes them — any
    iterable exposing ``clinic_date``, ``total_visits``,
    ``zakat_beneficiary_patients`` and ``paying_patients``. Rows outside
    ``date_range`` are ignored; the caller owns the query, exactly as it
    does for the chart itself.

    At ``GRAIN_DAY`` this is a pass-through in all but type: one bucket per
    reporting date and the same slots ``footfall_chart.slot_dates`` would
    have computed, so the existing day-grain chart is unchanged by going
    through it.
    """
    in_range = [
        row for row in rows if date_range.start <= row.clinic_date <= date_range.end
    ]
    if grain == GRAIN_DAY:
        slots = slot_dates(
            {row.clinic_date for row in in_range}, date_range.start, date_range.end
        )
    elif grain == GRAIN_WEEK:
        slots = _week_starts(date_range)
    elif grain == GRAIN_MONTH:
        slots = _month_starts(date_range)
    else:
        raise ValueError(f"Unknown footfall grain: {grain!r}")

    totals: dict[datetime.date, list[int]] = {}
    for row in in_range:
        bucket = totals.setdefault(_bucket_start(row.clinic_date, grain), [0, 0, 0])
        bucket[0] += row.total_visits
        bucket[1] += row.zakat_beneficiary_patients
        bucket[2] += row.paying_patients

    return BucketedFootfall(
        grain=grain,
        slots=slots,
        buckets=[
            FootfallBucket(slot, *totals[slot]) for slot in slots if slot in totals
        ],
    )


def _bucket_start(day: datetime.date, grain: str) -> datetime.date:
    """The first date of the bucket ``day`` falls in, at ``grain``."""
    if grain == GRAIN_WEEK:
        return day - datetime.timedelta(days=day.weekday())
    if grain == GRAIN_MONTH:
        return day.replace(day=1)
    return day


def _week_starts(date_range: DateRange) -> list[datetime.date]:
    """Every Monday whose week overlaps ``date_range``, ascending.

    The first slot is the Monday on or before ``start``, so a bucket keeps
    its real week identity — a range opening mid-week is labelled with that
    week's Monday even though the Monday itself sits outside the range. Only
    rows inside the range are ever folded into it.
    """
    weeks = []
    week = _bucket_start(date_range.start, GRAIN_WEEK)
    while week <= date_range.end:
        weeks.append(week)
        week += datetime.timedelta(days=7)
    return weeks


def _month_starts(date_range: DateRange) -> list[datetime.date]:
    """The 1st of every calendar month overlapping ``date_range``, ascending."""
    months = []
    month = date_range.start.replace(day=1)
    last = date_range.end.replace(day=1)
    while month <= last:
        months.append(month)
        month = (month + datetime.timedelta(days=32)).replace(day=1)
    return months


# --- Revenue gate (Plan 16 D6) ---------------------------------------------


def has_revenue(rows) -> bool:
    """Whether the range has per-service revenue to show. Always ``False`` today.

    Plan 16 D6: revenue is gated on **data**, not on a runtime feature flag,
    so every revenue surface — the fourth KPI card, the "Revenue by service"
    table, the side-column layout switch — branches on this from day one and
    Phase 2 needs no template work.

    ``DailyAggregate`` has no revenue column yet. D13 records why: the clinic
    software is being updated to add fee columns to the daily patient export,
    and until that release ships there is genuinely nothing to sum. When the
    ``service_revenue`` column lands (see the plan file's Phase 2 checklist)
    this becomes ``any(row.service_revenue for row in rows)`` and nothing
    else in the codebase has to change.
    """
    return False
