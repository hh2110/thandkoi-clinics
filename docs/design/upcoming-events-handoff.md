# Handoff: "Upcoming events" home-page card

Design bundle received 2026-07-29 (maintainer's family/stakeholder feedback
group — see [Plan 19](../../.claude/plans/19-family-network-feedback-2026-07.md)).
Matches the format of
[`clinic-dashboard-handoff.md`](clinic-dashboard-handoff.md) /
[`mobile-menu-handoff.md`](mobile-menu-handoff.md). All claims below (tokens,
files, classes) were verified against the real repo before implementation
started, per this project's Stage 3 grounding discipline.

## Overview

A family stakeholder asked for a way to announce an upcoming event on the
home page (first case: the free medical camp on **6 August 2026**) — today,
camps only appear *after the fact*, as data-driven daily/camp reports. This
adds a small, teaser-style **"Upcoming events"** element to the home page,
following the same shape as the site's other home-page teasers (latest daily
report, latest newsletter): render only when there is something to show,
hide gracefully otherwise.

**Approved: option 1b** — a single card tucked into the hero photo's corner,
mirroring the existing floating stat card (`.hero__stat-card`). Chosen over
1a (its own section under the hero) since the clinic doesn't expect to run
many events at once. It auto-hides once the event's date has passed. Option
1a is kept for reference only, in case the clinic ever runs several events at
once.

## Reconciling the bundle's own internal inconsistency

The design source (`Upcoming Events Options.dc.html`) states 1b is approved
and shows **exactly one event** in its screenshot
(`1b-hero-corner-card.png`) — no list, no dividers. But the same document's
generic "The card — states" section (3-event state, dividers) and its
Checklist (a new `partials/sections/upcoming_events.html` section partial,
"rows" plural) describe **1a's** section-card, not 1b's corner card. Read
literally, the checklist would build the un-approved option.

**Decision (Stage 7):** build what's approved — 1b, single event, no new
section partial. The 3-event/dividers/list-row treatment and the standalone
`upcoming_events.html` partial are 1a-only and **not built now** — revisit
only if the clinic ever needs to show more than one event at a time (the
corner card doesn't scale past one, by the bundle's own admission). The
underlying data model still supports many `UpcomingEvent` rows (so a future
1a build is a template-only change), but the home page only ever queries and
renders the single soonest one.

## Gap: no mobile screenshot of the approved option (found + fixed)

The bundle's file list includes a desktop-only screenshot of 1b
(`1b-hero-corner-card.png`); `flow-3-mobile.png` is the *lightbox* at mobile
width, not the corner card itself. The doc's mobile guidance ("render the
same card as a block directly below the hero's text column, not floating")
was asserted but not demonstrated — and a live 390px check (iframe harness
against a static snapshot; `resize_window` doesn't affect the real viewport)
caught a real bug from it: making only the new card static left it
overlapping `.hero__stat-card` ("100%"), which stayed absolutely positioned
and bottom-anchored to a `.hero__media` that was now taller. Fixed by giving
both cards the same static, stacked mobile treatment (`layout.css`'s
combined `.hero__stat-card, .events-teaser__card` media-query rule) —
confirmed live afterwards, both cards stack cleanly below the image with no
overlap, in both languages/directions.

## About the design file

`Upcoming Events Options.dc.html` (in the original bundle, not copied into
this repo — a prototype, not production code) is a design reference — all
colours are literal hex for portability; implemented with tokens per the
mapping table below, never the hexes.

## Placement — reconciling "a column on the side" with a single-column site

The site has no persistent sidebar anywhere (every page is `.section` +
`.wrapper`, full-bleed bands stacked top to bottom). **1b (approved):**
extends `.hero__stat-card` with a second floating card at the media's
trailing edge (`inset-inline-end`), holding one event: date, title, and —
when a flyer is set — a "View the flyer ↗" affordance opening the shared
lightbox. Renders only while `date >= today`.

## The card — states (1b, as built)

- **1 event:** the corner card renders with the date badge (day + month,
  stacked, aqua-tint box), title, and description.
- **0 events:** the card (and the whole event-related markup) is omitted
  entirely — no placeholder. Matches the existing pattern already on this
  page: the daily-report/newsletter teasers "each render beneath it only
  when that content type has a published item" (`home_page.html`'s own
  docstring).
