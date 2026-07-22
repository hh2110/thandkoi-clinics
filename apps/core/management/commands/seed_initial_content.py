"""Seed the initial Wagtail page tree for a fresh (production) database.

A newly migrated database has only Wagtail's default *Welcome* page, so the
public site 404s on every real URL. This command idempotently creates the
site's page structure — a :class:`~apps.core.models.HomePage` as the site root
plus the core child pages (About, Team, Our Work, Camp Reports, Newsletters,
Gallery, Contact, Donate) at the slugs the primary nav links to — and points
the default ``Site`` at the new home page.

It seeds **structure, not copy**: every page is created with its title/slug and
an otherwise empty body, published so its URL resolves. A human then fills in the
real content in ``/admin/`` (per the architecture brief, content lives in the
running application, never in this repo). Bank details and the team/service
rosters are deliberately *not* seeded.

Safe to run repeatedly: existing pages are detected and left untouched, so a
second run only reports "exists" and changes nothing. Run it once after the
first deploy to a fresh database::

    uv run python manage.py seed_initial_content

Pass ``--delete-welcome`` to also remove Wagtail's leftover default page once the
site has been repointed at the real home page.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import Page, Site

from apps.core.models import (
    AboutPage,
    CampReportIndexPage,
    ContactPage,
    DonatePage,
    DonorsPartnersPage,
    GalleryPage,
    HomePage,
    NewsletterIndexPage,
    OurWorkPage,
    TeamPage,
)

# (model, title, slug) for the core children, in nav order. Slugs MUST match
# templates/partials/nav.html (/about/, /team/, /our-work/, /donors-partners/,
# /camp-reports/, /newsletters/, /gallery/, /contact/, /donate/). The
# Newsletter/Camp Report archives, the Gallery (Plan 06), and Donors &
# Partners (Plan 11) are seeded empty — each shows its own "coming soon" state
# until content is entered — so their nav links resolve immediately after
# deploy rather than 404ing until the first admin visit.
CORE_CHILDREN = [
    (AboutPage, "About", "about"),
    (TeamPage, "Our Team", "team"),
    (OurWorkPage, "Our Work", "our-work"),
    (DonorsPartnersPage, "Donors & Partners", "donors-partners"),
    (CampReportIndexPage, "Camp Reports", "camp-reports"),
    (NewsletterIndexPage, "Newsletters", "newsletters"),
    (GalleryPage, "Gallery", "gallery"),
    (ContactPage, "Contact", "contact"),
    (DonatePage, "Donate", "donate"),
]


class Command(BaseCommand):
    help = (
        "Idempotently seed the initial Wagtail page tree (Home + core pages) and "
        "point the default Site at the Home page. Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete-welcome",
            action="store_true",
            help=(
                "Delete Wagtail's default 'Welcome' page once the Site has been "
                "repointed at the real Home page."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        root = Page.objects.filter(depth=1).first()
        if root is None:
            self.stderr.write(
                self.style.ERROR(
                    "No Wagtail root page found — is the database migrated?"
                )
            )
            return

        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            self.stderr.write(
                self.style.ERROR("No default Site found — is the database migrated?")
            )
            return

        previous_root = site.root_page  # Wagtail's default 'Welcome' page, usually

        home = self._get_or_create_home(root)
        self._repoint_site(site, home)
        self._create_children(home)
        self._maybe_delete_welcome(options["delete_welcome"], previous_root, home)

        self.stdout.write(self.style.SUCCESS("Initial content seed complete."))

    # -- steps ---------------------------------------------------------------

    def _get_or_create_home(self, root: Page) -> HomePage:
        home = HomePage.objects.first()
        if home is not None:
            self.stdout.write(f"  exists   Home page ({home.slug!r})")
            return home

        # Avoid a slug clash with the default Welcome page (also 'home' under root)
        # before creating our own — the root page's own slug never appears in URLs.
        slug = "home"
        clash = Page.objects.child_of(root).filter(slug=slug).exists()
        if clash:
            slug = "home-page"

        home = HomePage(title="The Thandkoi Clinics", slug=slug)
        root.add_child(instance=home)
        home.save_revision().publish()
        self.stdout.write(self.style.SUCCESS(f"  created  Home page ({home.slug!r})"))
        return home

    def _repoint_site(self, site: Site, home: HomePage) -> None:
        if site.root_page_id == home.id:
            return
        site.root_page = home
        site.save()
        self.stdout.write(
            self.style.SUCCESS(f"  updated  default Site → Home page ({home.slug!r})")
        )

    def _create_children(self, home: HomePage) -> None:
        for model, title, slug in CORE_CHILDREN:
            # Each core page is max_count=1, so existence is a simple type check.
            if model.objects.exists():
                existing = model.objects.first()
                self.stdout.write(f"  exists   {title} ({existing.slug!r})")
                continue
            page = model(title=title, slug=slug)
            home.add_child(instance=page)
            page.save_revision().publish()
            self.stdout.write(self.style.SUCCESS(f"  created  {title} ({slug!r})"))

    def _maybe_delete_welcome(
        self, delete_welcome: bool, previous_root: Page | None, home: HomePage
    ) -> None:
        if not delete_welcome or previous_root is None:
            return
        # Only delete the old default page — never our own Home page, and never a
        # page that is still a live HomePage.
        if previous_root.id == home.id:
            return
        if isinstance(previous_root.specific, HomePage):
            return
        slug = previous_root.slug
        previous_root.delete()
        self.stdout.write(self.style.SUCCESS(f"  deleted  old default page ({slug!r})"))
