"""
Core content models (Plan 04, extended by Plan 05, Plan 06).

The site's core pages — Home, About, Team, Our Work, Contact, Donate — plus the
site-wide Contact & Bank Details setting, modelled as editable Wagtail content a
non-technical admin can maintain in ``/admin/`` without touching code. Plan 06
adds the Newsletter and Camp Report archives (index + child *page* pattern) and
the Gallery (orderable child *images*, not pages).

Three Wagtail idioms carry the design here:

* **Orderable child models** (``TeamMember``, ``Service``, ``SocialLink``,
  ``GalleryImage``) — add / remove / reorder inline on their parent, no
  separate admin screen.
* **StreamField** on ``HomePage`` — a flexible body whose block templates each
  ``{% include %}`` a Plan 03.5 section partial, so pages *compose* the merged
  layout kit rather than authoring new section markup or CSS.
* **Index + child-page archives** (``NewsletterIndexPage``/``NewsletterPage``,
  ``CampReportIndexPage``/``CampReportPage``) — new to this repo in Plan 06;
  unlike the orderable children above, each issue/camp needs its own URL and
  SEO metadata, so it's a real ``Page``, grounded against Wagtail's own
  index/child archive idiom (no in-repo precedent existed before this plan).

Content (the real vision statement, team roster, service list, bank details)
lives in PostgreSQL, entered through the admin — never committed to this repo
(architecture brief: "configured in the running application").
"""

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail import blocks
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
        "core.DonatePage",
        "core.NewsletterIndexPage",
        "core.CampReportIndexPage",
        "core.GalleryPage",
    ]

    def get_latest_report(self):
        """The most recent published daily report, or ``None``.

        Plan 08 introduces the pipeline-fed report content type; until then
        there is nothing to query, so this returns ``None`` and the Home
        template hides the teaser (degrades gracefully rather than showing an
        empty box). When Plan 08 lands it wires the real "latest published"
        query here — no change to the Home template is needed for the teaser
        to start rendering.
        """
        return None

    def get_latest_newsletter(self):
        """The most recently published newsletter issue, or ``None``.

        Plan 06's half of the "latest report/newsletter" teaser Plan 04 left
        wired to nothing — mirrors ``get_latest_report``'s same degrade-to-
        nothing guard, now with a real query on the other side.
        """
        return NewsletterPage.objects.live().order_by("-issue_date").first()

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["latest_report"] = self.get_latest_report()
        context["latest_newsletter"] = self.get_latest_newsletter()
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


