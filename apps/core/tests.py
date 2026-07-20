"""Smoke tests for the project foundation and the Plan 03 design system.

These verify the app boots and its two entry points respond: the Wagtail home
page renders, and the /healthz probe returns 200. The Plan 03 additions below
cover the bilingual routing, RTL layout, brand-styled error pages, and the
anti-FOUC/theme-toggle markup added in that plan.
"""

import re
from contextlib import contextmanager
from importlib import reload
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import clear_url_caches, reverse
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


# --- Plan 03.5: page-body layout kit -----------------------------------------

# (template, minimal context, a substring the render must contain). The
# context is intentionally minimal — sections are driven entirely by block data
# (Plan 04 wires the real values), so each must degrade to its empty/placeholder
# state rather than raise when fields are unset. The marker proves the render
# actually produced the section's own markup, not just a non-None string.
SECTION_PARTIAL_CASES = [
    ("partials/sections/hero.html", {"title": "Care for all"}, "Care for all"),
    ("partials/sections/stat_band.html", {}, "stat-band"),
    ("partials/sections/card_grid.html", {}, "card-grid"),
    ("partials/sections/feature_split.html", {}, "feature-split"),
    ("partials/sections/cta_band.html", {}, "cta-band"),
    ("partials/sections/media_grid.html", {}, "media-grid"),
    ("partials/sections/section_header.html", {"heading": "Our work"}, "Our work"),
    ("partials/sections/_media_placeholder.html", {}, "media-placeholder"),
    ("partials/sections/_card.html", {"card": {"title": "OPD clinic"}}, "OPD clinic"),
]


@pytest.mark.parametrize(("template_name", "context", "marker"), SECTION_PARTIAL_CASES)
def test_section_partial_renders(template_name, context, marker):
    """Every section partial renders to a string containing its own markup.

    Sections are driven entirely by context/block data, so each must render
    (degrading to its empty/placeholder state where fields are unset) — the
    "renders correctly with fields unset" contract Plan 04 depends on.
    """
    html = render_to_string(template_name, context)
    assert isinstance(html, str)
    assert marker in html


def test_stat_band_shows_empty_state_when_no_stats():
    """With no stats the band shows its coming-soon line, not an empty grid."""
    html = render_to_string("partials/sections/stat_band.html", {})
    assert "stat-band__empty" in html


def test_stat_band_renders_supplied_numbers_only():
    """Numbers are template inputs — the band shows exactly what it's given."""
    html = render_to_string(
        "partials/sections/stat_band.html",
        {"stats": [{"value": "128", "label": "patients seen"}]},
    )
    assert "128" in html
    assert "patients seen" in html
    assert 'class="stat__value"' in html


def test_media_placeholder_shows_when_image_absent():
    """A media grid with imageless items renders the intentional placeholder."""
    html = render_to_string(
        "partials/sections/media_grid.html",
        {"items": [{"caption": "clinic photo"}]},
    )
    assert "media-placeholder" in html
    assert 'role="img"' in html
    assert "clinic photo" in html


def test_media_grid_uses_real_image_when_present():
    """When an image is set, the grid renders it instead of the placeholder."""
    html = render_to_string(
        "partials/sections/media_grid.html",
        {"items": [{"image": "/media/x.jpg", "alt": "A clinic day"}]},
    )
    assert "/media/x.jpg" in html
    assert 'alt="A clinic day"' in html
    assert "media-placeholder" not in html


def test_layout_css_linked_after_components_in_base(client, home_page):
    """base.html loads layout.css, and it comes after components.css."""
    content = client.get("/en/").content.decode()
    assert "css/layout.css" in content
    assert content.index("css/components.css") < content.index("css/layout.css")


def test_layout_css_uses_tokens_only_no_hardcoded_colours():
    """layout.css reads only tokens — no literal hex/rgb colours.

    Enforces the acceptance criterion "no new hard-coded colours": a token
    change must reflow the whole kit and both themes come for free. Translucent
    tints are derived with color-mix() from a token, so no rgba()/hex appears.
    """
    css = (settings.BASE_DIR / "static" / "css" / "layout.css").read_text()
    # Strip block comments so the explanatory prose (which mentions rgba) and
    # any hex in comments don't trip the check.
    css_no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    assert "rgba(" not in css_no_comments
    assert "rgb(" not in css_no_comments
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css_no_comments)
    assert "var(--color-" in css_no_comments


def test_styleguide_icons_colour_via_style_declaration_not_presentation_attr():
    """Icon colours resolve — set via a `style` declaration, not fill=/stroke=.

    A CSS custom property only resolves inside a CSS declaration; as a raw SVG
    presentation attribute (fill="var(--color-coral)") it renders black/none.
    Assert the tokened colour lives in a `style` attribute and that no tokened
    presentation attribute remains, so the three service-card icons actually
    show their intended coral/teal.
    """
    from apps.core.views import _ICON_CIRCLE, _ICON_CROSS, _ICON_DIAMOND

    assert 'style="fill:var(--color-coral)"' in _ICON_CROSS
    assert 'style="fill:none;stroke:var(--color-brand)"' in _ICON_CIRCLE
    assert 'style="fill:none;stroke:var(--color-brand)"' in _ICON_DIAMOND
    for icon in (_ICON_CROSS, _ICON_CIRCLE, _ICON_DIAMOND):
        assert 'fill="var(' not in icon
        assert 'stroke="var(' not in icon


@contextmanager
def _debug_urls():
    """Register the DEBUG-only styleguide route for the duration of a test.

    ``config/urls.py`` registers the throwaway styleguide route only under
    ``settings.DEBUG``, evaluated once at urlconf import. pytest-django runs the
    suite with ``DEBUG=False`` (its ``django_debug_mode`` default), so the route
    is absent by default and the URL would 404. This flips DEBUG on and rebuilds
    the urlconf so the gated route is exercised for real, then restores the
    DEBUG=False urlconf afterwards so no other test is affected.
    """
    import config.urls

    override = override_settings(DEBUG=True)
    override.enable()
    clear_url_caches()
    reload(config.urls)
    try:
        yield
    finally:
        override.disable()
        clear_url_caches()
        reload(config.urls)


@pytest.mark.parametrize(
    ("url", "lang", "direction"),
    [("/en/styleguide/", "en", "ltr"), ("/ur/styleguide/", "ur", "rtl")],
)
def test_styleguide_composes_sections_in_both_languages(
    client, db, url, lang, direction
):
    """A page composed of the section partials returns 200 with correct lang/dir.

    Exercises the whole kit through the real bilingual/RTL chrome in both
    languages — the Plan 04 "compose a page from the kit" path — via the
    DEBUG-gated styleguide route.
    """
    with _debug_urls():
        response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert f'<html lang="{lang}" dir="{direction}">' in content
    # A representative sampling of the composed sections is present.
    assert "hero" in content
    assert "stat-band" in content
    assert "card-grid" in content
    assert "feature-split" in content
    assert "cta-band" in content
    assert "media-grid" in content


def test_styleguide_route_absent_without_debug(client, db):
    """The styleguide route is DEBUG-gated — absent in production (DEBUG off).

    pytest-django runs with DEBUG=False, matching production, so the route must
    not resolve; it 404s through the Wagtail catch-all like any unknown path.
    """
    response = client.get("/en/styleguide/")
    assert response.status_code == 404


def test_styleguide_template_file_is_present():
    """The throwaway styleguide template exists where the view expects it."""
    template = (
        Path(settings.BASE_DIR)
        / "apps"
        / "core"
        / "templates"
        / "core"
        / "styleguide.html"
    )
    assert template.exists()
