"""Server-rendered SVG geometry for the stacked Zakat/Regular footfall chart.

Extracted verbatim from ``ReportIndexPage.get_funding_mix`` (Plan 13, PRs
#122/#124) in Plan 16 task 16.1, so the forthcoming clinic dashboard can
call the same code instead of copying it (Plan 16 D2). **No behaviour
change** — Plan 13's tests are the acceptance test for the extraction.

Bar coordinates and path data are computed here in Python rather than in the
template or client JS, so the chart renders fully without JavaScript —
mirrors ``circle-of-care.js``'s documented progressive-enhancement precedent
("the section renders fully without this script; this only adds the
reveal"). ``funding-mix-chart.js`` only wires up the hover tooltip on top of
this. Keep that property: geometry belongs here, not in a script.

Rows are duck-typed, not queried — this module takes whatever the caller has
already fetched (``DailyAggregate`` instances today) and reads only
``clinic_date``, ``total_visits``, ``zakat_beneficiary_patients`` and
``paying_patients``. Windowing is deliberately the caller's job: the reports
index applies its rolling 30 days, and the dashboard will apply a
reader-chosen range.

Two rules the geometry encodes on purpose, both from Plan 13 (see
``slot_dates``): Sundays get no slot because the clinic is closed, and a
Mon–Sat day with no report keeps its slot and renders as a visible gap.

**The Plan 16.2/16.3 seam, now closed** (task 16.3, 2026-07-25 — this
replaces 16.1's forward-looking note, which described a future that has
since arrived). 16.1 left two things unbuilt because they had no caller
yet; the clinic dashboard is that caller, so both are now real arguments
rather than speculation:

* ``slots`` — a caller-supplied ordered slot list. The dashboard plots week
  and month buckets on longer ranges (D3), and ``slot_dates`` below only
  knows how to walk a range *day by day*, so a week-grain range would
  otherwise get day slots carrying bars on Mondays alone. Deliberately an
  explicit slot list rather than a ``grain`` enum (D16): calendar policy
  lives in ``apps.pipeline.dashboard.bucket_footfall``, which already
  returns ``BucketedFootfall.slots``, and a ``grain`` enum here would
  duplicate that policy across two modules. Left optional, so the reports
  index — whose window is always day-grain — keeps calling this with the
  same three arguments 16.1 published.
* ``bar_class_prefix`` — the BEM block each bar segment's CSS class is
  built from (see :data:`DEFAULT_BAR_CLASS_PREFIX`). Those class names were
  the reports index's own scope back when it was the only caller; the
  dashboard names its own block instead of borrowing another page's
  stylesheet.

Nothing else here is grain-aware, and nothing needs to be: :func:`_bar`
reads four attributes off whatever it is handed, and ``bucket_footfall``
returns objects carrying exactly those four.
"""

from __future__ import annotations

import datetime

# SVG chart geometry (Plan 13) — fixed marks, not configurable.
CHART_WIDTH = 620
CHART_HEIGHT = 220
PAD_LEFT = 30
PAD_RIGHT = 10
PAD_TOP = 14
PAD_BOTTOM = 26
MAX_BAR_WIDTH = 24
STACK_GAP = 2  # surface gap between stacked segments
BAR_CORNER_RADIUS = 4
SUNDAY_WEEKDAY = 6  # date.weekday() — the clinic is closed Sundays
# Minimum centre-to-centre spacing (viewBox units) between two date
# labels. Measured against the widest rendered label ("27 Jun", ~30
# units) with headroom for a longer translated month name — Plan 13's
# Mon–Sat gap slots (see slot_dates) mean consecutive-day runs can now
# pack bars closer than a label is wide.
MIN_LABEL_SPACING = 40

#: BEM block the bar segments' CSS classes are built from, when the caller
#: names none. This is the reports index's own block, which is where these
#: class names started: they were written when ``get_funding_mix`` was the
#: only caller and stayed literal through 16.1's extraction. Keeping it the
#: default is what lets that caller — and the 16.1-era three-argument
#: contract generally — go on working unchanged. Any *new* caller should
#: pass its own block rather than style itself out of `report-index.css`.
DEFAULT_BAR_CLASS_PREFIX = "ri-funding-mix"


