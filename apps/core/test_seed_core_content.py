"""Tests for the ``seed_core_content`` management command.

Verifies the command populates the core pages from the org profile as
**unpublished drafts** by default (live pages stay empty until a human
publishes), creates the missing Donate page, stages the team roster and
services into the draft, fills the bank setting non-destructively, and that
``--publish`` makes everything live.
"""

import pytest
from django.core.management import call_command
from wagtail.models import Site

from apps.core.management.commands.seed_core_content import (
    COMMITTEE,
    DOCTORS,
    SERVICES_ACTIVE,
    SERVICES_PLANNED,
)
from apps.core.models import (
    AboutPage,
    ContactBankSettings,
    DonatePage,
    HomePage,
    OurWorkPage,
    Service,
    TeamPage,
)

TEAM_TOTAL = len(DOCTORS) + len(COMMITTEE)
SERVICE_TOTAL = len(SERVICES_ACTIVE) + len(SERVICES_PLANNED)


def _seed_tree():
    """Build the page structure the content command populates."""
    call_command("seed_initial_content")


@pytest.mark.django_db
def test_content_lands_in_draft_not_live():
    _seed_tree()
    call_command("seed_core_content")

    about = AboutPage.objects.get()
    # The live page is untouched (still empty), but a draft now carries content.
    assert about.vision == ""
    assert about.has_unpublished_changes
    draft = about.get_latest_revision_as_object()
    assert "healthy community" in draft.vision
    assert "cost-effective" in draft.mission

    # Home body: empty live, three blocks in the draft.
    home = HomePage.objects.get()
    assert len(home.body) == 0
    assert len(home.get_latest_revision_as_object().body) == 3


@pytest.mark.django_db
def test_team_and_services_staged_into_draft_only():
    _seed_tree()
    call_command("seed_core_content")

    team = TeamPage.objects.get()
    assert team.members.count() == 0  # nothing live yet
    draft_members = list(team.get_latest_revision_as_object().members.all())
    assert len(draft_members) == TEAM_TOTAL

    work = OurWorkPage.objects.get()
    assert work.services.count() == 0
    draft_services = list(work.get_latest_revision_as_object().services.all())
    assert len(draft_services) == SERVICE_TOTAL
    planned = [s for s in draft_services if s.status == Service.PLANNED]
    assert len(planned) == len(SERVICES_PLANNED)


@pytest.mark.django_db
def test_donate_drafted_when_page_already_exists():
    # seed_initial_content already creates a live, empty Donate page.
    _seed_tree()
    assert DonatePage.objects.get().live is True

    call_command("seed_core_content")

    donate = DonatePage.objects.get()
    assert donate.intro == ""  # live still empty
    assert donate.has_unpublished_changes
    draft = donate.get_latest_revision_as_object()
    assert "universal health coverage" in draft.intro
    assert draft.zakat_description and draft.sadaqa_description


@pytest.mark.django_db
def test_donate_page_created_as_draft_when_missing():
    # Mirrors production seeded before Plan 05 landed: no Donate page yet.
    _seed_tree()
    DonatePage.objects.get().delete()
    assert not DonatePage.objects.exists()

    call_command("seed_core_content")

    donate = DonatePage.objects.get()
    assert donate.live is False  # created draft-only, 404 on the frontend
    assert donate.slug == "donate"
    assert "universal health coverage" in donate.get_latest_revision_as_object().intro


@pytest.mark.django_db
def test_publish_flag_makes_everything_live():
    _seed_tree()
    call_command("seed_core_content", publish=True)

    assert "healthy community" in AboutPage.objects.get().vision
    assert DonatePage.objects.get().live is True
    assert TeamPage.objects.get().members.count() == TEAM_TOTAL
    assert OurWorkPage.objects.get().services.count() == SERVICE_TOTAL


@pytest.mark.django_db
def test_bank_setting_filled_but_never_overwrites_a_human_edit():
    _seed_tree()
    site = Site.objects.get(is_default_site=True)

    call_command("seed_core_content")
    setting = ContactBankSettings.for_site(site)
    assert setting.bank_iban == "PK83SONE0510930001644218"
    assert setting.bank_account_title == "The Thandkoi Clinics"
    assert setting.phone == "+92 344 4111235"
    assert setting.email == "info.thandkoiclinics@gmail.com"

    # A human corrects a value; re-running must not clobber it.
    setting.bank_iban = "PK00MANUAL0000000000000000"
    setting.save()
    call_command("seed_core_content")
    assert ContactBankSettings.for_site(site).bank_iban == "PK00MANUAL0000000000000000"


@pytest.mark.django_db
def test_published_core_pages_resolve_over_http(client):
    _seed_tree()
    call_command("seed_core_content", publish=True)
    for path in (
        "/en/about/",
        "/en/team/",
        "/en/our-work/",
        "/en/contact/",
        "/en/donate/",
    ):
        assert client.get(path).status_code == 200, path
