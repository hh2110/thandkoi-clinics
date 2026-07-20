"""
Core content models (Plan 04).

The site's five core pages — Home, About, Team, Our Work, Contact — plus the
site-wide Contact & Bank Details setting, modelled as editable Wagtail content a
non-technical admin can maintain in ``/admin/`` without touching code.

Two Wagtail idioms carry the design here:

* **Orderable child models** (``TeamMember``, ``Service``, ``SocialLink``) —
  add / remove / reorder inline on their parent, no separate admin screen.
* **StreamField** on ``HomePage`` — a flexible body whose block templates each
  ``{% include %}`` a Plan 03.5 section partial, so pages *compose* the merged
  layout kit rather than authoring new section markup or CSS.

Content (the real vision statement, team roster, service list, bank details)
lives in PostgreSQL, entered through the admin — never committed to this repo
(architecture brief: "configured in the running application").
"""

from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Orderable, Page

from apps.core import blocks as core_blocks


class HomePage(Page):
    """The site's root page — a StreamField body composed of Plan 03.5 sections.

    The body's block templates map onto the hero / stat-band / cta-band partials;
    a "latest daily report" teaser (feature split) renders conditionally beneath
    it once Plan 06 supplies a report content type (``get_latest_report`` returns
    ``None`` until then, so the section stays hidden rather than broken).
    """

    # Legacy Plan 01 field, retained for data safety but no longer surfaced in
    # the admin (no FieldPanel below) — the StreamField ``body`` drives the page,
    # so an editable ``intro`` panel would silently discard anything typed into
    # it. The field definition is kept unchanged so no migration is generated.
    intro = RichTextField(
        blank=True,
        help_text="Optional short lead text (legacy Plan 01 field; the body "
        "below drives the page).",
    )
    body = StreamField(
        [
            ("hero", core_blocks.HeroBlock()),
            ("impact_stats", core_blocks.ImpactStatsBlock()),
            ("donate_cta", core_blocks.DonateCTABlock()),
        ],
        blank=True,
        help_text="Compose the home page from the section kit.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("body"),
    ]

    # Only one HomePage, sitting directly under the Wagtail root; the other core
    # pages are its children so the primary nav's slugs (/about/, /team/, …)
    # resolve under it.
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]
    subpage_types = [
        "core.AboutPage",
        "core.TeamPage",
        "core.OurWorkPage",
        "core.ContactPage",
    ]

    def get_latest_report(self):
        """The most recent published daily report, or ``None``.

        Plan 06 introduces the report content type; until then there is nothing
        to query, so this returns ``None`` and the Home template hides the teaser
        (degrades gracefully rather than showing an empty box). When Plan 06
        lands it wires the real "latest published" query here — no change to the
        Home template is needed for the teaser to start rendering.
        """
        return None

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["latest_report"] = self.get_latest_report()
        return context

    class Meta:
        verbose_name = "Home page"