def build_footfall_chart(
    rows, start, end, slots=None, *, bar_class_prefix=DEFAULT_BAR_CLASS_PREFIX
) -> dict:
    """Stacked Zakat-vs-Regular bars for ``rows``, as SVG geometry.

    ``rows`` is any iterable of daily aggregates; ``start`` and ``end`` are
    the inclusive calendar bounds of the plotted window. Rows outside those
    bounds get no bar (they have no slot) but still set the y-scale, so the
    caller is responsible for passing bounds that cover the rows it wants
    drawn.

    ``slots`` overrides the day-by-day slot walk with an explicit ordered
    list of slot dates — one per bar position, empty positions included (see
    this module's docstring and Plan 16 D16). Each row is then matched to a
    slot by its ``clinic_date``, so a caller plotting week or month buckets
    passes buckets whose ``clinic_date`` is the bucket's first date, which
    is exactly what ``dashboard.bucket_footfall`` returns. ``start``/``end``
    are not consulted in that case: supplying the slots *is* deciding the
    layout, and the caller has already windowed its rows to build them.

    ``bar_class_prefix`` names the BEM block each segment's ``css_class`` is
    built from, so a second caller can style the chart from its own
    page-scoped stylesheet.

    Returns the empty chart (``{"bars": [], "ticks": []}``) when there is
    nothing to plot — no rows, or no slots in the range at all.

    Reuses the exact fields ``DailyReportPage.headline_stats`` already
    surfaces under the same labels: ``zakat_beneficiary_patients`` →
    "Zakat", ``paying_patients`` → "Regular" (``models.py``).

    Bars are positioned by each day's slot in the full calendar range (see
    ``slot_dates``), not by its position in the query result — so a
    Monday–Saturday day with no report reserves a blank slot and renders as
    a visible gap, rather than the timeline silently compressing around it.
    A Sunday with no report gets no slot at all, since the clinic's closure
    that day is expected.
    """
    rows_by_date = {row.clinic_date: row for row in rows}
    if not rows_by_date:
        return {"bars": [], "ticks": []}

    dates = slot_dates(rows_by_date, start, end) if slots is None else list(slots)
    if not dates:
        # No slots in range at all — ``end`` before ``start``, or a range
        # that is only closed Sundays. The reports index can't produce
        # either (its window is 30 days with ``end >= start``), but the
        # dashboard's range is reader-supplied, so return the same empty
        # contract as the no-rows case above rather than dividing by zero.
        return {"bars": [], "ticks": []}

    plot_width = CHART_WIDTH - PAD_LEFT - PAD_RIGHT
    plot_height = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM

    max_total = max(row.total_visits for row in rows_by_date.values()) or 1
    tick_step = 5 if max_total <= 20 else 10
    max_value = ((max_total // tick_step) + 1) * tick_step

    def y_for(value):
        raw = PAD_TOP + plot_height - (value / max_value) * plot_height
        return round(raw, 2)

    baseline = y_for(0)
    slot_width = round(plot_width / len(dates), 2)
    bar_width = round(min(MAX_BAR_WIDTH, slot_width * 0.6), 2)

    date_label_y = CHART_HEIGHT - 8

    bars = []
    last_label_x = None
    for i, slot_date in enumerate(dates):
        row = rows_by_date.get(slot_date)
        if row is None:
            continue  # Mon–Sat, no report — leave the slot empty (a gap)
        bar = _bar(
            row,
            i,
            slot_width,
            bar_width,
            baseline,
            y_for,
            date_label_y,
            bar_class_prefix,
        )
        # Gap slots let real bars pack closer together than a date label
        # is wide (see MIN_LABEL_SPACING) — thin colliding labels rather
        # than let them overlap. Every bar still gets its hit-tooltip and
        # its row in the table below, so no date is actually hidden, just
        # its always-visible axis text.
        bar["show_label"] = (
            last_label_x is None or bar["label_x"] - last_label_x >= MIN_LABEL_SPACING
        )
        if bar["show_label"]:
            last_label_x = bar["label_x"]
        bars.append(bar)
    ticks = [
        {"value": t, "y": y_for(t), "label_y": y_for(t) + 3}
        for t in range(0, max_value + 1, tick_step)
    ]
    return {
        "bars": bars,
        "ticks": ticks,
        "chart_width": CHART_WIDTH,
        "chart_height": CHART_HEIGHT,
        "grid_x1": PAD_LEFT,
        "grid_x2": CHART_WIDTH - PAD_RIGHT,
        "axis_label_x": PAD_LEFT - 6,
    }


def slot_dates(rows_by_date, start, end):
    """Ordered list of dates that get a chart slot between ``start`` and
    ``end`` inclusive.

    A Sunday with no ``DailyAggregate`` row gets no slot at all — the
    clinic is closed Sundays by design, so its absence is expected, not a
    gap. Every other day in range gets a slot regardless of whether it has
    data; the caller renders a bar for slots with data and leaves the rest
    empty, which is what shows up as a gap in the chart. A Sunday that does
    have a row (an exceptional open day) is kept, same as any other day
    with data.
    """
    dates = []
    d = start
    while d <= end:
        if d in rows_by_date or d.weekday() != SUNDAY_WEEKDAY:
            dates.append(d)
        d += datetime.timedelta(days=1)
    return dates


def _bar(
    row, index, slot_width, bar_width, baseline, y_for, date_label_y, class_prefix
):
    cx = round(PAD_LEFT + slot_width * index + slot_width / 2, 2)
    x = round(cx - bar_width / 2, 2)
    zakat_top = y_for(row.zakat_beneficiary_patients)
    total_top = y_for(row.zakat_beneficiary_patients + row.paying_patients)

    if row.zakat_beneficiary_patients == 0:
        # Solo regular segment, resting on the baseline — mirrors the
        # solo-zakat case below. Without this, the regular segment's base
        # would be offset by STACK_GAP above a degenerate zero-height
        # zakat segment, floating it off the baseline.
        segments = [
            {
                "path": _rounded_top_path(x, total_top, bar_width, baseline),
                "css_class": f"{class_prefix}__bar--regular",
            }
        ]
    elif row.paying_patients == 0:
        segments = [
            {
                "path": _rounded_top_path(x, zakat_top, bar_width, baseline),
                "css_class": f"{class_prefix}__bar--zakat",
            }
        ]
    else:
        regular_base = zakat_top - STACK_GAP
        segments = [
            {
                "path": _square_path(x, zakat_top, bar_width, baseline),
                "css_class": f"{class_prefix}__bar--zakat",
            },
            {
                "path": _rounded_top_path(x, total_top, bar_width, regular_base),
                "css_class": f"{class_prefix}__bar--regular",
            },
        ]

    return {
        "date": row.clinic_date,
        "zakat": row.zakat_beneficiary_patients,
        "regular": row.paying_patients,
        "total": row.total_visits,
        "segments": segments,
        "label_x": cx,
        "label_y": date_label_y,
        "hit_x": cx - slot_width / 2,
        "hit_width": slot_width,
    }


def _rounded_top_path(x, y_top, width, y_base):
    r = min(BAR_CORNER_RADIUS, width / 2, max(0, y_base - y_top))
    return (
        f"M {x} {y_base} L {x} {y_top + r} Q {x} {y_top} {x + r} {y_top} "
        f"L {x + width - r} {y_top} "
        f"Q {x + width} {y_top} {x + width} {y_top + r} "
        f"L {x + width} {y_base} Z"
    )


def _square_path(x, y_top, width, y_base):
    x_end, y_end = x + width, y_top
    return f"M {x} {y_base} L {x} {y_top} L {x_end} {y_end} L {x_end} {y_base} Z"
