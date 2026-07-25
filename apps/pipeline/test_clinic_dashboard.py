"""``ClinicDashboardPage`` — the rendered page (Plan 16, task 16.3).

The range arithmetic behind it is 16.2's and is tested in
``test_dashboard.py``; this file is about what actually reaches a reader:
the layout branches, the no-JS controls, the chart's accessible fallback,
and the page's behaviour on the ranges that would otherwise produce a NaN
or a 500.
"""

from __future__ import annotations

import datetime
import re

import pytest
from django.utils import timezone
from wagtail.models import Site

from apps.core.factories import HomePageFactory
from apps.pipeline import dashboard as dashboard_module
from apps.pipeline.factories import DailyAggregateFactory, ReportIndexPageFactory
from apps.pipeline.footfall_chart import CHART_HEIGHT, build_footfall_chart
from apps.pipeline.models import ClinicDashboardPage
from apps.pipeline.report_publishing import _get_or_create_clinic_dashboard

pytestmark = pytest.mark.django_db

# A Monday, so week-grain assertions can count off weekdays without a
# calendar in hand.
MONDAY = datetime.date(2026, 6, 1)


def day(offset: int) -> datetime.date:
    return MONDAY + datetime.timedelta(days=offset)


@pytest.fixture
def home_page():
    """A site-rooted HomePage — same shape as ``tests.py``'s fixture of the
    same name (kept local rather than moved to conftest, so that file's own
    tests are untouched by this task)."""
    home = HomePageFactory()
    site = Site.objects.get(is_default_site=True)
    site.root_page = home
    site.save()
    return home


@pytest.fixture
def dashboard(home_page):
    """The dashboard page, created through the real get-or-create helper.

    Deliberately not a factory: the helper (and the data migration that
    calls it) is how this page reaches every real environment, so exercising
    it here means the fixture itself covers the D1 creation path.
    """
    ReportIndexPageFactory(parent=home_page, slug="reports")
    return _get_or_create_clinic_dashboard()


def aggregate(clinic_date, *, total=6, zakat=4, regular=2, by_age=None):
    return DailyAggregateFactory(
        clinic_date=clinic_date,
        total_visits=total,
        zakat_beneficiary_patients=zakat,
        paying_patients=regular,
        female_patients=total - 2,
        male_patients=2,
        category_counts={"by_age_band": by_age or {"19-55": total}},
    )


def render(client, dashboard, **params) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{dashboard.url}?{query}" if query else dashboard.url
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode()


def squash(text: str) -> str:
    """Collapse template whitespace so copy can be asserted as one line."""
    return re.sub(r"\s+", " ", text)


# --- Creation in the tree (D1) ---------------------------------------------


def test_get_or_create_clinic_dashboard_is_idempotent(dashboard):
    """Called twice — the second call returns the same page, never a second
    one. This is what lets the data migration and ``publish_daily_report``
    both call it without racing to create duplicates."""
    again = _get_or_create_clinic_dashboard()

    assert again.pk == dashboard.pk
    assert ClinicDashboardPage.objects.count() == 1


def test_clinic_dashboard_lives_under_the_reports_index(dashboard):
    assert dashboard.slug == "dashboard"
    assert dashboard.get_parent().slug == "reports"
    assert dashboard.live is True
    # The locale prefix is real on this site — `/reports/dashboard/` (the
    # handoff's path) does not exist, `i18n_patterns` wraps Wagtail's
    # catch-all (Plan 16 D1).
    assert dashboard.url == "/en/reports/dashboard/"


def test_get_or_create_creates_the_reports_index_too_if_missing(home_page):
    """A fresh install runs migrations before anything has made a Reports
    index, so the helper has to be able to build its own parent."""
    created = _get_or_create_clinic_dashboard()

    assert created.get_parent().specific.slug == "reports"


# --- Layout branches (D6 — revenue is gated on data, not a flag) -----------


def test_renders_three_kpi_cards_and_no_revenue_card(client, dashboard):
    aggregate(timezone.localdate())

    content = render(client, dashboard)

    assert content.count('class="dash__kpi"') == 3
    assert "Patients seen" in content
    assert "Zakat visits" in content
    assert "Regular visits" in content
    # No fourth card, and no empty revenue table left behind either.
    assert 'data-role="kpi-revenue"' not in content
    assert 'data-role="revenue"' not in content
    assert "Revenue by service" not in content


