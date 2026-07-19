# Plan 04 — Core Content Pages

_Status: Drafted · Depends on: 01 Project foundation, 03 Design system & base templates · Next: 05 Donate placeholder_

## Goal

The first real content on the site: Home, About, Team/Management, Our Work
(services), and Contact, as editable Wagtail pages a non-technical admin can
update without touching code. English content only — this step is "the
shopfront exists and looks right," not the full nine-page structure from
[architecture-and-ai-brief.md §5](../../docs/architecture-and-ai-brief.md).

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
- Reports, Newsletters, Gallery pages → Plan 06 (Home's "latest report/
  newsletter" teaser is built to degrade gracefully — hidden, not broken —
  until that content type exists).
- Urdu translations of this content → Plan 10. Models are built so adding
  translated locales later (via Wagtail's i18n / `wagtail-localize`) doesn't
  require reshaping them, but no Urdu content is written this step.
- Real impact numbers driven by the data pipeline → Plan 08/09. Home's
  "impact numbers" are admin-editable static figures for now, not computed.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Content modelling | Standard Wagtail fields (`RichTextField`, `StreamField` where flexibility is actually needed) | Predictable pages (About, Contact) use plain fields; Home uses a `StreamField` body so Plan 05/06 can add new block types (donate CTA, report teaser) without restructuring the page model. |
| Team members | `Orderable` child model on `TeamPage` (django-modelcluster pattern) — name, role, category (Founder/Officer/Committee), photo, short bio | Standard Wagtail idiom; admin adds/reorders team members inline on the Team page, no separate admin screen to learn. |
| Services | Same `Orderable` child pattern on `OurWorkPage` — name, short description, icon/image | Mirrors Team's pattern so there's one convention, not two. |
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
   quality-of-care model; a simple `StreamField` or child-list for partner
   logos/names if there are any at launch.
4. **Team page** — `TeamPage` + `TeamMember` orderable child model (name,
   role, category, photo w/ required alt text, short bio); template groups
   members by category (Founders, Officers, Committee).
5. **Our Work page** — `OurWorkPage` + `Service` orderable child model (name,
   description, icon/image); template renders as a grid/list per
   brand-guidelines.md §4 layout rules.
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

## Open questions for the maintainer

- Real content for About/Team/Our Work — do you have existing copy (from the
  newsletters/organisational profile mentioned in the architecture brief) to
  adapt, or should placeholder copy ship first and get replaced later?
- Team member list and categories (Founders/Officers/Committee) — confirm
  this grouping matches how the clinic actually organises its people.
- Bank details for the Contact & Bank Details setting — these will live in
  the Wagtail admin (not this repo), but confirm someone has them ready to
  enter once Plan 04 ships.
