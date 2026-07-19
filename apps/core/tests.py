"""Smoke tests for the project foundation and the Plan 03 design system.

These verify the app boots and its two entry points respond: the Wagtail home
page renders, and the /healthz probe returns 200. The Plan 03 additions below
cover the bilingual routing, RTL layout, brand-styled error pages, and the
anti-FOUC/theme-toggle markup added in that plan.
"""

import pytest
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse
from wagtail.models import Page, Site

from apps.core.factories import HomePageFactory
from apps.core.models import HomePage


@pytest.fixture
def home_page(db):
    """A HomePage set as the default site root, replacing Wagtail's welcome page."""
    root = Page.get_first_root_node()
    home = HomePageFactory(
        parent=root, title="The Thandkoi Clinics", slug="thandkoi-home"
    )
    site = Site.objects.get(is_default_site=True)
    # Repoint the default site at our HomePage; drop Wagtail's welcome page.
    old_root = site.root_page
    site.root_page = home
    site.save()
    if old_root and old_root.pk != home.pk:
        old_root.delete()
    return home


def test_home_page_renders(client, home_page):
    """The home page returns 200 and shows its title.

    Plan 03 wraps the public page tree in ``i18n_patterns``, so the
    unprefixed root now 302s to the detected-language URL (``/en/`` by
    default) before it 200s — ``follow=True`` follows that redirect so this
    test still asserts exactly what it always has: a 200 response containing
    the page title.
    """
    response = client.get("/", follow=True)
    assert response.status_code == 200
    assert b"The Thandkoi Clinics" in response.content


def test_healthz_returns_200(client, db):
    """The health probe returns 200 with an ok status."""
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_homepage_factory_creates_page_in_tree(db):
    """The factory produces a real, tree-placed HomePage."""
    page = HomePageFactory()
    assert isinstance(page, HomePage)
    assert page.pk is not None
    assert page.depth >= 2  # under the tree root


# --- Plan 03: bilingual routing & RTL --------------------------------------


def test_home_page_renders_at_en_with_correct_lang_dir(client, home_page):
    """The English URL prefix renders lang="en" dir="ltr"."""
    response = client.get("/en/")
    assert response.status_code == 200
    content = response.content.decode()
    assert '<html lang="en" dir="ltr">' in content
    assert "The Thandkoi Clinics" in content


def test_home_page_renders_at_ur_with_correct_lang_dir(client, home_page):
    """The Urdu URL prefix renders lang="ur" dir="rtl" (mirrored layout)."""
    response = client.get("/ur/")
    assert response.status_code == 200
    content = response.content.decode()
    assert '<html lang="ur" dir="rtl">' in content


def test_root_redirects_to_a_language_prefix(client, home_page):
    """Visiting the bare "/" redirects to a language-prefixed URL."""
    response = client.get("/")
    assert response.status_code == 302
    assert response.url.startswith("/en/") or response.url.startswith("/ur/")


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_language_switcher_round_trips_to_the_same_page(client, db):
    """Switching language on a page returns the equivalent path, not "/".

    HomePage (Plan 01) is the site root and doesn't allow child pages yet
    (Plan 04 adds real content pages), so there's no second real page to
    navigate between languages on. The language switcher works purely off
    ``request.path`` string-slicing though, so a placeholder nav path (which
    404s, by design — see templates/partials/nav.html) still exercises the
    real round-trip logic: it should point at "/ur/about/", not "/ur/".
    """
    response = client.get("/en/about/")
    assert response.status_code == 404
    content = response.content.decode()
    assert 'href="/ur/about/"' in content


# --- Plan 03: error pages ----------------------------------------------------


@override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
def test_404_page_is_branded(client, db):
    """A missing page renders our styled 404.html, not Django's debug page."""
    response = client.get("/en/this-page-does-not-exist/")
    assert response.status_code == 404
    content = response.content.decode()
    assert "error-page" in content
    assert "404" in content
    # Not Django's built-in technical 404 debug page.
    assert "Page not found at" not in content
    assert "Traceback" not in content


def test_500_page_is_branded_and_has_no_stack_trace():
    """500.html renders standalone (Django gives it no request context) and
    degrades gracefully rather than raising or showing internals."""
    content = render_to_string("500.html")
    assert "error-page" in content
    assert "500" in content
    assert "Traceback" not in content
    assert "{% " not in content  # no leaked/unrendered template tags
    assert "{# " not in content  # no leaked/unrendered comments


# --- Plan 03: anti-FOUC + theme toggle ---------------------------------------


def test_anti_fouc_script_and_theme_toggle_markup_present(client, home_page):
    """The inline anti-FOUC script and the theme-toggle button both render."""
    response = client.get("/en/")
    content = response.content.decode()
    assert "thandkoi-theme" in content  # anti-FOUC localStorage read
    assert "data-theme-toggle" in content
    assert 'aria-pressed="false"' in content


def test_no_third_party_font_or_cdn_requests(client, home_page):
    """No reference to a font CDN — fonts are genuinely self-hosted."""
    response = client.get("/en/")
    content = response.content.decode()
    assert "fonts.googleapis.com" not in content
    assert "fonts.gstatic.com" not in content
