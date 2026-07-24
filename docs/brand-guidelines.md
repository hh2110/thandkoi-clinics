# Thandkoi Clinics — Brand Guidelines

_Last updated: 2026-07-24 · Status: draft for sign-off_

These guidelines define the visual identity for the website and all digital
material. **The logo is the authority** — all colours below are sampled from the
official logo (see [`brand/`](../brand/)).

> Earlier drafts inferred colours from the newsletters and drifted toward a deep
> pine-teal + mint + amber as general brand colours. The logo corrects this: the
> brand is a **mid teal-cyan** with a **coral-red** accent (cross/heart motif
> only) and a **pale-aqua** secondary. This document is now aligned to the logo.
> Amber reappears deliberately, as the Donate button colour and a short named
> list of homepage highlights (§2, widened 2026-07-24) — coral read as
> alarming for a donation ask; it is not a return to the earlier inferred
> palette.

## 1. Logo

The mark is a circular ring enclosing an illustrated family (mother, father,
swaddled child) with a red medical cross where the ring opens, above the wordmark
**THE / THANDKOI / CLINICS**.

<picture>
  <img alt="The Thandkoi Clinics logo" src="../brand/logo.svg" width="300">
</picture>

### Vector assets

The logo is also available as true vector (SVG), traced from
`brand/logo-primary.jpg`, transparent background.

| File | Use |
|---|---|
| [`brand/logo.svg`](../brand/logo.svg) | Full lockup — mark + wordmark. Used for print and design-reference contexts. |
| [`brand/logo-mark.svg`](../brand/logo-mark.svg) | Mark only, no wordmark. Square-ish crop, for contexts too narrow for the full lockup (social avatar, app icon). |
| [`brand/favicon.svg`](../brand/favicon.svg) / `favicon-32.png` / `favicon-180.png` / `favicon-512.png` | Browser tab / bookmark / home-screen icons. |

- **Clear space:** padding equal to the ring's stroke height around the mark.
- **Minimum size:** ~140px wide for the full lockup so the illustration stays
  legible.
- **Don't:** recolour, stretch, or add effects.
- **Known limitation:** the illustration has real detail (individual faces, a
  polka-dot pattern) that gets muddy at 32px — the 32px favicon export is
  usable but not crisp. If a cleaner tiny-icon treatment is ever needed,
  a deliberately simplified icon (ring + cross only) would read better than
  shrinking the full mark further.

### Header lockups (primary — use these for the live site)

2026-07-23: two rounds of trying to keep the full mark + wordmark lockup in
the header (first a recoloured `logo.svg`, then a recoloured
`logo-reversed.png`) both still read as two different logos across themes —
`logo.svg` and `logo-reversed.png` are traced from two different source
illustrations (different ring weight, colour saturation, proportions), and
matching the wordmark's contrast per theme was a recurring problem on top
of that. **Maintainer decision: drop the wordmark from the header and use
the mark (ring + family + cross) only.** The clinic's name stays visible
elsewhere on every page (site-footer's copyright line, and the page
`<title>`/OG tags), so this doesn't remove the only on-page name text —
it moves it out of the header specifically.

| File | Use |
|---|---|
| [`brand/logo-dark.png`](../brand/logo-dark.png) | Dark theme. A crop of `logo-reversed.png` with the wordmark rows removed — the same approved illustration, just less of the canvas. |
| [`brand/logo-light.svg`](../brand/logo-light.svg) | Light theme. Commissioned from an external design pass as a mark-only vector (not derived from any asset already in this repo) once recolouring attempts on the existing assets kept losing to the "two different logos" problem above. |

These two aren't pixel-derived from one another and have different
intrinsic aspect ratios (`logo-dark.png` ~1.24, `logo-light.svg` ~1.07);
`.site-header__logo` in `static/css/components.css` sizes both by a shared
*width* rather than height so they read as the same size regardless.

`brand/logo.svg` and `brand/logo-mark.svg` (an existing mark-only crop of
the `logo.svg` family) remain the vector source for print and any future
context that needs true vector (not raster) art — they are not currently
used on the live site, and `logo-mark.svg` in particular was not reused for
the header precisely because it inherits `logo.svg`'s "different
illustration than logo-reversed.png" problem.

## 2. Colour palette

All values sampled from `brand/logo-primary.jpg`.

### Core brand