def test_side_cards_render_whether_or_not_revenue_exists(client, dashboard):
    """Funding split and Gender sit side by side beneath the (absent) revenue
    table, in the same auto-fitting pair they will occupy once it arrives.

    Plan 18 Track B moved the table to its own full-width row, so unlike Plan
    16's 1.75fr/1fr split this layout carries no `--no-revenue` modifier —
    there is nothing left for `has_revenue` to switch. That absence is the
    assertion: a modifier creeping back in means the two states diverged
    again.
    """
    aggregate(timezone.localdate())

    content = render(client, dashboard)

    assert 'class="dash__split"' in content
    assert "dash__split--no-revenue" not in content
    assert 'data-role="funding-split"' in content
    assert 'data-role="gender"' in content


def test_revenue_branches_light_up_when_has_revenue_turns_true(
    client, dashboard, monkeypatch
):
    """Phase 2's rehearsal: the same template renders the fourth KPI card and
    the revenue table with no template change — only ``dashboard.has_revenue``
    flipping (Plan 16 D6). The surrounding layout is unchanged by design
    (Plan 18 D6), which is why only the two revenue surfaces are asserted."""
    aggregate(timezone.localdate())
    monkeypatch.setattr(dashboard_module, "has_revenue", lambda rows: True)

    content = render(client, dashboard)

    assert content.count('class="dash__kpi"') == 4
    assert 'data-role="kpi-revenue"' in content
    assert 'data-role="revenue"' in content
    assert "Revenue by service" in content
    # The rows scroll as one block on a narrow screen rather than each
    # crushing its own tracks — the head sits outside the scroller.
    assert 'class="dash__revenue-scroll"' in content
    assert 'class="dash__split"' in content
    assert "dash__split--no-revenue" not in content


# --- The header line -------------------------------------------------------


def test_header_line_reads_range_days_and_reporting_days(client, dashboard):
    for offset in range(5):
        aggregate(day(offset))

    content = squash(render(client, dashboard, start=day(0), end=day(29)))

    assert "1 Jun 2026 – 30 Jun 2026 · 30 days · 5 reporting days" in content


def test_header_line_uses_singular_forms_for_a_one_day_range(client, dashboard):
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(0)))

    assert "1 Jun 2026 – 1 Jun 2026 · 1 day · 1 reporting day" in content


# --- Presets and the date form, both without JavaScript (D9) ---------------


def test_presets_are_plain_links_carrying_the_range(client, dashboard):
    today = timezone.localdate()
    aggregate(today)

    content = render(client, dashboard)

    for label in ("7 days", "14 days", "30 days", "90 days", "1 year"):
        assert label in content
    # Links, not buttons — no script turns these into anything.
    week_start = (today - datetime.timedelta(days=6)).isoformat()
    assert f'href="{dashboard.url}?start={week_start}&amp;end={today.isoformat()}"' in (
        content
    )


def test_the_preset_matching_the_current_range_length_is_selected(client, dashboard):
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(6)))

    selected = re.findall(r'dash__preset--selected"[^>]*>([^<]+)<', content)
    assert selected == ["7 days"]


def test_range_controls_are_one_reflowing_stack_at_every_width(client, dashboard):
    """The approved mobile pattern (option 1c, "everything visible") is a
    reflow, not a second layout: presets and both dates are on the page at
    390px exactly as they are at 1280px, behind no tap.

    Plan 18 Track B. The widths themselves are CSS and aren't testable here;
    what is testable — and what a regression would break first — is that the
    markup carries no width-conditional branch and each date field is its own
    labelled block rather than sharing one line with a separator.
    """
    aggregate(day(0))

    content = render(client, dashboard, start=day(0), end=day(6))

    form = re.search(r'<form class="dash__dates".*?</form>', content, re.S).group()
    assert form.count('class="dash__date-field"') == 2
    for field_id in ("dash-start", "dash-end"):
        assert f'for="{field_id}"' in form
        assert f'id="{field_id}"' in form
    # The old single-line card's "–" between the two inputs is gone; the
    # fields are stacked label-over-input in their own blocks now.
    assert "dash__date-sep" not in form


