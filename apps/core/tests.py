"""Smoke tests for the project foundation and the Plan 03 design system.

These verify the app boots and its two entry points respond: the Wagtail home
page renders, and the /healthz probe returns 200. The Plan 03 additions below
cover the bilingual routing, RTL layout, brand-styled error pages, and the
anti-FOUC/theme-toggle markup added in that plan.
"""

import re

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse
from wagtail.models import Page, Site

from apps.core.factories import (
    AboutPageFactory,
    ContactPageFactory,
    DonatePageFactory,
    HomePageFactory,
    OurWorkPageFactory,
    ServiceFactory,
    TeamMemberFactory,
    TeamPageFactory,
)
from apps.core.models import ContactBankSettings, HomePage, Service, TeamMember


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


def test_home_title_is_not_doubled(client, home_page):
    """The home <title> shows the site name once, not "X — X".

    The home page's own title *is* the site name, so the shared
    " — The Thandkoi Clinics" suffix must be suppressed — otherwise the
    browser tab and social/WhatsApp preview read it twice.
    """
    content = client.get("/en/", follow=True).content.decode()
    title = re.search(r"<title>(.*?)</title>", content, re.S).group(1).strip()
    assert title == "The Thandkoi Clinics"


def test_inner_page_title_has_site_suffix(client, home_page):
    """A non-home page keeps the " — The Thandkoi Clinics" suffix."""
    AboutPageFactory(parent=home_page, title="About", slug="about")
    content = client.get("/en/about/").content.decode()
    title = re.search(r"<title>(.*?)</title>", content, re.S).group(1).strip()
    assert title == "About — The Thandkoi Clinics"


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


# --- Plan 04: core content pages ---------------------------------------------


def test_home_page_composes_layout_kit_sections(client, home_page):
    """Home renders the 03.5 kit sections from its StreamField body.

    The default factory body is hero + impact-stat band + an unlinked donate
    CTA, so the composed markup (hero, stat-band) is present — the Plan 04
    "compose a page from the kit" path, exercised through the real chrome.
    """
    content = client.get("/en/").content.decode()
    assert "hero" in content
    assert "stat-band" in content
    assert "467+" in content  # a supplied impact figure renders verbatim


@pytest.mark.parametrize(
    ("url", "lang", "direction"),
    [("/en/", "en", "ltr"), ("/ur/", "ur", "rtl")],
)
def test_home_renders_in_both_languages(client, home_page, url, lang, direction):
    """The composed Home page renders correctly in both languages / directions."""
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert f'<html lang="{lang}" dir="{direction}">' in content
    assert "hero" in content


def test_home_donate_cta_and_report_teaser_hidden_when_unset(client, home_page):
    """With no donate link and no report, neither section renders (hidden, not broken).

    The factory body's donate CTA has no cta_page/cta_url, and there is no report
    content type yet, so the CTA band and the feature-split teaser are both
    absent — no dead "Donate" button, no empty placeholder box.
    """
    content = client.get("/en/").content.decode()
    assert "cta-band" not in content
    assert "feature-split" not in content


def test_donate_cta_block_renders_when_linked():
    """When the donate CTA points somewhere, the band renders (regression guard)."""
    from wagtail.blocks import StreamValue

    from apps.core.models import HomePage as _HP

    body = _HP().body.stream_block
    value = StreamValue(
        body,
        [
            (
                "donate_cta",
                {
                    "heading": "Give",
                    "cta_label": "Donate now",
                    "cta_url": "https://example.org/donate",
                },
            )
        ],
    )
    html = value.render_as_block()
    assert "cta-band" in html
    assert "https://example.org/donate" in html


def test_hero_cta_target_guard_and_donate_only_amber(home_page):
    """The hero primary CTA is guarded on a target and amber is Donate-only.

    (a) A label with no target is not rendered (no dead "#" link); (b) a
    non-donate CTA with a real target uses button--primary, never the amber
    button--donate (brand-guidelines.md §7); (c) a CTA explicitly marked as the
    donate ask uses button--donate.
    """
    from wagtail.blocks import StreamValue

    from apps.core.models import HomePage as _HP

    target = AboutPageFactory(parent=home_page, slug="hero-target")
    body = _HP().body.stream_block

    # (a) Label but no target → the button is suppressed entirely.
    ghost = StreamValue(
        body, [("hero", {"headline": "Hi", "primary_cta_label": "Ghost link"})]
    )
    ghost_html = ghost.render_as_block()
    assert "Ghost link" not in ghost_html

    # (b) A non-donate CTA with a real target → button--primary, not amber.
    plain = StreamValue(
        body,
        [
            (
                "hero",
                {
                    "headline": "Hi",
                    "primary_cta_label": "Learn more",
                    "primary_cta_page": target,
                    "primary_cta_donate": False,
                },
            )
        ],
    )
    plain_html = plain.render_as_block()
    assert "Learn more" in plain_html
    assert "button--primary" in plain_html
    assert "button--donate" not in plain_html

    # (c) The donate ask, explicitly marked → the amber button.
    donate = StreamValue(
        body,
        [
            (
                "hero",
                {
                    "headline": "Hi",
                    "primary_cta_label": "Give Zakat / Sadaqa",
                    "primary_cta_page": target,
                    "primary_cta_donate": True,
                },
            )
        ],
    )
    donate_html = donate.render_as_block()
    assert "button--donate" in donate_html