class DonatePage(Page):
    """Zakat/Sadaqa "Giving with Purpose" message + ways to actually give.

    A placeholder, not a checkout (architecture brief §5 + this assistant's own
    safety rules never build a live money-movement flow): plain
    ``RichTextField``s, same reasoning as About/Contact — the copy is
    predictable, not flexible. Bank details are deliberately **not** fields
    here; they're pulled live from the shared ``ContactBankSettings`` singleton
    (Plan 04) so a correction only ever needs one edit, never two. Zakat and
    Sadaqa get their own section each (maintainer decision, Plan 05) rather than
    one blended message.
    """

    intro = RichTextField(
        blank=True, help_text='"Giving with Purpose" message (PDF p.18).'
    )
    zakat_description = RichTextField(
        blank=True,
        help_text="Zakat section: specific eligibility/calculation rules (PDF p.18).",
    )
    sadaqa_description = RichTextField(
        blank=True,
        help_text="Sadaqa section: general voluntary giving (PDF p.18).",
    )
    how_to_give = RichTextField(
        blank=True,
        help_text="How-to-give steps for the bank transfer below.",
    )
    in_kind_giving = RichTextField(
        blank=True,
        help_text="In-kind options (medicine, equipment, volunteering) — "
        "arranged via Contact, not a form.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        FieldPanel("zakat_description"),
        FieldPanel("sadaqa_description"),
        FieldPanel("how_to_give"),
        FieldPanel("in_kind_giving"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    def get_context(self, request, *args, **kwargs):
        """Add the live Contact page URL for the "another way to give" CTA.

        Guarded the same way ``HomePage.get_latest_report`` guards its teaser:
        if no Contact page exists yet, this is ``None`` and the template omits
        the CTA entirely rather than linking to a dead "#".
        """
        context = super().get_context(request, *args, **kwargs)
        contact_page = ContactPage.objects.live().first()
        context["contact_page_url"] = contact_page.url if contact_page else None
        return context

    class Meta:
        verbose_name = "Donate page"


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


# --- Plan 06: Newsletter archive --------------------------------------------


class NewsletterIndexPage(Page):
    """Archive of newsletter issues, newest first.

    Lists only *published* issues (Wagtail's own draft/publish gate — no
    separate flag needed, Plan 06 decision) so a drafted-but-unpublished issue
    never appears here or in Home's teaser.
    """

    intro = RichTextField(blank=True, help_text="Optional intro copy for the archive.")

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["core.NewsletterPage"]

    def get_newsletters(self):
        """Published issues under this index, newest first."""
        return NewsletterPage.objects.live().child_of(self).order_by("-issue_date")

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        paginator = Paginator(self.get_newsletters(), 12)
        context["newsletters"] = paginator.get_page(request.GET.get("page"))
        return context

    class Meta:
        verbose_name = "Newsletter index page"


class NewsletterPage(Page):
    """One newsletter issue.

    Independently linkable and carries its own SEO metadata — unlike Plan 04's
    Team/Service *orderable children*, an issue is meant to be shared and
    indexed on its own, which is exactly what a real ``Page`` gives it. Plan 09
    later drafts into this same model via ``save_revision()`` (a Wagtail draft,
    unpublished, same mechanism a human uses) — no new model for AI content.

    ``body`` is a StreamField (not a plain ``RichTextField`` like About/
    Contact) so an issue can mix prose with photos; the photo block reuses
    ``ConsentedImageBlock`` (Plan 04) since a newsletter issue is exactly the
    kind of content likely to carry camp/community photography.
    """

    issue_date = models.DateField(help_text="The issue's cover date.")
    summary = models.TextField(
        blank=True,
        help_text="Short teaser blurb — shown in the archive list and Home's "
        "latest-newsletter section.",
    )
    body = StreamField(
        [
            ("paragraph", blocks.RichTextBlock()),
            ("photo", core_blocks.ConsentedImageBlock()),
        ],
        blank=True,
        help_text="The issue's content.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("issue_date"),
        FieldPanel("summary"),
        FieldPanel("body"),
    ]

    parent_page_types = ["core.NewsletterIndexPage"]
    subpage_types: list[str] = []

    class Meta:
        verbose_name = "Newsletter"


# --- Plan 06: Camp Report archive -------------------------------------------


class CampReportIndexPage(Page):
    """Archive of medical camp reports, newest first.

    Same index + child-page pattern as the Newsletter archive above — see
    ``NewsletterIndexPage`` for why this needed a real archive rather than
    Plan 04's orderable-child pattern.
    """

    intro = RichTextField(blank=True, help_text="Optional intro copy for the archive.")

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["core.CampReportPage"]

    def get_camp_reports(self):
        """Published camp reports under this index, newest first."""
        return CampReportPage.objects.live().child_of(self).order_by("-camp_date")

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        paginator = Paginator(self.get_camp_reports(), 12)
        context["camp_reports"] = paginator.get_page(request.GET.get("page"))
        return context

    class Meta:
        verbose_name = "Camp report index page"


class CampReportPage(Page):
    """One medical camp's report — date, patients served, credits, photos.

    Patients served is **structured, split by category** (children / general /
    Welfare-free-service, matching the source PDF's own breakdown) rather than
    one lumped total, with the total *derived* rather than entered separately
    (maintainer decision, Plan 06) — the clinic already tracks it this way, and
    structured fields let a future plan aggregate across camps without
    re-parsing prose. Photos reuse ``ConsentedImageBlock`` (Plan 04) and are
    this plan's other real load-bearing use of the consent gate alongside the
    Gallery — camp photography is exactly the case it was built for.
    """

    camp_date = models.DateField(help_text="The date of the camp.")
    location = models.CharField(max_length=180, blank=True)
    patients_children = models.PositiveIntegerField(
        default=0, help_text="Patients served — Paediatrics / children."
    )
    patients_general = models.PositiveIntegerField(
        default=0, help_text="Patients served — General Medicine / adults."
    )
    patients_welfare = models.PositiveIntegerField(
        default=0,
        help_text="Patients served under the Welfare (free-of-cost) category.",
    )
    services_offered = StreamField(
        [("service", blocks.CharBlock(max_length=120))],
        blank=True,
        help_text="Services offered at this camp, one entry each.",
    )
    partner_credits = models.TextField(
        blank=True, help_text="Partner organisations and volunteers, one per line."
    )
    narrative = RichTextField(blank=True, help_text="The camp's story.")
    photos = StreamField(
        [("photo", core_blocks.ConsentedImageBlock())],
        blank=True,
        help_text="Camp photos — consent required before publish.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("camp_date"),
        FieldPanel("location"),
        MultiFieldPanel(
            [
                FieldPanel("patients_children"),
                FieldPanel("patients_general"),
                FieldPanel("patients_welfare"),
            ],
            heading="Patients served (by category)",
        ),
        FieldPanel("services_offered"),
        FieldPanel("partner_credits"),
        FieldPanel("narrative"),
        FieldPanel("photos"),
    ]

    parent_page_types = ["core.CampReportIndexPage"]
    subpage_types: list[str] = []

    @property
    def total_patients_served(self):
        """The derived total — never entered directly (Plan 06 decision)."""
        return self.patients_children + self.patients_general + self.patients_welfare

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["patient_stats"] = [
            {"value": str(self.patients_children), "label": "Children"},
            {"value": str(self.patients_general), "label": "General"},
            {"value": str(self.patients_welfare), "label": "Welfare (free)"},
            {
                "value": str(self.total_patients_served),
                "label": "Total patients served",
            },
        ]
        context["camp_photos"] = [
            {
                "image": block.value["image"].get_rendition("fill-640x640").url,
                "alt": block.value["alt_text"] or block.value["image"].title,
                "caption": block.value["caption"],
            }
            for block in self.photos
            if block.value.get("image") and block.value.get("consent_confirmed")
        ]
        return context

    class Meta:
        verbose_name = "Camp report"


# --- Plan 06: Gallery --------------------------------------------------------


class GalleryPage(Page):
    """A single photo gallery.

    Images are orderable child *objects*, not child pages — mirroring Plan
    04's Team/Service pattern rather than the Newsletter/Camp Report archive
    pattern above, since a gallery photo needs no URL or SEO metadata of its
    own (Plan 06 decision, "Gallery structure").
    """

    intro = RichTextField(blank=True, help_text="Optional intro copy above the grid.")

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        InlinePanel("images", label="Photos"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types: list[str] = []

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["gallery_items"] = [
            {
                "image": gallery_image.image.get_rendition("fill-640x640").url,
                "alt": gallery_image.alt_text or gallery_image.image.title,
                "caption": gallery_image.caption,
            }
            for gallery_image in self.images.all()
            if gallery_image.image_id and gallery_image.consent_confirmed
        ]
        return context

    class Meta:
        verbose_name = "Gallery page"


class GalleryImage(Orderable):
    """One photo in a Gallery — an orderable child of ``GalleryPage``.

    ``consent_confirmed`` is **mandatory here, not just present** — this is
    exactly the surface Plan 04 built the consent convention for: identifiable
    camp/community photography (brand-guidelines.md §5). Enforced in
    ``clean()`` so no image can be saved with an image set but consent left
    unticked, mirroring ``ConsentedImageBlock``'s own guard.
    """

    page = ParentalKey(GalleryPage, on_delete=models.CASCADE, related_name="images")
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    alt_text = models.CharField(
        max_length=180,
        blank=True,
        help_text="Describe the image for screen-reader users. Falls back to "
        "the image's own title if left blank.",
    )
    caption = models.CharField(max_length=180, blank=True)
    consent_confirmed = models.BooleanField(
        default=False,
        help_text="Tick to confirm every identifiable person in this photo has "
        "consented to it being published (brand-guidelines.md §5).",
    )

    panels = [
        FieldPanel("image"),
        FieldPanel("alt_text"),
        FieldPanel("caption"),
        FieldPanel("consent_confirmed"),
    ]

    def clean(self):
        super().clean()
        if self.image_id and not self.consent_confirmed:
            raise ValidationError(
                {"consent_confirmed": "Confirm consent before publishing this photo."}
            )

    def __str__(self):
        return self.caption or (self.image.title if self.image_id else "Untitled photo")
