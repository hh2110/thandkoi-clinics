# Plan 04 — Core Content Pages

_Status: Drafted · Depends on: 01 Project foundation, 03 Design system & base templates · Next: 05 Donate placeholder_

## Goal

The first real content on the site: Home, About, Team/Management, Our Work
(services), and Contact, as editable Wagtail pages a non-technical admin can
update without touching code. English content only — this step is "the
shopfront exists and looks right," not the full nine-page structure from
[architecture-and-ai-brief.md §5](../../docs/architecture-and-ai-brief.md).

This plan ships with **real launch copy**, not placeholder text — see
"Source material" below.

## Source material

The maintainer's organisational profile PDF (`The Thandkoi Clinics final
V15.pdf`, 20 pages) has real, ready-to-use copy for every page in this plan.
Page references below are to that PDF so the implementer can pull exact
wording rather than paraphrase from this plan:

- **p.5 — "Our Message"**: founders' welcome message/quote (Dr Amanullah,
  Dr Kausar Khurshid) — good About-page intro or pull-quote.
- **p.6 — Vision / Mission / Objectives**: three short blocks, verbatim-ready
  for the About page's corresponding `RichTextField`s.
- **p.7 — Quality of Care circle**: one paragraph, for About.
- **p.8–10 — "Meet Our Team"**: the real roster, two groups —
  - *Doctors*: Dr Khadija Amanullah, Dr Amanullah, Abdul Azim, Dr Kausar
    Khurshid, Dr Yusra Amanullah, Dr Mubaraka Amanullah, Dr Saifullah Khan,
    Dr Hikmatyar Hasan, Dr Javeria Khan, Syed Dawood Shah.
  - *Staff & Committee*: Dr Ammar Fayyaz (In-charge Medical Officer), Ataullah
    Khan (Health & Zakat Committee Chair), Shaheera Hayat (Advocacy &
    Communications Officer), Mohammad Amir (Health & Zakat Committee Member),
    Umar Jan (Logistics & Accounts Assistant), Mohammad Khalid (Health &
    Zakat Committee Member), Siraj Ahmad Lodhi (Finance & Admin Officer).
  - Plus a short "united by a shared commitment…" team paragraph (p.10) for
    the Team page intro. **Photos aren't in the extractable text** — check
    the PDF's images or ask the maintainer for headshots per person.
- **p.11–13 — Inauguration & first medical camp**: 16 May 2026, inaugurated
  by former National Assembly Speaker/MNA Asad Qaiser and DHO Swabi
  Dr Abdul Latif; a free camp the same day served 379 patients across
  Pediatrics, Gynaecology, General Medicine, and Psychiatry, with volunteer
  doctors from Khyber Teaching Hospital and Police & Services Hospital. This
  is the clinic's founding story — belongs on About; may later seed the
  *first* Camp Report once Plan 06 exists.
- **p.14 — Patients served (as of PDF publication)**: 467+ children
  seen/treated, 189 patients served at the clinic, 426 served under Welfare
  (free service). Good **starting values** for Home's admin-editable impact
  stats — the admin should update these at launch to whatever's current,
  since the PDF numbers age the moment they're entered.
- **p.15 — Specialized Services**: Telemedicine, Health Education, Capacity
  Building & Community Engagement, Medications, Emergency Care, Women's
  Health Unit, Regular Check-ups — all **currently active**. Laboratory &
  Pharmacy and Radiology/Imaging are explicitly listed as **"aiming to
  introduce"** — i.e. planned, not live yet. The Service model should carry
  this distinction (see decisions table) rather than presenting aspirational
  services as already available.
- **p.16–17 — Our Infrastructure**: a bullet list (reception/triage, waiting
  areas, consultation rooms, on-site pharmacy, immunisation, digital health
  records, infection control) plus photo captions (consultation rooms,
  courtyard/entrance, pharmacy, main entrance, architecture, waiting areas) —
  for Our Work's infrastructure section. Photos are in the PDF; extract or
  request originals.
- **p.18 — "Giving with Purpose"**: donation mission paragraph — reference
  for **Plan 05** (Donate), not built this step, but worth carrying forward
  so it isn't re-sourced later.
- **p.19–20 — Contact & bank details**: phone `+92 344 4111235`, social
  `@thandkoi.clinics`, email `info.thandkoiclinics@gmail.com`, plus full bank
  account details for Zakat/Sadaqa donations (account title, IBAN, account
  number, branch code, branch name). **Not reproduced in this file** — per
  the architecture brief's "configured in the running application, not
  stored in this repository" decision (see the Contact & Bank Details
  setting below), these get entered directly into the Wagtail admin at
  build time, straight from the PDF. The phone/email/social are low-
  sensitivity public contact channels either way; the bank details are the
  reason this whole setting exists rather than being template constants.

## Scope

**In scope**
- Wagtail page models + templates for: Home, About, Team/Management, Our Work
  (services), Contact.
- A site-wide **Contact & Bank Details** setting (singleton, Wagtail admin
  editable) — the architecture brief is explicit that these are "configured
  in the running application, not stored in this repository," so they can't
  be a fixture or a hardcoded template value.
- Team members and services as orderable child content, editable without a
  developer (add/remove/reorder in the Wagtail admin).
- Wiring Plan 03's footer/header placeholders to real data (nav links that
  resolve, footer contact block pulling from the new setting).

**Out of scope** (later plans)
- Donate page itself → Plan 05 (Home's donate CTA links to it once it exists;
  built as a configurable link so it doesn't hard-fail before Plan 05 lands).
  The source PDF's "Giving with Purpose" copy (p.18) is noted above for
  reuse there.
- Reports, Newsletters, Gallery pages → Plan 06 (Home's "latest report/
  newsletter" teaser is built to degrade gracefully — hidden, not broken —
  until that content type exists). The inauguration/first-camp story (p.11–13)
  may become the first real Camp Report then.
- Urdu translations of this content → Plan 10. Models are built so adding
  translated locales later (via Wagtail's i18n / `wagtail-localize`) doesn't
  require reshaping them, but no Urdu content is written this step.
- Real impact numbers driven by the data pipeline → Plan 08/09. Home's
  "impact numbers" are admin-editable static figures for now (seeded from
  p.14's real counts at launch), not computed.
- Team member and infrastructure **photos** — the source PDF has them as
  images, not extractable as files from this plan's text-extraction pass;
  getting the actual photo assets (or requesting fresh ones) is a launch
  task, not a plan decision.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Content modelling | Standard Wagtail fields (`RichTextField`, `StreamField` where flexibility is actually needed) | Predictable pages (About, Contact) use plain fields; Home uses a `StreamField` body so Plan 05/06 can add new block types (donate CTA, report teaser) without restructuring the page model. |
| Team members | `Orderable` child model on `TeamPage` (django-modelcluster pattern) — name, role, category (**Doctors** / **Staff & Committee**, matching the real roster), photo, short bio | Standard Wagtail idiom; admin adds/reorders team members inline on the Team page, no separate admin screen to learn. Categories match the source PDF's actual two groupings, not a generic Founders/Officers/Committee guess. |
| Services | Same `Orderable` child pattern on `OurWorkPage` — name, short description, icon/image, **status** (`Active` / `Planned`) | Mirrors Team's pattern so there's one convention, not two. The status field exists because the real service list has two "aiming to introduce" entries (Laboratory & Pharmacy, Radiology/Imaging) — the template must not present those as already available. |
| Contact & bank details | `wagtail.contrib.settings` `BaseSiteSetting` singleton — phone, email, socials, bank account details, address/map | Editable in Wagtail admin under Settings; consumed by both the Contact page and Plan 03's footer partial. This is what makes it "configured in the running app," not committed to the repo. |
| Home's donate CTA | A Wagtail `PageChooserBlock`/URL field, not a hardcoded link | Points at nothing (hidden) until Plan 05 exists, then an admin points it at the real Donate page — no code change needed to wire it up. |
| Home's report/newsletter teaser | Conditionally rendered — queries for a "latest published" item of that content type; renders nothing if none exists | Avoids a broken or empty-looking section before Plan 06 ships, and avoids the Home template needing a code change when Plan 06 lands (it starts rendering the moment content exists). |
| Images & consent | Every image field requires alt text (Wagtail supports this natively); any photo of an identifiable person outside of staff/team gets a `consent_confirmed` checkbox the admin must tick before publish | Establishes the convention now (staff/team photos are implicitly consented — they're employees, in a professional context) so Plan 06 (camp/patient photography) reuses it rather than inventing a second pattern later. Per brand-guidelines.md §5's dignity & consent rule. |

## Proposed page tree

```
HomePage (from Plan 01, replaced with real content)
├── AboutPage
├── TeamPage
│   └── (TeamMember — Orderable child, not a Page)
├── OurWorkPage
│   └── (Service — Orderable child, not a Page)
└── ContactPage
```

Team members and services are child *objects*, not child *pages* — they don't
need their own URL, preview, or SEO metadata, so modelling them as Wagtail
pages would be overhead the admin has to navigate around for no benefit.

## Task checklist

1. **Contact & Bank Details setting** — `apps/core` (or a new `apps/settings`
   app): a `BaseSiteSetting` with phone, email, socials (list), bank account
   details (fields, not free text, so they render consistently), address, and
   an optional map embed URL. Register in the Wagtail admin.
2. **Home page** — extend the Plan 01 placeholder: `StreamField` body with a
   `HeroBlock` (mission statement), `ImpactStatsBlock` (admin-editable number
   + label pairs), `DonateCTABlock` (link field, renders nothing if unset),
   and a "latest report/newsletter" teaser section (queries, renders nothing
   if no matching content exists yet).
3. **About page** — `RichTextField`s for vision, mission, objectives,
   quality-of-care model, and the founding/inauguration story, populated
   from source PDF p.5–7 and p.11–13 (see Source material above); a simple
   `StreamField` or child-list for partner logos/names if there are any at
   launch.
4. **Team page** — `TeamPage` + `TeamMember` orderable child model (name,
   role, category, photo w/ required alt text, short bio); template groups
   members by category (Doctors, Staff & Committee); populated from the real
   roster (p.8–10) — photos still needed as a separate asset task.
5. **Our Work page** — `OurWorkPage` + `Service` orderable child model (name,
   description, icon/image, status); template renders as a grid/list per
   brand-guidelines.md §4 layout rules, visually distinguishing `Planned`
   services (e.g. a "coming soon" tag) from `Active` ones; populated from
   the real service list and infrastructure section (p.15–17).
6. **Contact page** — renders the Contact & Bank Details setting; a simple
   "email us" `mailto:` link rather than a contact form (no form backend
   needed at this stage — matches "no analytics or third-party scripts by
   default" from CLAUDE.md's privacy guardrails, and avoids a spam-handling
   problem for a 2–4-person admin team).
7. **Wire up Plan 03's shell** — primary nav links resolve to the real pages;
   footer partial pulls from the Contact & Bank Details setting instead of
   placeholder text.
8. **Consent convention** — a reusable image-field pattern (custom block or
   model mixin) with the `consent_confirmed` checkbox described above, used
   wherever a non-staff person could appear in a photo.
9. **Tests** — smoke tests per page (renders 200, correct template used);
   a test that the Contact page reflects a change to the setting; a test
   that Home's donate CTA and report teaser are absent/hidden when unset
   rather than broken.

## Acceptance criteria

- All five pages are creatable in the Wagtail admin, render correctly, and
  are reachable from the primary nav.
- Editing the Contact & Bank Details setting changes both the Contact page
  and the footer, with no code change or redeploy.
- Team members and services can be added, removed, and reordered from the
  Wagtail admin without a developer.
- Home renders correctly with the donate CTA and report teaser both unset
  (current state) — no broken links, no empty-looking placeholder boxes.
- Every image has alt text; any non-staff person photo has a ticked
  `consent_confirmed` field before it can be published.
- `ruff check` and `pytest` (including the new page/setting tests) pass in
  CI.

## Resolved (was open questions)

- **Real content for About/Team/Our Work**: resolved — sourced from the
  organisational profile PDF (see "Source material" above), not placeholder
  copy.
- **Team categories**: resolved — Doctors / Staff & Committee, matching the
  PDF's actual grouping (not the earlier Founders/Officers/Committee guess).

## Open questions for the maintainer

- Team member and infrastructure **photos** — the PDF's images aren't
  pulled out by this plan's text extraction; are originals available
  separately, or should this launch with placeholder/generic imagery for
  people missing a photo?
- Bank details are ready in the source PDF (p.19) to enter into the Contact
  & Bank Details setting — confirm these are still current before they go
  live (organisational documents can lag real account changes).
