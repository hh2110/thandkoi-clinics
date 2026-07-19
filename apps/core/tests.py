"""Smoke tests for the project foundation.

These verify the app boots and its two entry points respond: the Wagtail home
page renders, and the /healthz probe returns 200.
"""

import pytest
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
    """The home page returns 200 and shows its title."""
    response = client.get("/")
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