| Token | Hex | Role |
|---|---|---|
| Teal Brand (primary) | `#086C7E` | The logo teal. Brand ground, dark sections, primary buttons (white text) |
| Teal Deep | `#0A3E48` | Footer / deepest ground; max-contrast text on light |
| Teal Bright | `#12879B` | Hover / active states |
| Pale Aqua | `#A0E0E8` | The "CLINICS" tone. Light accent + highlights **on dark** — not small text on light |
| Aqua Tint | `#E4F4F6` | Soft section backgrounds, dividers |

### Accent — coral (the cross & heart only)

| Token | Hex | Role |
|---|---|---|
| Coral | `#EF5148` | Brand accent; medical-cross & heart motif **only** — not for buttons or CTAs |
| Coral Deep | `#D83A30` | Coral fills / hover, where coral is used decoratively |
| Peach | `#F0B878` | Illustration warmth; optional soft wash. Decorative only |

### Accent — amber (Donate call-to-action, plus scoped highlights)

Coral read as alarming/negative for a donation ask, so Donate gets its own warm,
welcoming accent instead — coral stays reserved for the cross/heart motif.

| Token | Hex | Role |
|---|---|---|
| Amber (light) | `#CE8A2C` | **Primary Donate CTA** on light backgrounds |
| Amber (dark) | `#E8B04A` | **Primary Donate CTA** on dark backgrounds — lighter for contrast |

> **2026-07-24 (Plan 11 D12):** widened from Donate-only to a short, named
> list of homepage highlights (source: maintainer-supplied handoff
> `home-page-redesign.zip`, "Accent-color consistency"): the hero's "100%"
> donor-funded chip figure (was teal-on-`--color-surface` in dark mode,
> near-invisible — a genuine contrast bug, not just preference), the
> daily-report teaser's lead stat ("Patients seen"), and its "Read the full
> report →" link. Everything else (other stat figures, nav, eyebrows) stays
> teal — this is still a scoped exception, just a longer list than one. See
> §7's updated Do/Don't.

### Neutrals — light theme (cyan-teal biased, so they read as chosen)

| Token | Hex | Role |
|---|---|---|
| Ink | `#0E2025` | Primary text |
| Ink Soft | `#3E5257` | Secondary text |
| Ink Faint | `#728A8F` | Captions, meta |
| Border | `#E0E7E8` | Hairlines, card edges |
| Paper | `#F2F6F6` | Page background (light) |
| Card | `#FFFFFF` | Cards, panels |

### Neutrals — dark theme

The site has a **user-facing light/dark toggle** (not just dark-styled
sections like the footer), so the neutral scale needs a real dark pairing —
derived from the existing teal scale rather than a generic grey, so dark mode
still reads as this brand and not a default inverted theme.

| Token | Hex | Role | Derivation |
|---|---|---|---|
| Ink Dark | `#F2F6F6` | Primary text on dark | Reuses the **Paper** token — near-white, easier on the eyes than pure white |
| Ink Soft Dark | `#ABB4B6` | Secondary text on dark | Lightened **Ink Soft** |
| Ink Faint Dark | `#9EA0A1` | Captions, meta on dark | Lightened **Ink Faint** |
| Border Dark | `#195A67` | Hairlines, card edges on dark | Lightened + desaturated **Teal Deep** |
| Page Dark | `#0A3E48` | Page background (dark) | Reuses **Teal Deep** |
| Raised Dark | `#0B4753` | Full-bleed tinted bands (dark) — stat band, daily-report band | Between Page Dark and Card Dark |
| Card Dark | `#0D4F5C` | Cards, panels (dark) | Slightly lightened **Teal Deep**, for elevation contrast against Page Dark |
| Footer Dark | `#082D35` | Footer background (dark) | Darkened **Teal Deep** |

> **2026-07-24 (Plan 11 D12):** Page Dark, Raised Dark, and Card Dark were
> flat — `--color-accent-soft-bg` (Raised) resolved to the *same* value as
> Page Dark, so every "raised" band sat flush with the page background (the
> "everything collapses to one flat teal" bug the maintainer reported).
> Raised Dark is a new, genuinely-distinct value so the ladder (Footer <
> Page < Raised < Card) is monotonic. Footer Dark also used to reuse Page
> Dark outright ("the footer is visually one family" with the page,
> previous wording of this row) — now strictly darker, so the footer reads
> as the page's deepest anchor in dark mode too, matching what light mode
> already did (Footer `#0F3038` vs. Page `#F2F6F6`). Source: maintainer-
> supplied handoff `home-page-redesign.zip`.

