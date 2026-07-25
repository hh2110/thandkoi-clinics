"""The primary nav drawer (Plan 18 Track A).

Three fixes came out of one piece of feedback — the open mobile menu read as
"you are in Donate" whatever page you were on — and each leaves a different
kind of trace:

* the current-page marker's *colour* is a token swap, checked in
  ``tokens.css`` rather than in rendered HTML (a stylesheet assertion, but a
  cheap one: the whole bug was that a token which doesn't flip per theme was
  used on a surface that does, and nothing but a test stops that recurring);
* Donate's *placement* is markup, and is what these tests mostly pin;
* ``aria-current`` itself predates this plan (Plan 15 D4) and had no test —
  it gets one here, because Track A's whole point is making that attribute
  visible, and a marker on the wrong link is worse than none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from wagtail.models import Page, Site

from apps.core.factories import (
    AboutPageFactory,
    DonatePageFactory,
    HomePageFactory,
    TeamPageFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def home_page(db):
    """A HomePage set as the default site root — same shape as ``tests.py``'s
    fixture of the same name, kept local so that file is untouched."""
    root = Page.get_first_root_node()
    home = HomePageFactory(
        parent=root, title="The Thandkoi Clinics", slug="thandkoi-home"
    )
    site = Site.objects.get(is_default_site=True)
    old_root = site.root_page
    site.root_page = home
    site.save()
    if old_root and old_root.pk != home.pk:
        old_root.delete()
    return home


def header_of(client, path: str) -> str:
    """The rendered <header> only, so a "Donate" elsewhere on the page (the
    hero CTA, the footer) can't satisfy a header assertion by accident."""
    content = client.get(path).content.decode()
    return content.split("<header", 1)[1].split("</header>", 1)[0]


def nav_list_of(header: str) -> str:
    """Just the ``<ul class="primary-nav__list">`` — the list of *pages*.

    Sliced between the list's opening tag and the CTA block that now follows
    it rather than by matching ``</ul>``: the list contains a nested ``<ul>``
    (the "More" flyout), so any regex closing on the first ``</ul>`` would
    silently return a fragment ending mid-list — and a fragment satisfies a
    "Donate is not in here" assertion for the wrong reason. Both markers are
    required, so removing either fails loudly instead of narrowing the slice.
    """
    start = header.index('<ul class="primary-nav__list">')
    end = header.index('<div class="primary-nav__cta">')
    assert start < end
    return header[start:end]


# --- Fix 2: Donate is in the header, but not among the pages ---------------


def test_donate_is_in_the_header_but_outside_the_page_list(client, home_page):
    """The fix that prompted the handoff.

    As the list's last ``<li>`` the amber Donate button read as the selected
    page. It keeps its fill, its amber and its place in the header — it just
    stops being a row among About / Our Work / Reports.
    """
    DonatePageFactory(parent=home_page, slug="donate")

    header = header_of(client, "/en/")

    assert 'class="button button--donate primary-nav__cta-button"' in header
    assert "/en/donate/" in header
    # ...and none of that is inside the list of pages.
    nav_list = nav_list_of(header)
    assert "button--donate" not in nav_list
    assert "/en/donate/" not in nav_list


def test_the_donate_block_carries_its_supporting_sentence(client, home_page):
    """Out of the list, Donate has room for the ask it never had as a row."""
    DonatePageFactory(parent=home_page, slug="donate")

    header = header_of(client, "/en/")

    assert 'class="primary-nav__cta"' in header
    assert "Zakat and Sadaqa keep care free for those who need it most." in header


# --- Fix 1: the current-page marker -----------------------------------------


def test_aria_current_marks_the_page_you_are_actually_on(client, home_page):
    """Only one link is marked, and it is the one you asked for."""
    AboutPageFactory(parent=home_page, slug="about")

    header = header_of(client, "/en/about/")

    marked = re.findall(r'href="([^"]+)"[^>]*aria-current="page"', header)
    assert marked == ["/en/about/"]


def test_aria_current_reaches_the_more_dropdown_too(client, home_page):
    """Team / Gallery / Contact live in the "More" flyout, not the top row.

    Plan 18 D2: they need no second CSS rule because ``.nav-dropdown`` is an
    ``<li>`` *inside* ``.primary-nav__list``, so the marker's descendant
    selector already reaches them. This test is what keeps that structural
    assumption honest — move the dropdown out of the list and it fails.
    """
    TeamPageFactory(parent=home_page, slug="team")

    header = header_of(client, "/en/team/")

    marked = re.findall(r'href="([^"]+)"[^>]*aria-current="page"', header)
    assert marked == ["/en/team/"]
    dropdown = re.search(
        r'<ul class="nav-dropdown__menu">.*?</ul>', header, re.S
    ).group()
    assert 'aria-current="page"' in dropdown


