"""Tests for the ``seed_initial_content`` management command.

The command turns a freshly migrated database (Wagtail's default *Welcome* page
only) into the real site structure. These tests run against exactly that starting
state — pytest-django's test database has Wagtail's default page + Site from the
core migrations — so they exercise the true production code path.
"""

import pytest
from django.core.management import call_command
from wagtail.models import Page, Site

from apps.core.models import (
    AboutPage,
    CampReportIndexPage,
    ContactPage,
    DonatePage,
    GalleryPage,
    HomePage,
    NewsletterIndexPage,
    OurWorkPage,
    TeamPage,
)

CORE_CHILD_MODELS = (
    AboutPage,
    TeamPage,
    OurWorkPage,
    CampReportIndexPage,
    NewsletterIndexPage,
    GalleryPage,
    ContactPage,
    DonatePage,
)


def _seed(**kwargs):
    call_command("seed_initial_content", **kwargs)


@pytest.mark.django_db
def test_seed_creates_home_and_core_pages():
    """A fresh database gains one HomePage + the core child pages, all live."""
    _seed()

    assert HomePage.objects.count() == 1
    home = HomePage.objects.get()
    for model in CORE_CHILD_MODELS:
        assert model.objects.count() == 1, model.__name__
        page = model.objects.get()
        # Child of the home page, published, and reachable.
        assert page.get_parent().id == home.id
        assert page.live is True


@pytest.mark.django_db
def test_seed_uses_nav_slugs():
    """Child slugs match the hard-coded nav links (/about/, /team/, …)."""
    _seed()
    slugs = {
        AboutPage: "about",
        TeamPage: "team",
        OurWorkPage: "our-work",
        CampReportIndexPage: "camp-reports",
        NewsletterIndexPage: "newsletters",
        GalleryPage: "gallery",
        ContactPage: "contact",
        DonatePage: "donate",
    }
    for model, slug in slugs.items():
        assert model.objects.get().slug == slug


@pytest.mark.django_db
def test_seed_repoints_default_site_at_home():
    """The default Site's root becomes the new HomePage (so children sit at /about/)."""
    _seed()
    site = Site.objects.get(is_default_site=True)
    home = HomePage.objects.get()
    assert site.root_page_id == home.id


@pytest.mark.django_db
def test_seed_is_idempotent():
    """A second run creates nothing new and leaves the tree untouched."""
    _seed()
    home_id = HomePage.objects.get().id
    page_count = Page.objects.count()

    _seed()

    assert HomePage.objects.count() == 1
    assert HomePage.objects.get().id == home_id
    assert Page.objects.count() == page_count
    for model in CORE_CHILD_MODELS:
        assert model.objects.count() == 1, model.__name__


@pytest.mark.django_db
def test_seed_delete_welcome_removes_default_page():
    """``--delete-welcome`` drops Wagtail's leftover default page after repointing."""
    # Wagtail's core migration seeds a default 'home' Welcome page as the site root.
    original_root = Site.objects.get(is_default_site=True).root_page
    assert not isinstance(original_root.specific, HomePage)

    _seed(delete_welcome=True)

    assert not Page.objects.filter(id=original_root.id).exists()
    # The real HomePage is now the site root and survives.
    assert Site.objects.get(is_default_site=True).root_page.specific_class is HomePage


@pytest.mark.django_db
def test_seeded_pages_resolve_over_http(client):
    """After seeding, the core URLs return 200 under the /en/ i18n prefix."""
    _seed()
    for path in (
        "/en/",
        "/en/about/",
        "/en/team/",
        "/en/our-work/",
        "/en/camp-reports/",
        "/en/newsletters/",
        "/en/gallery/",
        "/en/contact/",
        "/en/donate/",
    ):
        assert client.get(path).status_code == 200, path