Accent colours carry over largely as-is: Teal Brand, Pale Aqua, and Amber
(dark) `#E8B04A` were already designed to sit on a dark ground. Coral stays
decorative-only in both themes.

### Accessibility (WCAG AA) — read before using colour for text

- ✅ **Ink on Paper/Card** — the default for body text.
- ✅ **White on Teal Brand / Teal Deep** — safe for buttons and dark sections.
- ✅ **Teal Deep on white** — safe for links/headings; use Teal Deep (not Teal
  Brand) for small text on white to stay above 4.5:1.
- ⚠️ **Coral** — decorative use only (cross/heart motif); if ever used as a fill,
  use **Coral Deep** with **white bold ≥16px** text (large-text AA). Not for
  small body text on white.
- ⚠️ **Amber** — use **Amber (dark) `#E8B04A`** with dark ink text, or **Amber
  (light) `#CE8A2C`** with white text, to stay above 4.5:1 for the Donate CTA.
- ⚠️ **Pale Aqua / Peach** — decorative / on-dark only; never body text on light.
- ✅ **Ink Dark on Page Dark/Card Dark** — the dark-theme default for body text.
- "Free / Zakat beneficiary" badges use **Teal**, not a new colour.

Body text ≥16px; visible keyboard focus; both themes use their own re-tuned
token set (above) rather than a naive CSS invert.

## 3. Typography

The wordmark is a **bold sans**, so the type system is sans-forward. All faces are
open-source (SIL OFL), free, and self-hostable.

| Role | Typeface | Notes |
|---|---|---|
| Headings / display | **Archivo** (Bold/ExtraBold) | Wide grotesque matching the "THANDKOI" wordmark. Alt: Libre Franklin. |
| Body & UI | **Public Sans** (400/600) | Clean, screen-legible. Alt: Source Sans 3. |
| Data & report figures | Public Sans, `tabular-nums` | Aligns report columns. |
| Urdu (Nastaliq) | **Noto Nastaliq Urdu** | Headings/quotes: چراغ شفا, صحت سب کے لیے. |
| Urdu / Arabic (UI) | **Noto Naskh Arabic** | Inline labels where Nastaliq is too tall. |

Wordmark styling echoes the logo: small "THE", heavy "THANDKOI" in Teal Brand,
lighter "CLINICS" in Pale Aqua.

**Type scale** (1.25): 0.8 / 1.0 / 1.25 / 1.563 / 1.953 / 2.441 rem. Running text
~65 characters wide; `text-wrap: balance` on headings; uppercase labels ~0.14em
letter-spacing.

_Serif is optional for long-form editorial only; the default UI is sans._

## 4. Layout & spacing

- Base unit **8px** (compose 8/16/24/32/48/64).
- Generous whitespace; calm and uncluttered — healthcare, not retail.
- Cards: 12px radius, 1px Border, soft shadow.
- Reading pages ~720px wide; wider grids for galleries/reports.

## 5. Imagery

- Real clinic, camp, and community photography; warm, natural light.
- **Dignity & consent:** never publish identifiable patient images without
  explicit consent; prefer context shots where consent is unclear. (Brand rule
  *and* privacy rule.)
- The logo's family illustration is the signature graphic — use it rather than
  generic stock.

## 6. Voice & tone

- **Compassionate, dignified, clear.** Plain language, minimal jargon.
- **Community-first** and faith-respectful (Zakat, Sadaqa, sincerity).
- **Honest and specific** — real numbers and stories, no over-claiming.
- **Bilingual by default** — English and Urdu given equal care; Pashto may follow.

## 7. Do / Don't

- ✅ Anchor on Teal Brand; use Amber for the donate action and the short
  named list of homepage highlights (§2), Coral only for the cross/heart
  motif.
- ✅ Let whitespace and type carry the page.
- ✅ Give Urdu the same care as English (RTL, proper Nastaliq).
- ❌ Don't reintroduce navy/mint — they aren't in the logo.
- ❌ Don't use Amber beyond the Donate CTA and the §2 highlight list
  (2026-07-24, Plan 11 D12) — it's still a deliberate, scoped exception, not
  a general brand colour, just a longer list than one.
- ❌ Don't use Coral, Pale Aqua, or Peach for small body text.
- ❌ Don't add gradients, heavy shadows, or emoji as section markers.

## 8. Open items

- None outstanding — logo (vector, §1), colour palette incl. Donate accent
  (§2), and type direction (§3, Archivo + Public Sans) are all confirmed.
  This document can move from draft to final on sign-off.
