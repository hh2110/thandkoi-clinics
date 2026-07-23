# Plan 06 — Newsletters, Camp Reports & Gallery

_Status: Drafted · Depends on: 01 Project foundation, 03 Design system & base templates, 04 Core content pages · Next: 07 Accounts & roles_

## Goal

Three more content types, human-authored for now: a Newsletter archive, a
Camp Report archive, and a photo Gallery. This is the moment Home's "latest
report/newsletter" teaser (built pointing at nothing in Plan 04) starts
rendering for real, and the moment Plan 04's image-consent convention gets
its first actual use — camp/patient photography is exactly the case it was
built for.

**Not** the AI-drafting side of newsletters (Plan 09) or the data-pipeline-fed
daily/monthly Report pages (Plan 08) — see Scope. This plan only builds the
content types; Plan 09 later drafts *into* the Newsletter model this plan
creates, via `save_revision()` (a Wagtail draft, unpublished, same mechanism
a human uses), not a new model.

## Scope

**In scope**
- `NewsletterIndexPage` + `NewsletterPage` (archive + individual issues).
- `CampReportIndexPage` + `CampReportPage` (archive + individual camps) —
  date, location, patients-served figures, services offered, partner/
  volunteer credits, narrative body, photos.
- `GalleryPage` + orderable `GalleryImage` children (image, caption, the
  `consent_confirmed` field from Plan 04 — mandatory here, since this is
  where identifiable patient/camp photos actually appear).
- Wiring Home's report/newsletter teaser to query real `NewsletterPage`
  data (the *Report* half of that teaser still waits for Plan 08).

**Out of scope** (later plans)
- Auto-generated **daily/monthly Report pages** driven by the data pipeline
  → Plan 08. A Report page's entire purpose is displaying pipeline-computed
  numbers, so it doesn't make sense to build that model before the pipeline
  exists to fill it — building it here would mean guessing its shape twice.
- AI-drafted newsletter content → Plan 09. This plan's `NewsletterPage` is
  the target model Plan 09 drafts into; no AI code here.