class AboutPage(Page):
    """The clinic's story: welcome, vision / mission / objectives, care model.

    Plain ``RichTextField``s — an About page is predictable, so it doesn't need a
    StreamField. The real copy (organisational profile PDF p.5–7, p.11–13) is
    entered in the admin later; this ships the empty shape.
    """

    intro = RichTextField(
        blank=True, help_text="Founders' welcome / message (PDF p.5)."
    )
    vision = RichTextField(blank=True, help_text="Vision statement (PDF p.6).")
    mission = RichTextField(blank=True, help_text="Mission statement (PDF p.6).")
    objectives = RichTextField(blank=True, help_text="Objectives (PDF p.6).")
    quality_of_care = RichTextField(
        blank=True, help_text="Quality-of-care model (PDF p.7)."
    )
    founding_story = RichTextField(
        blank=True, help_text="Inauguration & first medical camp (PDF p.11–13)."
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        FieldPanel("vision"),
        FieldPanel("mission"),
        FieldPanel("objectives"),
        FieldPanel("quality_of_care"),
        FieldPanel("founding_story"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    class Meta:
        verbose_name = "About page"


class TeamPage(Page):
    """The team roster, grouped Doctors / Staff & Committee.

    Members are orderable child objects (not pages — they need no URL of their
    own); the template groups them by category and renders each through the
    Plan 03.5 card grid's person-card variant.
    """

    intro = RichTextField(
        blank=True,
        help_text='Team introduction ("united by a shared commitment…", PDF p.10).',
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        InlinePanel("members", label="Team members"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        members = self.members.all()
        # Group in Python so each category renders as its own card grid; members
        # keep their admin-defined ``sort_order`` within a group.
        context["doctors"] = [m for m in members if m.category == TeamMember.DOCTORS]
        context["staff"] = [m for m in members if m.category == TeamMember.STAFF]
        return context

    class Meta:
        verbose_name = "Team page"


class TeamMember(Orderable):
    """One person on the team — an orderable child of ``TeamPage``.

    Staff / team photos are implicitly consented (professional portraits of the
    clinic's own people), so this deliberately carries no ``consent_confirmed``
    field; that gate exists for non-staff photography (see
    ``blocks.ConsentedImageBlock``, reused from Plan 06).
    """

    DOCTORS = "doctors"
    STAFF = "staff"
    CATEGORY_CHOICES = [
        (DOCTORS, "Doctors"),
        (STAFF, "Staff & Committee"),
    ]

    page = ParentalKey(TeamPage, on_delete=models.CASCADE, related_name="members")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=140, blank=True)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default=DOCTORS
    )
    photo = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Portrait; falls back to a placeholder until one is added.",
    )
    bio = models.TextField(blank=True, help_text="Short one- or two-line bio.")

    panels = [
        FieldPanel("name"),
        FieldPanel("role"),
        FieldPanel("category"),
        FieldPanel("photo"),
        FieldPanel("bio"),
    ]

    def __str__(self):
        return self.name


class OurWorkPage(Page):
    """The clinic's services and infrastructure.

    Services are orderable children carrying a ``status`` so the template can
    distinguish live services from the two "aiming to introduce" ones (Laboratory
    & Pharmacy, Radiology/Imaging) — presenting the latter with a "Planned" tag
    rather than as already available (PDF p.15).
    """

    intro = RichTextField(blank=True, help_text="Introduction to the clinic's work.")
    infrastructure = RichTextField(
        blank=True, help_text="Our infrastructure (PDF p.16–17)."
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        InlinePanel("services", label="Services"),
        FieldPanel("infrastructure"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    class Meta:
        verbose_name = "Our Work page"


class Service(Orderable):
    """One service offered (or planned) — an orderable child of ``OurWorkPage``.

    Mirrors ``TeamMember``'s pattern so there's one convention. ``status``
    separates active services from aspirational ones; the template renders the
    ``Planned`` card tag for the latter.
    """

    ACTIVE = "active"
    PLANNED = "planned"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PLANNED, "Planned"),
    ]

    page = ParentalKey(OurWorkPage, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional icon or photo for the service card.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
        help_text='"Planned" shows a coming-soon tag and must not read as available.',
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("description"),
        FieldPanel("image"),
        FieldPanel("status"),
    ]

    def __str__(self):
        return self.name


class ContactPage(Page):
    """Contact details, rendered from the shared Contact & Bank Details setting.

    No contact form (no form backend, no spam surface, no third-party scripts —
    CLAUDE.md privacy guardrails); a plain ``mailto:`` is enough for a small
    admin team. The phone / email / socials / bank details all come from the
    ``ContactBankSettings`` singleton, so editing that setting updates this page
    with no redeploy.
    """

    intro = RichTextField(blank=True, help_text="Optional lead text above the details.")

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    class Meta:
        verbose_name = "Contact page"


@register_setting(icon="mail")
class ContactBankSettings(ClusterableModel, BaseSiteSetting):
    """Site-wide contact & Zakat/Sadaqa bank details (a Wagtail singleton).

    The architecture brief mandates these be "configured in the running
    application, not stored in this repository", so they are neither a fixture
    nor a template constant: an admin enters them in /admin/ → Settings, and both
    the footer and the Contact page read them from here. ``ClusterableModel`` is
    mixed in so social links can be orderable children (``InlinePanel``).
    """

    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    map_embed_url = models.URLField(
        blank=True,
        help_text="Optional map embed URL (e.g. an OpenStreetMap share link).",
    )

    bank_account_title = models.CharField(max_length=140, blank=True)
    bank_name = models.CharField(max_length=140, blank=True)
    bank_iban = models.CharField(max_length=60, blank=True)
    bank_account_number = models.CharField(max_length=60, blank=True)
    bank_branch = models.CharField(
        max_length=140, blank=True, help_text="Branch name and/or code."
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("phone"),
                FieldPanel("email"),
                FieldPanel("address"),
                FieldPanel("map_embed_url"),
                InlinePanel("social_links", label="Social links"),
            ],
            heading="Contact",
        ),
        MultiFieldPanel(
            [
                FieldPanel("bank_account_title"),
                FieldPanel("bank_name"),
                FieldPanel("bank_iban"),
                FieldPanel("bank_account_number"),
                FieldPanel("bank_branch"),
            ],
            heading="Zakat & Sadaqa bank details",
        ),
    ]

    class Meta:
        verbose_name = "Contact & bank details"


class SocialLink(Orderable):
    """One social/contact link on the Contact & Bank Details setting."""

    setting = ParentalKey(
        ContactBankSettings, on_delete=models.CASCADE, related_name="social_links"
    )
    label = models.CharField(max_length=60, help_text='e.g. "Instagram".')
    url = models.URLField()

    panels = [
        FieldPanel("label"),
        FieldPanel("url"),
    ]

    def __str__(self):
        return self.label