@pytest.mark.parametrize(
    ("factory", "slug", "template"),
    [
        (AboutPageFactory, "about", "core/about_page.html"),
        (TeamPageFactory, "team", "core/team_page.html"),
        (OurWorkPageFactory, "our-work", "core/our_work_page.html"),
        (ContactPageFactory, "contact", "core/contact_page.html"),
        (DonatePageFactory, "donate", "core/donate_page.html"),
    ],
)
def test_core_pages_render_with_correct_template(
    client, home_page, factory, slug, template
):
    """Each core page is creatable under Home, returns 200, uses its template."""
    factory(parent=home_page, slug=slug)
    response = client.get(f"/en/{slug}/")
    assert response.status_code == 200
    assert template in [t.name for t in response.templates]


def test_core_pages_render_in_urdu_with_rtl(client, home_page):
    """A representative content page renders lang="ur" dir="rtl"."""
    AboutPageFactory(parent=home_page, slug="about")
    content = client.get("/ur/about/").content.decode()
    assert '<html lang="ur" dir="rtl">' in content


def test_team_page_groups_members_and_shows_placeholder(client, home_page):
    """The team page groups by category and shows the placeholder for no photo."""
    team = TeamPageFactory(parent=home_page, slug="team")
    TeamMemberFactory(page=team, name="Dr Doctor One", category=TeamMember.DOCTORS)
    TeamMemberFactory(page=team, name="Ataullah Khan", category=TeamMember.STAFF)
    content = client.get("/en/team/").content.decode()
    assert "Doctors" in content
    assert "Committee" in content  # the "Staff & Committee" group heading
    assert "Dr Doctor One" in content
    assert "Ataullah Khan" in content
    # No photos set → the intentional placeholder stands in for each portrait.
    assert "media-placeholder" in content


def test_our_work_planned_service_shows_tag(client, home_page):
    """A Planned service renders the coming-soon tag; an Active one does not."""
    work = OurWorkPageFactory(parent=home_page, slug="our-work")
    ServiceFactory(page=work, name="Telemedicine", status=Service.ACTIVE)
    ServiceFactory(page=work, name="Laboratory & Pharmacy", status=Service.PLANNED)
    content = client.get("/en/our-work/").content.decode()
    assert "Telemedicine" in content
    assert "Laboratory &amp; Pharmacy" in content
    assert "card__tag" in content  # the Planned tag is present


def test_contact_page_and_footer_reflect_the_setting(client, home_page):
    """Editing the Contact & Bank Details setting updates the Contact page + footer.

    One shared singleton drives both surfaces, so a single edit is visible in the
    Contact page body and the site footer with no code change or redeploy.
    """
    ContactPageFactory(parent=home_page, slug="contact")
    site = Site.objects.get(is_default_site=True)
    contact = ContactBankSettings.for_site(site)
    contact.email = "info.thandkoiclinics@example.org"
    contact.phone = "+92 344 4111235"
    contact.bank_account_title = "The Thandkoi Clinics"
    contact.bank_iban = "PK00EXMP0000000000000000"
    contact.save()

    page = client.get("/en/contact/").content.decode()
    assert "info.thandkoiclinics@example.org" in page
    assert "+92 344 4111235" in page
    assert "PK00EXMP0000000000000000" in page

    # The same values appear in the footer (rendered on every page).
    home = client.get("/en/").content.decode()
    assert "info.thandkoiclinics@example.org" in home
    assert "+92 344 4111235" in home


def test_footer_shows_placeholder_when_setting_empty(client, home_page):
    """With the setting unset, the footer shows its coming-soon placeholders."""
    content = client.get("/en/").content.decode()
    assert "Contact details coming soon." in content
    assert "Bank details coming soon." in content


# --- Plan 05: donate placeholder ---------------------------------------------