def test_home_is_not_marked_current_from_another_page(client, home_page):
    """The negative control for the two above: an unmarked nav is possible,
    so a passing assertion there means something."""
    AboutPageFactory(parent=home_page, slug="about")

    header = header_of(client, "/en/about/")

    assert not re.search(r'href="/en/"[^>]*aria-current', header)


# --- Fixes 1 and 3: the tokens behind them ---------------------------------


def _tokens_css() -> str:
    return (Path(settings.BASE_DIR) / "static" / "css" / "tokens.css").read_text()


def _dark_blocks(css: str) -> list[str]:
    """Every block that defines the dark palette.

    ``tokens.css`` carries it three times over — the ``prefers-color-scheme``
    media query and two ``[data-theme]`` blocks — and a token added to only
    some of them is a bug that shows up for exactly the visitors who picked
    a theme by hand. Splitting on the light ``[data-theme="light"]`` block
    keeps that out of the sample.
    """
    dark = re.split(r':root\[data-theme="light"\]', css)[0]
    return [
        block
        for block in re.split(
            r"(?=@media \(prefers-color-scheme: dark\)|:root\[)", dark
        )
        if "--color-donate-bg: var(--color-amber-on-dark)" in block
    ]


def test_nav_current_token_flips_per_theme():
    """The bug: the marker was ``--color-brand``, which is #086c7e in *both*
    themes — 1.9:1 on the dark drawer. The fix only works if the new token is
    defined in every dark block, not just the media query."""
    css = _tokens_css()
    dark_blocks = _dark_blocks(css)

    assert len(dark_blocks) == 2, "expected the media query + [data-theme=dark]"
    for block in dark_blocks:
        assert "--color-nav-current: var(--color-pale-aqua);" in block
    assert "--color-nav-current: var(--color-brand);" in css


def test_donate_label_is_dark_ink_on_amber_in_both_themes():
    """Declared once, as a literal, and never re-declared per theme.

    ``var(--color-ink)`` flips to near-white in dark mode, which put pale text
    on the amber fill. Declaring it per-theme is what let the two drift apart
    in the first place, so the guard is structural: exactly one declaration,
    in ``:root`` (Plan 18 D3).
    """
    css = _tokens_css()

    assert css.count("--color-donate-text:") == 1
    assert "--color-donate-text: #0e2025;" in css


def test_button_labels_outrank_the_themed_anchor_rules():
    """The bug behind both colour fixes (Plan 18 D10).

    ``:root[data-theme="dark"] a`` is (0,2,1) and a lone ``.button--donate``
    is (0,1,0), so for anyone who had picked a theme by hand the themed link
    colour won and *every* filled button rendered pale aqua on its own fill.
    The fix excludes button-styled anchors from those rules via
    ``:not(:where(.button))`` — ``:where()`` so the rules keep the exact
    specificity they had.

    Asserted on the stylesheet because the alternative is a headless browser
    this suite does not have. It is a narrow guard, but the failure it pins
    is invisible to every other kind of test here: the markup is unchanged
    and the token is correct — only the computed colour is wrong.
    """
    css = (Path(settings.BASE_DIR) / "static" / "css" / "base.css").read_text()
    # Comments carry example selectors; strip them before parsing rules.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    # Only rules that set `color` matter — the focus-outline rule deliberately
    # does match buttons, and should keep doing so.
    colour_selectors = [
        selector.strip()
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if re.search(r"(^|;)\s*color\s*:", body)
    ]
    bare_anchor_rules = [
        selector
        for selector in colour_selectors
        # a bare `a` type selector, i.e. not `a.something` / `.x a.button`
        if re.search(r"(^|[\s>+~])a(?![\w-])(?!\s*\.)", selector)
    ]
    assert bare_anchor_rules, "expected base.css to still colour bare anchors"
    for selector in bare_anchor_rules:
        assert ":not(:where(.button))" in selector, (
            f"{selector!r} colours anchors without excluding button-styled "
            "ones; it will silently outrank .button--donate/.button--primary"
        )
