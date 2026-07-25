"""The two approved dashboard entry points (Plan 16, task 16.4).

1a — `Open the dashboard →` in the reports index's footfall card head.
1c — a fourth, link tile in the Home impact band.

Both resolve their href through ``ClinicDashboardPage.entry_point_url``
rather than hardcoding ``/en/reports/dashboard/`` (the path is
locale-prefixed, D1), and both omit themselves rather than render a dead
link when there is no live dashboard page.

The last group of tests is D7's whole point: the link tile is opt-in
context on ``stat_band.html``, so the partial's **other** consumer, the
newsletter stat band, must render exactly as it did before this task. That
is asserted here rather than eyeballed.
"""

from __future__ import annotations

import datetime
import re

import pytest
from django.template.loader import render_to_string
from wagtail.models import Site

from apps.core.factories import (
    HomePageFactory,
    NewsletterIndexPageFactory,
    NewsletterPageFactory,
)
from apps.pipeline.factories import DailyAggregateFactory, ReportIndexPageFactory
from apps.pipeline.models import ClinicDashboardPage
from apps.pipeline.report_publishing import _get_or_create_clinic_dashboard

pytestmark = pytest.mark.django_db


@pytest.fixture
def home_page():
    """A site-rooted HomePage — same shape as ``test_clinic_dashboard.py``'s
    fixture of the same name."""
    home = HomePageFactory()
    site = Site.objects.get(is_default_site=True)
    site.root_page = home
    site.save()
    return home


@pytest.fixture
def reports_index(home_page):
    """The reports index, with one recent aggregate so its footfall card —
    the head that carries entry point 1a — actually renders."""
    index = ReportIndexPageFactory(parent=home_page, slug="reports")
    DailyAggregateFactory(
        clinic_date=datetime.date.today() - datetime.timedelta(days=1),
        total_visits=12,
        zakat_beneficiary_patients=5,
        paying_patients=7,
    )
    return index


@pytest.fixture
def dashboard(reports_index):
    """The dashboard page, through the real get-or-create helper (D1)."""
    return _get_or_create_clinic_dashboard()


# --- entry_point_url ---------------------------------------------------------


def test_entry_point_url_is_none_without_a_dashboard_page(reports_index):
    """A database that has never run the D1 data migration links nowhere."""
    assert ClinicDashboardPage.entry_point_url() is None


def test_entry_point_url_is_the_pages_own_locale_prefixed_url(dashboard):
    """Never a hardcoded path — Wagtail owns the URL, prefix included."""
    url = ClinicDashboardPage.entry_point_url()
    assert url == dashboard.url
    assert url.endswith("/reports/dashboard/")


def test_entry_point_url_is_none_when_the_dashboard_is_unpublished(dashboard):
    """Unpublishing is this plan's rollback lever ("unlink the entry points
    — a content edit, no deploy"), so it has to actually unlink them."""
    dashboard.unpublish()

    assert ClinicDashboardPage.entry_point_url() is None


# --- 1a: reports index -------------------------------------------------------


def test_reports_index_links_to_the_dashboard(client, dashboard):
    content = client.get("/en/reports/").content.decode()

    assert "Open the dashboard →" in content
    assert (
        f'<a class="ri-funding-mix__dashboard-link" href="{dashboard.url}">' in content
    )


def test_reports_index_link_sits_in_the_footfall_card_head(client, dashboard):
    """1a's placement is the design decision, so pin it: inside the head,
    after the title — not loose somewhere else on the page."""
    content = client.get("/en/reports/").content.decode()

    head = re.search(
        r'<div class="ri-funding-mix__head">(.*?)</div>', content, re.DOTALL
    )
    assert head is not None
    assert "ri-funding-mix__title" in head.group(1)
    assert "ri-funding-mix__dashboard-link" in head.group(1)


def test_reports_index_omits_the_link_without_a_dashboard_page(client, reports_index):
    content = client.get("/en/reports/").content.decode()

    assert "ri-funding-mix__title" in content  # the card itself still renders
    assert "ri-funding-mix__dashboard-link" not in content
    assert "Open the dashboard" not in content


@pytest.mark.parametrize("path", ["/en/", "/en/reports/"], ids=["home", "reports"])
def test_entry_point_pages_leak_no_template_comment_markers(client, dashboard, path):
    """Caught in the browser, not by a substring assertion: Django's ``{# #}``
    is single-line only, so a multi-line one renders as visible page text.
    Both entry points sit next to an explanatory comment, so both pages are
    checked."""
    content = client.get(path).content.decode()

    assert "{#" not in content
    assert "#}" not in content


# --- 1c: home impact band ----------------------------------------------------


def test_home_impact_band_shows_the_dashboard_tile(client, dashboard):
    content = client.get("/en/").content.decode()

    assert "stat-band--with-link" in content
    assert (
        f'<a class="stat-band__card stat-band__link-card" href="{dashboard.url}">'
        in content
    )
    assert "See the live dashboard" in content
    assert '<span class="stat-band__link-glyph" aria-hidden="true">→</span>' in content


def test_home_impact_band_has_no_tile_without_a_dashboard_page(client, home_page):
    """No dashboard, no tile — and the band is byte-for-byte the three-card
    row it was before 16.4."""
    content = client.get("/en/").content.decode()

    assert "stat-band" in content  # the band itself still renders
    assert "stat-band--with-link" not in content
    assert "stat-band__link-card" not in content
    assert "See the live dashboard" not in content


# --- D7: the partial's other consumer is untouched ---------------------------

#: The band's opening tag with no link context — pinned in full, because
#: D7's promise is about the exact markup other consumers emit, not just
#: about the link being absent from it.
UNLINKED_SECTION_TAG = (
    '<section class="section section--tinted section--banded stat-band">'
)


def test_stat_band_without_link_context_renders_exactly_as_before():
    html = render_to_string(
        "partials/sections/stat_band.html",
        {"heading": "Our impact", "stats": [{"value": "763", "label": "Patients"}]},
    )

    assert UNLINKED_SECTION_TAG in html
    assert "stat-band__link-card" not in html
    assert "<a " not in html


@pytest.mark.parametrize(
    "context",
    [
        {"link_url": "/en/reports/dashboard/"},
        {"link_label": "See the live dashboard"},
    ],
    ids=["url-only", "label-only"],
)
def test_stat_band_needs_both_link_values_to_render_a_tile(context):
    """Half the context renders no tile — never a labelless link or a link
    to nowhere."""
    html = render_to_string(
        "partials/sections/stat_band.html",
        {"stats": [{"value": "763", "label": "Patients"}], **context},
    )

    assert UNLINKED_SECTION_TAG in html
    assert "stat-band__link-card" not in html


def test_newsletter_stat_band_is_unchanged_by_the_opt_in_link(
    client, home_page, dashboard
):
    """The real second consumer, rendered through its own block template
    while a live dashboard page exists — the exact situation D7 is about."""
    index = NewsletterIndexPageFactory(parent=home_page, slug="newsletters")
    NewsletterPageFactory(
        parent=index,
        slug="may-2026",
        title="A new chapter begins",
        issue_date=datetime.date(2026, 6, 1),
        body=[
            (
                "stat_band",
                {
                    "heading": "Our impact, at a glance",
                    "updated": "May–June 2026",
                    "stats": [{"value": "763", "label": "Patients seen"}],
                },
            ),
        ],
    )

    content = client.get("/en/newsletters/may-2026/").content.decode()

    assert '<section class="section section--snug stat-band">' in content
    assert "stat-band--with-link" not in content
    assert "stat-band__link-card" not in content
    assert "See the live dashboard" not in content