def test_date_form_is_a_get_form_with_a_visible_apply_and_no_script(client, dashboard):
    aggregate(day(0))

    content = render(client, dashboard, start=day(0), end=day(6))

    form = re.search(r'<form class="dash__dates".*?</form>', content, re.S).group()
    assert 'method="get"' in form
    assert f'action="{dashboard.url}"' in form
    assert '<button class="dash__apply" type="submit">Apply</button>' in squash(form)
    # Nothing auto-submits: the maintainer chose the plain Apply button, so
    # the form carries no handler and the page's own markup ships no script
    # at all (the sitewide ones base.html loads after the footer are another
    # matter — none of them touches this page).
    assert "onchange" not in form.lower()
    page_body = content.split('class="dash wrapper"')[1].split("<footer")[0]
    assert "<script" not in page_body
    # The chart's hover hooks (added 2026-07-25) are the one JS-facing
    # markup on this page, and they are scoped to the chart: the range
    # controls this test is about still carry no handler of any kind.
    assert "data-funding-mix" not in form


def test_date_inputs_are_prefilled_with_the_current_range(client, dashboard):
    """The reader's own range comes back in the fields, in the ISO format an
    ``<input type="date">`` submits — so pressing Apply again is a no-op
    rather than a silent reset to the default."""
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(6)))

    fields = dict(
        re.findall(r'name="(start|end)" value="([\d-]+)" max="[\d-]+"', content)
    )
    assert fields == {"start": "2026-06-01", "end": "2026-06-07"}


# --- The chart and its accessible fallback ---------------------------------


def test_chart_is_role_img_with_an_aria_label(client, dashboard):
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(5)))

    assert 'role="img"' in content
    assert "Patient footfall from 1 Jun 2026 to 6 Jun 2026" in content


def test_every_bar_gets_a_hover_hit_rect_carrying_its_own_figures(client, dashboard):
    """The hover tooltip funding-mix-chart.js opens (2026-07-25) reads only
    these attributes, so a bar without one is a bar the reader cannot hover.
    The date spells the year out like the table row it mirrors, not like the
    axis label under the bar."""
    aggregate(day(0), total=7, zakat=5, regular=2)
    aggregate(day(2), total=9, zakat=3, regular=6)

    content = render(client, dashboard, start=day(0), end=day(5))

    # The <svg>'s own opt-in hook, and the three label strings the script
    # builds the tooltip sentence from — without these the rects below are
    # never wired up at all.
    svg = re.search(r"<svg class=\"dash-chart__plot\".*?>", content, re.S).group()
    assert "data-funding-mix\n" in svg
    for label in ("zakat", "regular", "total"):
        assert f'data-label-{label}="' in svg
    hits = re.findall(r"<rect class=\"dash-chart__hit\".*?/>", content, re.S)
    assert len(hits) == 2
    for hit, (date, zakat, regular, total) in zip(
        hits,
        [("1 Jun 2026", 5, 2, 7), ("3 Jun 2026", 3, 6, 9)],
        strict=True,
    ):
        assert f'data-date="{date}"' in hit
        assert f'data-zakat="{zakat}"' in hit
        assert f'data-regular="{regular}"' in hit
        assert f'data-total="{total}"' in hit


def test_hover_hit_rects_are_full_height_so_short_bars_stay_hoverable(
    client, dashboard
):
    """Next to a 200-visit day a 2-visit day is a few pixels tall, but both
    hit targets span the full plot, so the quiet day is as easy to hover as
    the busy one."""
    aggregate(day(0), total=200, zakat=150, regular=50)
    aggregate(day(2), total=2, zakat=2, regular=0)

    content = render(client, dashboard, start=day(0), end=day(5))

    hits = re.findall(r"<rect class=\"dash-chart__hit\".*?/>", content, re.S)
    assert len(hits) == 2
    for hit in hits:
        # Asserted against the geometry module's own constant, not against a
        # chart rebuilt here from a second copy of the rows: the plot height
        # is fixed, so a local rebuild would only add a copy to drift.
        assert f'height="{CHART_HEIGHT}"' in hit
        assert 'y="0"' in hit


