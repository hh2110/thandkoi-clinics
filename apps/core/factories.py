"""
factory_boy factories for core models.

Wagtail pages live in a tree, so they can't be created with a plain
``Model.objects.create(...)`` — a new page must be added under a parent via
``parent.add_child(instance=...)``. ``_TreePageFactory`` encapsulates that so
this and later plans have one consistent pattern to follow. Content pages
(About/Team/Our Work/Contact) pass ``parent=<a HomePage>`` since they sit under
the home page in the tree.
"""

import datetime

import factory
from wagtail.models import Page

from apps.core.models import (
    AboutPage,
    CampReportIndexPage,
    CampReportPage,
    ContactPage,
    DonatePage,
    GalleryImage,
    GalleryPage,
    HomePage,
    NewsletterIndexPage,
    NewsletterPage,
    OurWorkPage,
    Service,
    TeamMember,
    TeamPage,
)

# A ready-made StreamField body composing the Plan 03.5 section kit (hero +
# impact-stat band + a donate CTA left unlinked, so the band stays hidden — the
# current pre-Plan-05 state). Numbers/copy here are test fixtures only.
DEFAULT_HOME_BODY = [
    (
        "hero",
        {
            "eyebrow": "Primary care · Thandkoi, Swabi",
            "headline": "Compassionate care for our community",
            "intro": "A not-for-profit, family-run primary care clinic funded on "
            "a Zakat & Sadaqa model.",
            "tagline": "صحت سب کے لیے · چراغ شفا",
            "stat_value": "Free",
            "stat_label": "for every Zakat beneficiary",
        },
    ),
    (
        "impact_stats",
        {
            "caption": "Figures entered by the admin.",
            "stats": [
                {"value": "467+", "label": "children treated"},
                {"value": "189", "label": "patients served"},
                {"value": "426", "label": "welfare (free) patients"},
                {"value": "100%", "label": "donor-funded, no fees"},
            ],
        },
    ),
    # No cta_page / cta_url: the donate band stays hidden until Plan 05 lands.
    (
        "donate_cta",
        {
            "heading": "Your Zakat keeps the doors open.",
            "body": "Every rupee goes directly to medicines and care.",
        },
    ),
]


class _TreePageFactory(factory.django.DjangoModelFactory):
    """Base factory that places a new Wagtail page under an explicit parent."""

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Attach the new page under an explicit parent (default: tree root)."""
        parent = kwargs.pop("parent", None) or Page.get_first_root_node()
        instance = model_class(*args, **kwargs)
        parent.add_child(instance=instance)
        return instance


class HomePageFactory(_TreePageFactory):
    class Meta:
        model = HomePage

    title = factory.Sequence(lambda n: f"Home {n}")
    slug = factory.Sequence(lambda n: f"home-{n}")
    intro = "<p>Welcome to The Thandkoi Clinics.</p>"
    body = factory.LazyFunction(lambda: list(DEFAULT_HOME_BODY))


class AboutPageFactory(_TreePageFactory):
    class Meta:
        model = AboutPage

    title = "About"
    slug = "about"
    vision = "<p>Health for all.</p>"
    mission = "<p>Dignified primary care, free at the point of need.</p>"


class TeamPageFactory(_TreePageFactory):
    class Meta:
        model = TeamPage

    title = "Team"
    slug = "team"
    intro = "<p>United by a shared commitment.</p>"


class TeamMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TeamMember

    name = factory.Sequence(lambda n: f"Dr Example {n}")
    role = "Physician"
    category = TeamMember.DOCTORS
    bio = "A short bio."


class OurWorkPageFactory(_TreePageFactory):
    class Meta:
        model = OurWorkPage

    title = "Our Work"
    slug = "our-work"
    intro = "<p>What we do.</p>"


class ServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Service {n}")
    description = "A service the clinic offers."
    status = Service.ACTIVE


class ContactPageFactory(_TreePageFactory):
    class Meta:
        model = ContactPage

    title = "Contact"
    slug = "contact"


class DonatePageFactory(_TreePageFactory):
    class Meta:
        model = DonatePage

    title = "Donate"
    slug = "donate"
    zakat_description = "<p>Specific eligibility and calculation rules.</p>"
    sadaqa_description = "<p>General voluntary giving, any amount, any time.</p>"


class NewsletterIndexPageFactory(_TreePageFactory):
    class Meta:
        model = NewsletterIndexPage

    title = "Newsletters"
    slug = "newsletters"


class NewsletterPageFactory(_TreePageFactory):
    class Meta:
        model = NewsletterPage

    title = factory.Sequence(lambda n: f"Newsletter issue {n}")
    slug = factory.Sequence(lambda n: f"issue-{n}")
    issue_date = factory.LazyFunction(datetime.date.today)
    summary = "A short teaser blurb."


class CampReportIndexPageFactory(_TreePageFactory):
    class Meta:
        model = CampReportIndexPage

    title = "Camp Reports"
    slug = "camp-reports"


class CampReportPageFactory(_TreePageFactory):
    class Meta:
        model = CampReportPage

    title = factory.Sequence(lambda n: f"Camp report {n}")
    slug = factory.Sequence(lambda n: f"camp-{n}")
    camp_date = factory.LazyFunction(datetime.date.today)
    location = "Thandkoi, Swabi"
    patients_children = 100
    patients_general = 50
    patients_welfare = 25


class GalleryPageFactory(_TreePageFactory):
    class Meta:
        model = GalleryPage

    title = "Gallery"
    slug = "gallery"


class GalleryImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GalleryImage

    caption = "A clinic photo."
    consent_confirmed = True