- Urdu translations → out of scope for now (see the
  [plans README](README.md#out-of-scope-for-now) — Bilingual generation),
  same as every other content plan.
- Bulk/automated photo import — camp and gallery photos are added one at a
  time through the admin, same as any other Wagtail image upload.

## Source material

Same organisational profile PDF as Plans 04/05 (`The Thandkoi Clinics final
V15.pdf`) has one ready-to-use example, and confirms a gap:

- **p.11–13 — inauguration & first medical camp**: 16 May 2026, inaugurated
  by former National Assembly Speaker/MNA Asad Qaiser and DHO Swabi
  Dr Abdul Latif; 379 patients served free of cost across Pediatrics,
  Gynaecology, General Medicine, and Psychiatry; volunteer doctors from
  Khyber Teaching Hospital and Police & Services Hospital. This is a
  ready-made **first CampReportPage** — real dates, real numbers, real
  partner credits, already flagged for this purpose back in Plan 04.
- **p.16–17 — infrastructure photos**: consultation rooms, courtyard/
  entrance, pharmacy, main entrance, architecture, waiting areas — candidate
  Gallery images, though (as in Plan 04) the actual image files aren't
  extractable from this plan's text pass; originals or exports are needed.
- **No newsletter issues found in the source PDF** — it's an organisational
  profile, not a newsletter archive. If back-issues exist elsewhere (the
  architecture brief mentions the clinic "already produces newsletters"),
  they're a separate source to gather at content-entry time; none are ready
  to reference here.

As with Plans 04/05: this is reference material for the post-deploy
content-entry pass, not text this plan's PR commits to the repo — see Plan
04's "Where content lives: code vs. CMS" section, which applies unchanged
here.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Page structure | Index + child pages (Wagtail's standard archive pattern) for both Newsletter and Camp Report | Each issue/camp is independently linkable, shareable, and gets its own SEO metadata — unlike Plan 04's Team/Service children, these need real page-ness. |
| Gallery structure | One `GalleryPage`, orderable `GalleryImage` children (not separate pages) | Mirrors Plan 04's Team/Service pattern — gallery images don't need their own URL or preview. |
| Camp Report fields | Structured, not just a rich-text blob: date, location, **patients-served split by category** (e.g. children / general / Welfare-free-service — matching the PDF's own breakdown, with a derived total), services offered (list), partner credits (text/list), narrative body, photos | **Maintainer decision:** split patients-served by category rather than a single total — the clinic already tracks it that way. Structured category fields let a future plan aggregate across camps without re-parsing prose; costs nothing now since the source content is already this shape. |
| Consent field | `consent_confirmed` required (not just present) on every `GalleryImage` and every Camp Report photo before publish | Plan 04 introduced this as a convention; this is the plan where it's actually load-bearing — these are exactly the photos likely to show identifiable patients. |
| Home teaser wiring | Query the latest published `NewsletterPage`; leave the Report half of the teaser exactly as Plan 04 left it (hidden) until Plan 08 | Partial wiring is fine — the teaser was built to degrade gracefully per-content-type, not all-or-nothing. |

> **2026-07-23 update (branch `chore/remove-camp-upload-feature`):** the
> patients-served-by-category split, `services_offered`, and
> `partner_credits` described in the "Camp Report fields" row above were
> removed from `CampReportPage` entirely and replaced with a single optional
> `report_document` attachment field. Maintainer decision — moving away from
> a generic/structured-stats direction for this page. The camp-upload flow
> (Plan 11 Track C3) that once auto-parsed camp exports into this archive
> was also removed in the same branch; `CampReportPage` is hand-authored
> only again.

## Proposed page tree additions

```
HomePage
├── ...(existing from Plan 04)
├── NewsletterIndexPage
│   └── NewsletterPage (repeated)
├── CampReportIndexPage
│   └── CampReportPage (repeated)
│       └── (photos — via a gallery/image StreamField block, not child pages)
└── GalleryPage
    └── (GalleryImage — Orderable child, not a Page)
```

## Feature flag

**No flag** — deliberate. Two gates already do the work a flag would: **Wagtail's
draft/publish** (archives list only *published* items; drafts are invisible, and
this plan adds a test for exactly that) and the **`consent_confirmed` publish
block** on any identifiable photo. New content-type models are inert additive
migrations until an admin creates and publishes an item. Nav/footer links are
added only now that the sections exist. Ships on merge + deploy; content entered
post-deploy.

## Precedent map

New-repo note: Plan 04 is merged by now, so the child-object, consent, and teaser
patterns have in-repo precedent; the **index + child *page*** archive pattern is
new to the repo and grounded against Wagtail's standard idiom.

| Element | Precedent to mirror | Where |
|---|---|---|
| Orderable `GalleryImage` children | Plan 04's `TeamMember`/`Service` `Orderable` child pattern | Plan 04 (in repo) |
| `consent_confirmed` on photos (now load-bearing) | Plan 04's consent convention (first real use here) | Plan 04 (in repo) |
| Home teaser wiring (query latest published) | Plan 04's conditionally-rendered teaser | Plan 04 (in repo) |
| `StreamField` bodies | Plan 04's Home `StreamField` blocks | Plan 04 (in repo) |
| Archive/listing/detail templates | Plan 03.5 section partials + Plan 03 `base.html` | Plans 03/03.5 (in repo) |
| **Index + child-page archive pattern** (`NewsletterIndexPage`→`NewsletterPage`, `CampReportIndexPage`→`CampReportPage`) | **No in-repo precedent** — ground against Wagtail's standard index/child archive idiom (independently linkable, own SEO) | Wagtail docs (best practice) |
| **Structured Camp Report fields** (patients-served split by category) | **No precedent** — grounded in the maintainer decision + the PDF's own breakdown, not invented | maintainer decision |
| Draft-visibility test (foundation for Plan 09) | Grounds on Wagtail's live/draft mechanism | Wagtail (best practice) |

## Task checklist (code — this plan's PR)

1. **Newsletter models** — `NewsletterIndexPage` (lists children, newest
   first) + `NewsletterPage` (issue date, `StreamField` body for rich
   content + inline images).
2. **Camp Report models** — `CampReportIndexPage` + `CampReportPage` (date,
   location, **patients-served as per-category integer fields** — e.g.
   children / general / Welfare-free-service — with the total derived from
   them rather than entered separately, services-offered list,
   partner-credits field, narrative `RichTextField`/`StreamField`, photo
   block using the consent-required image pattern).
3. **Gallery model** — `GalleryPage` + `GalleryImage` orderable child
   (image, caption, `consent_confirmed`).
4. **Templates** — archive/listing templates (newest-first, paginated if long)
   and individual-item templates for both Newsletter and Camp Report;
   Gallery grid template.
5. **Home teaser wiring** — replace the "renders nothing" query from Plan 04
   with a real "latest published `NewsletterPage`" query; leave Report
   untouched (still nothing to query).
6. **Nav/footer** — add real links now that these sections exist (was
   placeholder/404 since Plan 03).
7. **Tests** — smoke tests per new page type; a test that an unpublished
   (draft) Newsletter/Camp Report does **not** appear in the archive listing
   or Home's teaser (this is the exact mechanism Plan 09's AI-drafted
   content will rely on later — worth locking down now while it's cheap to
   test); a test that a `GalleryImage`/Camp Report photo without
   `consent_confirmed` can't be published.

## Content entry checklist (post-deploy, via Wagtail admin — not part of this PR)

1. First `CampReportPage`: the 16 May 2026 inauguration/camp story (p.11–13)
   — real content, ready to enter as-is.
2. Gallery images from infrastructure photos (p.16–17) once the actual image
   files are available.
3. First newsletter issue(s), whenever source content exists (none found in
   the PDF — separate gathering step).

## Acceptance criteria

- Newsletter and Camp Report archives list only published items, newest
  first; draft items are invisible to public visitors.
- Home's teaser renders the latest published newsletter once one exists,
  with zero code change from what Plan 04 shipped.
- No `GalleryImage` or Camp Report photo can be published without
  `consent_confirmed` ticked.
- `ruff check` and `pytest` (including the draft-visibility and consent
  tests) pass in CI.

## Resolved questions (answered by the maintainer)

- **Newsletter back-issues** → **yes, they exist** and will populate the
  archive: the `NewsletterIndexPage` is built to hold back-issues, entered as
  a content-entry step once the source files are gathered (the org-profile
  PDF isn't the source — see "Source material" above). The archive is not
  assumed to start empty at launch.
- **Camp Report "patients served"** → **split by category** (e.g. children /
  general / Welfare-free-service), matching the PDF's own breakdown, with the
  total derived — not a single lumped figure. Reflected in the Camp Report
  fields decision and task checklist above.

## Release plan

- **How it ships:** merge → additive migrations → deploy pipeline (staging →
  verify → production). Post-deploy content steps: the first `CampReportPage`
  (16 May 2026 inauguration, ready-to-enter), gallery images once the actual
  image files are gathered, and newsletter back-issues as their sources are
  gathered. Add the real nav/footer links (previously placeholder) as part of
  the ship.
- **Gating check:** the **draft-visibility** test (drafts invisible in archives
  and Home's teaser) and the **consent** test (no photo publishes without
  `consent_confirmed`) green in CI; on staging, confirm archives list published
  items newest-first and Home's teaser renders the latest published newsletter.
- **Privacy note (load-bearing here):** this is where identifiable patient/camp
  photos first appear. The `consent_confirmed` block is a **privacy gate, not
  just a feature gate** — no image ships without it, per brand-guidelines.md §5.
- **Who gets access:** the public (everyone), published items only.
- **Who's informed:** maintainer **and the other Administrators** — they enter
  content *and* must understand the consent gate before uploading any camp/
  patient photo. Brief them on the consent rule specifically, not just the pages.
- **Rollback trigger:** unpublish any item in the admin (instant); code revert
  for a model/migration defect. A consent concern about a live photo is an
  immediate unpublish, no redeploy.