def test_view_as_table_lists_every_bucket_with_its_figures(client, dashboard):
    """Day grain: one row per reporting day, all four columns."""
    aggregate(day(0), total=7, zakat=5, regular=2)
    aggregate(day(2), total=9, zakat=3, regular=6)

    content = render(client, dashboard, start=day(0), end=day(5))

    assert "View as table" in content
    rows = re.findall(r"<tr>\s*<td>(.*?)</td>", content, re.S)
    assert [row.strip() for row in rows] == ["1 Jun 2026", "3 Jun 2026"]
    for figure in ("<td>5</td>", "<td>2</td>", "<td>7</td>", "<td>9</td>"):
        assert figure in content


def test_view_as_table_lists_every_week_bucket_at_week_grain(client, dashboard):
    """A 130-day range crosses D3's 90-slot boundary into week grain, and
    every week that reported gets its own row — labelled by its Monday."""
    for offset in (0, 5, 8, 100):
        aggregate(day(offset))

    content = render(client, dashboard, start=day(0), end=day(129))

    assert "One bar per week, starting Monday." in squash(content)
    rows = [row.strip() for row in re.findall(r"<tr>\s*<td>(.*?)</td>", content, re.S)]
    # Weeks 1 (two reporting days folded together), 2, and the week holding
    # day 100 — the ~16 weeks with nothing reported keep their slots but get
    # no row, exactly as an unreported weekday does at day grain.
    assert rows == ["1 Jun 2026", "8 Jun 2026", "7 Sep 2026"]


def test_chart_uses_its_own_css_block_not_the_reports_index_one(client, dashboard):
    """The geometry is shared with the reports index; the styling is not."""
    aggregate(day(0))

    content = render(client, dashboard, start=day(0), end=day(5))

    assert "dash-chart__bar--zakat" in content
    assert "ri-funding-mix" not in content


def test_caption_states_the_grain_and_keeps_the_sundays_sentence(client, dashboard):
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(5)))

    assert "One bar per day the clinic reported data." in content
    assert "Sundays are omitted — the clinic is closed." in content


def test_month_grain_labels_buckets_by_month(client, dashboard):
    """Past D3's 400-slot boundary the grain becomes one bar per month."""
    aggregate(day(0))
    aggregate(day(400))

    content = squash(render(client, dashboard, start=day(0), end=day(500)))

    assert "One bar per month." in content
    rows = [row.strip() for row in re.findall(r"<tr>\s*<td>(.*?)</td>", content, re.S)]
    assert rows == ["Jun 2026", "Jul 2027"]


# --- Reporting gaps --------------------------------------------------------


def test_gap_chips_cap_at_twelve_and_append_a_more_chip(client, dashboard):
    aggregate(day(0))

    content = squash(render(client, dashboard, start=day(0), end=day(20)))

    chips = re.findall(r'class="dash__chip[^"]*"> ?([^<]+?) ?<', content)
    assert len(chips) == ClinicDashboardPage.MAX_GAP_CHIPS + 1
    assert chips[0] == "2 Jun"
    assert chips[-1].startswith("+")
    assert chips[-1].endswith("more")


def test_no_gaps_shows_the_single_none_chip(client, dashboard):
    """Mon–Sat all reported; the Sunday in between is not a gap."""
    for offset in range(6):
        aggregate(day(offset))

    content = squash(render(client, dashboard, start=day(0), end=day(6)))

    chips = re.findall(r'class="dash__chip[^"]*"> ?([^<]+?) ?<', content)
    assert chips == ["None — every open day reported"]


# --- The ranges that must not break ----------------------------------------