- **2+ events exist in the admin:** only the single soonest (`date__gte
  =today`, ascending, first row) renders. No count/list chrome — this is the
  approved 1b behaviour, not a limitation to fix later.

### Row interaction states
- **No link, no flyer:** plain text, not clickable, default cursor.
- **`link_url` set:** the whole card becomes an `<a>`. Hover →
  `var(--color-accent-soft-bg)` (same aqua-tint hover as
  `.stat-band__link-card:hover` in `layout.css`). Focus →
  `var(--color-focus-ring)` outline.
- **`flyer` set instead:** the card becomes a `[data-lightbox-trigger]`
  (mutually exclusive with `link_url` — a card shows one affordance, not
  both), reusing `templates/partials/lightbox.html` +
  `static/js/lightbox.js` exactly as `media_grid.html`'s gallery photos do.
- No amber anywhere in this card — amber stays exclusively the Donate button
  (`docs/brand-guidelines.md` §7).

## Design tokens used (all existing — verified in `static/css/tokens.css`)

| Token | Role here |
|---|---|
| `--color-brand` | Date-badge day number |
| `--color-accent-soft-bg` | Date-badge background, link hover |
| `--color-surface` | Card background |
| `--color-border-default` | Card border, date-badge border |
| `--color-text` | Event title |
| `--color-text-soft` | Month label, description |
| `--card-shadow` | Card shadow |
| `--color-focus-ring` | Keyboard focus |

Nothing new — every value already exists in `tokens.css`.

## Data shape

```python
class UpcomingEvent(models.Model):
    date = models.DateField()
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=160, blank=True)
    link_url = models.URLField(blank=True)
    flyer = models.ForeignKey("wagtailimages.Image", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="+")
```

A Wagtail **snippet**, not a StreamField block on `HomePage` — the home-page
query needs to filter (`date >= today`) and order (`date` ascending) live.
Query: `UpcomingEvent.objects.filter(date__gte=today).order_by("date").first()`
(single row for 1b — see reconciliation above; the model stays list-capable
for a future 1a revisit).

**Deliberately no photo-per-event field** — future events don't have a photo
by definition; a photo field would pressure editors to source one for
content that hasn't happened. The flyer is a designed graphic, not identifiable
community/patient photography, so `docs/brand-guidelines.md` §5's photo-consent
gate does not apply to it (mirrors how `ConsentedImageBlock` is *not* reused
here).

## Interaction flow — clicking the card

1. When the event has a flyer image, the card becomes a
   `[data-lightbox-trigger]` with `data-lightbox-src`/`data-lightbox-alt`
   pointing at the flyer's `original` rendition (an uncropped designed
   graphic, unlike `ConsentedImageBlock` photos elsewhere on the site), plus
   a "View the flyer ↗" affordance line.
2. Clicking/tapping opens the same shared `<dialog id="lightbox">` already on
   every page — no new dialog, no new JS.
3. No flyer, `link_url` set instead → an ordinary link. Neither set → plain
   text.

## Copy (first real entry)

- Eyebrow: "Upcoming"
- 6 Aug 2026, "Free medical camp — Thandkoi", "Consultations, medicines and
  specialist care for the whole community. No appointment needed."

Urdu translations required for the heading/eyebrow at minimum
(`{% translate %}`), matching every other user-facing string on the site.

## Files in this bundle

| File | What it is |
|---|---|
| `1b-hero-corner-card.png` | **Approved.** The hero corner card, desktop, light theme |
| `flow-1-row-affordance.png` | The "View the flyer ↗" affordance |
| `flow-2-lightbox-desktop.png` | The shared lightbox open on the flyer, desktop |
| `flow-3-mobile.png` | The same lightbox, mobile width |
| `1a-reference-desktop-light.png`, `1a-reference-desktop-dark.png`, `1a-reference-mobile.png`, `1a-one-event-state.png` | Reference-only option (not built) — kept in case the clinic ever needs several events at once |
