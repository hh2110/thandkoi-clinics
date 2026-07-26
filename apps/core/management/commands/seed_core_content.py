"""Populate the core pages with real content from the organisational profile.

This is a **one-time content bootstrap** for a fresh site: it fills Home, About,
Team, Our Work, Contact, and Donate with the copy, team roster, services, and
Zakat/Sadaqa bank details taken from *The Thandkoi Clinics* profile document, so
the maintainer starts from real content instead of blank pages rather than
re-typing it all into ``/admin/``.

Everything is written as an **unpublished draft revision** (not published), so a
human reviews and publishes each page in ``/admin/`` — nothing goes live until
they do. (``ContactBankSettings`` is a Wagtail *setting*, which has no
draft/publish workflow, so its blank fields are filled directly; existing values
are never overwritten.) Pass ``--publish`` to publish immediately instead.

Content normally lives only in the running application (architecture brief), not
in the repo; this command is the deliberate exception that seeds it once. It
assumes the page tree already exists — run ``seed_initial_content`` first.

    uv run python manage.py seed_core_content            # draft (default)
    uv run python manage.py seed_core_content --publish   # publish immediately
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import Site

from apps.core.models import (
    AboutPage,
    ContactBankSettings,
    ContactPage,
    DonatePage,
    HomePage,
    OurWorkPage,
    Service,
    SocialLink,
    TeamMember,
    TeamPage,
)

# --- Content (from "The Thandkoi Clinics" profile document) ----------------

ABOUT_INTRO = (
    "<p>Thandkoi Clinics is a humble initiative dedicated to serving humanity "
    "through accessible, compassionate, and high-quality healthcare. Established "
    "with a vision to care for our families, strengthen our communities, and "
    "invest in the wellbeing of future generations, the clinics aim to provide "
    "not-for-profit medical services to those most in need with dignity, "
    "sincerity, and compassion.</p>"
    "<p>This initiative reflects our shared commitment to improving lives and "
    "creating a healthier, stronger community for all. We pray that Allah (SWT) "
    "places barakah in this effort, makes it a source of benefit for all, and "
    "abundantly rewards every individual who contributed their time, support, "
    "and dedication to turning this vision into a reality.</p>"
    "<p>With sincere prayers and gratitude,<br/>Dr Amanullah and "
    "Dr Kausar Khurshid</p>"
)
ABOUT_VISION = (
    "<p>A healthy community where quality healthcare is accessible to all, "
    "regardless of any discrimination.</p>"
)
ABOUT_MISSION = (
    "<p>To provide cost-effective, compassionate, and accessible healthcare to "
    "underserved communities across Swabi.</p>"
)
ABOUT_OBJECTIVES = (
    "<ul>"
    "<li>To provide low-cost and accessible quality healthcare to "
    "underprivileged communities.</li>"
    "<li>To deliver compassionate and dignified patient-centred care.</li>"
    "<li>To improve health outcomes through early diagnosis and treatment.</li>"
    "<li>To promote health awareness and disease prevention.</li>"
    "<li>To establish a sustainable community healthcare initiative.</li>"
    "<li>To strengthen community wellbeing for present and future "
    "generations.</li>"
    "</ul>"
)
ABOUT_QUALITY = (
    "<p>The Quality of Care Protocol for this facility is designed as an "
    "integrated, patient-centred primary healthcare model delivered under one "
    "roof. Grounded in safety, efficiency, and accessibility, the model promotes "
    "coordinated care and improved patient outcomes. It is also structured for "
    "scalability and can be replicated in other districts of KP and across "
    "Pakistan as a sustainable primary healthcare framework.</p>"
)
ABOUT_FOUNDING = (
    "<p>On 16 May 2026, the people of Thandkoi witnessed a historic milestone "
    "with the inauguration of their affordable and accessible healthcare "
    "facility. The clinic was inaugurated by former Speaker of the National "
    "Assembly and MNA Mr. Asad Qaiser, alongside DHO Swabi Dr. Abdul Latif and "
    "other community leaders. The occasion was followed by a free medical camp, "
    "where consultations were provided, medicines were dispensed, and families "
    "received care, marking the beginning of accessible healthcare for the "
    "community.</p>"
    "<p>A Free Medical Camp was organised under the Thandkoi Clinics initiative "
    "with the support of volunteer doctors from Khyber Teaching Hospital and "
    "Police & Services Hospital. Free consultations, medicines, and "
    "healthcare services were provided across Paediatrics, Gynaecology, General "
    "Medicine, and Psychiatry. In just one morning, the camp served 379 "
    "patients, with all services provided 100% free of cost.</p>"
)

TEAM_INTRO = (
    "<p>The Thandkoi Clinics team is united by a shared commitment to serve "
    "humanity through compassionate and accessible healthcare. Together, our "
    "doctors, staff, and volunteers work with sincerity, dignity, and care to "
    "improve lives and create a trusted environment of healing, hope, and "
    "service for the community.</p>"
)
# (name, role) — from "Meet Our Team". Roles for doctors aren't itemised in the
# source, so they're left blank for the maintainer to fill in the admin.
DOCTORS = [
    ("Dr Khadija Amanullah", ""),
    ("Dr Amanullah", ""),
    ("Dr Kausar Khurshid", ""),
    ("Dr Yusra Amanullah", ""),
    ("Dr Mubaraka Amanullah", ""),
    ("Dr Saifullah Khan", ""),
    ("Dr Hikmatyar Hasan", ""),
    ("Dr Javeria Khan", ""),
    ("Abdul Azim", ""),
    ("Syed Dawood Shah", ""),
]
COMMITTEE = [
    ("Dr Ammar Fayyaz", "In-charge Medical Officer"),
    ("Ataullah Khan", "Health & Zakat Committee Chair"),
    ("Shaheera Hayat", "Advocacy & Communications Officer"),
    ("Mohammad Amir", "Health & Zakat Committee Member"),
    ("Umar Jan", "Logistics & Accounts Assistant"),
    ("Mohammad Khalid", "Health & Zakat Committee Member"),
    ("Siraj Ahmad Lodhi", "Finance & Admin Officer"),
]

OURWORK_INTRO = (
    "<p>In support of our vision for accessible healthcare, we provide "
    "comprehensive medical services under one roof, from everyday "
    "consultations to emergency care, always with dignity and free of cost to "
    "those most in need.</p>"
)
# (name, description) for active services.
SERVICES_ACTIVE = [
    ("Regular Check-ups", "Ongoing medical consultations for children and adults."),
    (
        "Emergency Care Services",
        "Urgent medical response to stabilise patients "
        "with life-threatening conditions.",
    ),
    (
        "Women's Health Unit",
        "Dedicated care and support for women's health and wellbeing.",
    ),
    (
        "Medications",
        "Providing essential medicines free of cost to deserving individuals.",
    ),
    ("Telemedicine", "Remote healthcare consultations."),
    ("Health Education", "Empowering individuals with health awareness."),
    (
        "Capacity Building & Community Engagement",
        "Initiatives to strengthen "
        "healthcare providers' skills and enhance community awareness and "
        "participation in preventive care.",
    ),
]
SERVICES_PLANNED = [
    (
        "Laboratory & Pharmacy",
        "Aiming to introduce accessible lab and pharmacy facilities.",
    ),
    ("Radiology / Imaging", "Aiming to introduce diagnostic imaging services."),
]
OURWORK_INFRASTRUCTURE = (
    "<ul>"
    "<li>A well-organised reception and registration desk ensuring smooth "
    "patient intake and flow management.</li>"
    "<li>A structured triage system prioritising patients based on medical need "
    "and urgency.</li>"
    "<li>Clean, comfortable waiting areas ensuring patient dignity, privacy, and "
    "easy access.</li>"
    "<li>Dedicated consultation and examination rooms for specialised and "
    "confidential care.</li>"
    "<li>Integrated diagnostic services with on-site laboratory support for "
    "timely clinical decision-making.</li>"
    "<li>Strong infection prevention and control measures ensuring safe patient "
    "handling.</li>"
    "<li>On-site pharmacy services ensuring timely access to essential "
    "medicines.</li>"
    "<li>Comprehensive immunisation services delivered in a safe and organised "
    "setting.</li>"
    "<li>A secure digital health record system enabling efficient and "
    "coordinated patient data management.</li>"
    "</ul>"
)

CONTACT_INTRO = (
    "<p>We'd love to hear from you, whether for appointments, volunteering, or "
    "to discuss in-kind support. Reach us using the details below.</p>"
)

DONATE_INTRO = (
    "<p>Every resident of Thandkoi and its surrounding areas deserves access to "
    "quality healthcare that is free, accessible, and delivered with dignity. "
    "Thandkoi Clinics brings this vision to life by advancing the principle of "
    "universal health coverage through a transparent, accountable, and "
    "registered framework built upon the spirit of Zakat, Sadaqa, and voluntary "
    "giving.</p>"
)
DONATE_ZAKAT = (
    "<p>Your Zakat directly funds free treatment, medicines, and care for "
    "eligible patients who cannot afford healthcare. Every contribution is used "
    "transparently and accountably for those most in need.</p>"
)
DONATE_SADAQA = (
    "<p>Sadaqa (voluntary charity) supports the clinic's day-to-day running, "
    "from medicines and equipment to keeping our doors open for everyone, "
    "regardless of their ability to pay.</p>"
)
DONATE_HOW = (
    "<p>You can give directly by bank transfer to the account shown below. "
    "Please reference “Donation” with your transfer so we can acknowledge your "
    "contribution.</p>"
)
DONATE_IN_KIND = (
    "<p>We also welcome in-kind support, such as medicines, medical equipment, "
    "and volunteering time from healthcare professionals. Please get in touch "
    "via our Contact page to arrange in-kind giving.</p>"
)

# Home StreamField body (block types match apps.core.blocks).
HOME_BODY = [
    (
        "hero",
        {
            "eyebrow": "Primary care · Thandkoi, Swabi",
            "headline": "Bringing healthcare to every doorstep",
            "intro": "A not-for-profit, family-run primary care clinic serving "
            "our community on a Zakat and Sadaqa model, free for those most in "
            "need.",
            "tagline": "صحت سب کے لیے",
            "stat_value": "100%",
            "stat_label": "donor-funded, free for those in need",
        },
    ),
    (
        "donate_cta",
        {
            "heading": "Your Zakat keeps our doors open",
            "body": "Every contribution goes directly to medicines and care for "
            "those who need it most.",
        },
    ),
]

# Contact & Zakat/Sadaqa bank details for the site-wide setting (public info).
BANK = {
    "phone": "+92 344 4111235",
    "email": "info.thandkoiclinics@gmail.com",
    "bank_account_title": "The Thandkoi Clinics",
    "bank_name": "Soneri Bank",
    "bank_iban": "PK83SONE0510930001644218",
    "bank_account_number": "30001644218",
    "bank_branch": "IB Khudadad City (branch code 5109)",
    "address": "Thandkoi, Swabi, Khyber Pakhtunkhwa, Pakistan",
}

# (label, url) — social links for the same setting. Seeded separately from
# BANK: these are orderable child objects (SocialLink), not plain scalar
# fields, so they can't go through the generic getattr/setattr loop below.
SOCIAL_LINKS = [
    (
        "Facebook",
        "https://www.facebook.com/profile.php"
        "?id=61588951366955&name=xhp_nt__fb__action__open_user",
    ),
    (
        "Instagram",
        "https://www.instagram.com/thandkoi.clinics/",
    ),
]


class Command(BaseCommand):
    help = (
        "Populate the core pages with real draft content from the org profile "
        "(review & publish in /admin/). Run seed_initial_content first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish each page immediately instead of leaving it as a draft.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.publish = options["publish"]
        home = HomePage.objects.first()
        if home is None:
            self.stderr.write(
                self.style.ERROR(
                    "No HomePage found — run `seed_initial_content` first."
                )
            )
            return

        self._home(home)
        self._about(home)
        self._team(home)
        self._our_work(home)
        self._contact(home)
        self._donate(home)
        self._settings()

        verb = "published" if self.publish else "drafted"
        self.stdout.write(self.style.SUCCESS(f"Core content {verb}."))
        if not self.publish:
            self.stdout.write(
                "Review each page in /admin/ (they show as drafts with "
                "unpublished changes) and Publish when ready."
            )

    # -- helpers -------------------------------------------------------------

    def _get(self, model, home, title, slug):
        """Fetch the singleton page, or create it as an unpublished child."""
        obj = model.objects.first()
        if obj is not None:
            return obj
        obj = model(title=title, slug=slug, live=False)
        home.add_child(instance=obj)
        return obj

    def _save(self, page, label):
        """Save the staged content as a draft revision (or publish it)."""
        revision = page.save_revision()
        if self.publish:
            revision.publish()
        self.stdout.write(
            self.style.SUCCESS(
                f"  {'published' if self.publish else 'drafted'}  {label}"
            )
        )

    # -- pages ---------------------------------------------------------------

    def _home(self, home):
        home.body = HOME_BODY
        self._save(home, "Home")

    def _about(self, home):
        about = self._get(AboutPage, home, "About", "about")
        about.intro = ABOUT_INTRO
        about.vision = ABOUT_VISION
        about.mission = ABOUT_MISSION
        about.objectives = ABOUT_OBJECTIVES
        about.quality_of_care = ABOUT_QUALITY
        about.founding_story = ABOUT_FOUNDING
        self._save(about, "About")

    def _team(self, home):
        team = self._get(TeamPage, home, "Our Team", "team")
        team.intro = TEAM_INTRO
        team.members.clear()
        for name, role in DOCTORS:
            team.members.add(
                TeamMember(name=name, role=role, category=TeamMember.DOCTORS)
            )
        for name, role in COMMITTEE:
            team.members.add(
                TeamMember(name=name, role=role, category=TeamMember.STAFF)
            )
        self._save(team, f"Our Team ({len(DOCTORS) + len(COMMITTEE)} members)")

    def _our_work(self, home):
        work = self._get(OurWorkPage, home, "Our Work", "our-work")
        work.intro = OURWORK_INTRO
        work.infrastructure = OURWORK_INFRASTRUCTURE
        work.services.clear()
        for name, desc in SERVICES_ACTIVE:
            work.services.add(
                Service(name=name, description=desc, status=Service.ACTIVE)
            )
        for name, desc in SERVICES_PLANNED:
            work.services.add(
                Service(name=name, description=desc, status=Service.PLANNED)
            )
        total = len(SERVICES_ACTIVE) + len(SERVICES_PLANNED)
        self._save(work, f"Our Work ({total} services)")

    def _contact(self, home):
        contact = self._get(ContactPage, home, "Contact", "contact")
        contact.intro = CONTACT_INTRO
        self._save(contact, "Contact")

    def _donate(self, home):
        donate = self._get(DonatePage, home, "Donate", "donate")
        donate.intro = DONATE_INTRO
        donate.zakat_description = DONATE_ZAKAT
        donate.sadaqa_description = DONATE_SADAQA
        donate.how_to_give = DONATE_HOW
        donate.in_kind_giving = DONATE_IN_KIND
        self._save(donate, "Donate")

    def _settings(self):
        """Fill the Contact & Bank Details setting — only blank fields, never
        overwriting anything a human already entered. Settings have no
        draft/publish workflow, so this is written live."""
        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            return
        obj = ContactBankSettings.for_site(site)
        filled = []
        for field, value in BANK.items():
            if not getattr(obj, field, ""):
                setattr(obj, field, value)
                filled.append(field)
        if filled:
            obj.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"  set      Contact & bank details ({', '.join(filled)})"
                )
            )
        else:
            self.stdout.write("  exists   Contact & bank details (left as-is)")

        if obj.social_links.exists():
            self.stdout.write("  exists   Social links (left as-is)")
        else:
            for label, url in SOCIAL_LINKS:
                obj.social_links.add(SocialLink(label=label, url=url))
            obj.save()
            self.stdout.write(
                self.style.SUCCESS(f"  set      Social links ({len(SOCIAL_LINKS)})")
            )