@pytest.mark.parametrize(
    ("label", "params"),
    [
        ("empty range", {"start": "2030-01-01", "end": "2030-01-20"}),
        ("one-day range", {"start": "2026-06-01", "end": "2026-06-01"}),
        ("five-year range", {"start": "2021-08-01", "end": "2026-07-25"}),
        ("garbage params", {"start": "banana", "end": "2026-13-45"}),
        ("end before start", {"start": "2026-06-30", "end": "2026-06-01"}),
        ("no params", {}),
    ],
)
def test_range_renders_a_sane_page(client, dashboard, label, params):
    aggregate(day(0))

    content = render(client, dashboard, **params)

    assert "NaN" not in content
    assert "Clinic dashboard" in content
    assert "None" not in re.findall(r'dash__kpi-value">([^<]+)<', content)


def test_empty_range_shows_no_data_rather_than_a_zero_rate(client, dashboard):
    content = squash(render(client, dashboard, start="2030-01-01", end="2030-01-20"))

    assert "No data" in content
    assert "per reporting day" not in content
    # The chart has nothing to plot, so it says so instead of drawing an
    # axis around an empty plot area.
    assert "View as table" not in content


# --- The two meanings of `pct` (D5) ----------------------------------------


def test_gender_card_renders_no_percentage_text(client, dashboard):
    """`gender_rows.pct` is the share of the larger of Female/Male, so it
    scales the two bars against each other — rendering it as "% of visits"
    would be plainly wrong, and the design gives the card no % at all."""
    aggregate(day(0), total=10, zakat=6, regular=4)

    content = render(client, dashboard, start=day(0), end=day(5))
    gender_card = content.split('data-role="gender"')[1].split("</section>")[0]

    assert "%" not in re.sub(r'style="width: \d+%;"', "", gender_card)


def test_funding_percentages_may_sum_to_under_a_hundred(client, dashboard):
    """Zakat 4 + Regular 2 out of 10 visits — the four unknown-payment
    visits are shown by omission, not as a fourth category (D5), and the
    counts beside each bar stay authoritative."""
    aggregate(day(0), total=10, zakat=4, regular=2)

    content = squash(render(client, dashboard, start=day(0), end=day(5)))

    assert "40% of all visits" in content
    assert "20% of all visits" in content
    assert "Zakat patients" in content
    assert "Regular patients" in content
    assert ">4<" in content and ">2<" in content


# --- The slot argument on the shared geometry (D16) ------------------------


def test_build_footfall_chart_lays_bars_out_on_caller_supplied_slots():
    """A week-grain range: three week slots, the middle one empty. The empty
    week keeps its slot (so it reads as a gap) and the third week's bar sits
    where the third slot is — not squeezed up next to the first."""
    date_range = dashboard_module.DateRange(MONDAY, day(20))
    rows = [_Row(day(0), 10, 6, 4), _Row(day(15), 8, 5, 3)]

    bucketed = dashboard_module.bucket_footfall(
        rows, date_range, dashboard_module.GRAIN_WEEK
    )
    chart = build_footfall_chart(
        bucketed.buckets,
        date_range.start,
        date_range.end,
        slots=bucketed.slots,
        bar_class_prefix="dash-chart",
    )

    assert bucketed.slots == [MONDAY, day(7), day(14)]
    assert [bar["date"] for bar in chart["bars"]] == [MONDAY, day(14)]
    # Two bars, three slots: the gap between them is two slot widths, which
    # is only true if the second bar was placed at index 2.
    gap = chart["bars"][1]["label_x"] - chart["bars"][0]["label_x"]
    assert round(gap, 2) == round(2 * chart["bars"][0]["hit_width"], 2)


def test_build_footfall_chart_without_slots_is_unchanged():
    """The reports index still calls this with three arguments and still
    gets day slots and its own class names — 16.1's contract, untouched."""
    chart = build_footfall_chart([_Row(MONDAY, 5, 3, 2)], MONDAY, day(5))

    assert [bar["date"] for bar in chart["bars"]] == [MONDAY]
    assert chart["bars"][0]["segments"][0]["css_class"] == "ri-funding-mix__bar--zakat"


class _Row:
    """Duck-typed daily aggregate — the four attributes the chart reads."""

    def __init__(self, clinic_date, total_visits, zakat, regular):
        self.clinic_date = clinic_date
        self.total_visits = total_visits
        self.zakat_beneficiary_patients = zakat
        self.paying_patients = regular