def test_donate_page_shows_distinct_zakat_and_sadaqa_sections(client, home_page):
    """The Zakat and Sadaqa sections render with their own headings and copy.

    Maintainer decision (Plan 05): one page, but the reader can clearly tell
    which form of giving is which — never blended into a single message.
    """
    DonatePageFactory(
        parent=home_page,
        slug="donate",
        zakat_description="<p>Specific Zakat eligibility rules.</p>",
        sadaqa_description="<p>General voluntary giving, any amount.</p>",
    )
    content = client.get("/en/donate/").content.decode()
    assert "Zakat" in content
    assert "Sadaqa" in content
    assert "Specific Zakat eligibility rules." in content
    assert "General voluntary giving, any amount." in content


def test_donate_page_reflects_the_bank_details_setting(client, home_page):
    """Bank details on the Donate page match the shared Contact & Bank setting.

    Guards against the field ever being duplicated/hardcoded on DonatePage
    later — the setting is the one source of truth (Plan 05 decision).
    """
    DonatePageFactory(parent=home_page, slug="donate")
    site = Site.objects.get(is_default_site=True)
    contact = ContactBankSettings.for_site(site)
    contact.bank_account_title = "The Thandkoi Clinics"
    contact.bank_name = "Example Bank"
    contact.bank_iban = "PK00EXMP0000000000000000"
    contact.bank_account_number = "0000-1111-2222"
    contact.bank_branch = "Swabi Branch"
    contact.save()

    content = client.get("/en/donate/").content.decode()
    assert "The Thandkoi Clinics" in content
    assert "Example Bank" in content
    assert "PK00EXMP0000000000000000" in content
    assert "0000-1111-2222" in content
    assert "Swabi Branch" in content


def test_donate_page_shows_placeholder_when_bank_details_unset(client, home_page):
    """With no bank details entered yet, the page shows the coming-soon line."""
    DonatePageFactory(parent=home_page, slug="donate")
    content = client.get("/en/donate/").content.decode()
    assert "Bank details coming soon." in content


def test_donate_page_in_kind_giving_links_to_contact_channels(client, home_page):
    """In-kind giving copy renders alongside tel:/mailto: links from the setting."""
    DonatePageFactory(
        parent=home_page,
        slug="donate",
        in_kind_giving="<p>Medicine, equipment, and volunteering.</p>",
    )
    site = Site.objects.get(is_default_site=True)
    contact = ContactBankSettings.for_site(site)
    contact.phone = "+92 344 4111235"
    contact.email = "info.thandkoiclinics@example.org"
    contact.save()

    content = client.get("/en/donate/").content.decode()
    assert "Medicine, equipment, and volunteering." in content
    # tel: strips spaces (a well-formed URI); the visible text keeps them.
    assert 'href="tel:+923444111235"' in content
    assert "+92 344 4111235" in content
    assert 'href="mailto:info.thandkoiclinics@example.org"' in content


def test_donate_page_cta_hidden_without_a_contact_page(db):
    """No dead "#" link: the closing CTA is omitted until a Contact page exists.

    Mirrors the hero/donate-band guard (Plan 04) that never links to nowhere.
    """
    donate = DonatePageFactory()
    from django.test import RequestFactory

    request = RequestFactory().get("/donate/")
    context = donate.get_context(request)
    assert context["contact_page_url"] is None


def test_donate_page_cta_links_to_contact_page_when_it_exists(client, home_page):
    """Once a Contact page exists, the closing CTA links to it."""
    DonatePageFactory(parent=home_page, slug="donate")
    ContactPageFactory(parent=home_page, slug="contact")
    content = client.get("/en/donate/").content.decode()
    assert "cta-band" in content
    assert 'href="/en/contact/"' in content
    assert "button--donate" in content


def test_consent_block_requires_confirmation(db):
    """The reusable consent image block refuses an image without ticked consent.

    Establishes the brand-guidelines.md §5 convention Plan 06 reuses: an
    identifiable-person photo cannot be saved unless consent is confirmed.
    """
    from wagtail.blocks import StructBlockValidationError
    from wagtail.images.tests.utils import Image, get_test_image_file

    from apps.core.blocks import ConsentedImageBlock

    image = Image.objects.create(title="A person", file=get_test_image_file())
    block = ConsentedImageBlock()
    with pytest.raises(StructBlockValidationError):
        block.clean(block.to_python({"image": image.pk, "consent_confirmed": False}))
    # With consent ticked it validates cleanly.
    cleaned = block.clean(
        block.to_python({"image": image.pk, "consent_confirmed": True})
    )
    assert cleaned["consent_confirmed"] is True
