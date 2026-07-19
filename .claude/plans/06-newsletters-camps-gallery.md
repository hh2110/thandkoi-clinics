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
| Camp Report fields | Structured, not just a rich-text blob: date, location, patients-served (number), services offered (list), partner credits (text/list), narrative body, photos | Structured fields let a future plan (if ever wanted) aggregate across camps without re-parsing prose; costs nothing now since the source content is already this shape. |
| Consent field | `consent_confirmed` required (not just present) on every `GalleryImage` and every Camp Report photo before publish | Plan 04 introduced this as a convention; this is the plan where it's actually load-bearing — these are exactly the photos likely to show identifiable patients. |
| Home teaser wiring | Query the latest published `NewsletterPage`; leave the Report half of the teaser exactly as Plan 04 left it (hidden) until Plan 08 | Partial wiring is fine — the teaser was built to degrade gracefully per-content-type, not all-or-nothing. |

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

## Task checklist (code — this plan's PR)

1. **Newsletter models** — `NewsletterIndexPage` (lists children, newest
   first) + `NewsletterPage` (issue date, `StreamField` body for rich
   content + inline images).
2. **Camp Report models** — `CampReportIndexPage` + `CampReportPage` (date,
   location, patients-served integer field(s), services-offered list,
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

## Open questions for the maintainer

- Do back-issues of the existing newsletters (mentioned in the architecture
  brief as already produced) exist as files somewhere, or does the archive
  start empty at launch?
- Camp Report "patients served" — one total figure, or split by category
  like the PDF's own numbers (e.g. children vs. general vs. Welfare/free
  service)? The PDF suggests the clinic already tracks it by category.
