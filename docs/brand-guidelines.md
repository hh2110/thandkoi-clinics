# Thandkoi Clinics — Brand Guidelines

_Last updated: 2026-07-19 · Status: draft for sign-off_

These guidelines define the visual identity for the website and all digital
material. Colours and motifs are derived from the clinic's existing newsletter
and organisational profile, then unified into one intentional system.

> **Note on brand drift:** the existing materials used three different anchors —
> a royal navy (`#073a70`), a muted teal (`#467d8b`), and a deep teal-green with
> mint (`#094a46` / `#5fbfb8`). This system standardises on **deep teal** (the
> most recent and most healthcare-appropriate direction), keeps the **navy** as a
> heritage/logo colour, and adds a warm **amber** drawn from the چراغ (lamp) motif.

## 1. Colour palette

### Core brand

| Token | Hex | Role |
|---|---|---|
| Teal Deep (primary) | `#0A4A46` | Brand anchor; dark grounds; primary buttons (white text) |
| Teal | `#0F6E6A` | Links, section headers on light, secondary emphasis |
| Teal Bright | `#1A8C86` | Hover / active states |
| Mint (accent) | `#5FBFB8` | Accents, motifs, highlights **on dark** — not body text on light |
| Mint Pale | `#E8F0EF` | Section tints, subtle backgrounds, dividers |

### Heritage

| Token | Hex | Role |
|---|---|---|
| Heritage Navy | `#073A70` | Logo lockup and occasional deep accent only |

### Warm accent — the چراغ (lamp of healing)

| Token | Hex | Role |
|---|---|---|
| Amber (donate) | `#C0851F` | Donate call-to-action fills + lamp motif; use **sparingly** |
| Amber Soft | `#E6B45A` | Dark-theme accent variant |

### Semantic / support

| Token | Hex | Role |
|---|---|---|
| Zakat Green | `#3F7D5A` | "Free / Zakat beneficiary / verified" badges (large text only) |
| Care Red | `#B34739` | Heart & medical-cross motif; alerts. Minimal use |

### Neutrals (teal-biased, so they read as chosen, not default)

| Token | Hex | Role |
|---|---|---|
| Ink | `#12211F` | Primary text |
| Ink Soft | `#41514F` | Secondary text |
| Ink Faint | `#77908C` | Captions, meta |
| Border | `#E2E8E6` | Hairlines, card edges |
| Paper | `#F3F6F5` | Page background (light) |
| Card | `#FFFFFF` | Cards, panels |

### Accessibility (WCAG AA) — read before using colour for text

- ✅ **Ink on Paper/Card** — high contrast; the default for body text.
- ✅ **White on Teal Deep** — safe for buttons, headers, dark sections.
- ✅ **Teal on white** — passes for links and normal text.
- ⚠️ **Amber on white** — fails AA for small text. Use amber as a **fill** with
  dark Ink text on top, or for icons/large text only.
- ⚠️ **Mint on white** — decorative only; never body text on a light ground.
- ⚠️ **Zakat Green / Care Red on white** — badges and large text only.

Always keep body text ≥ 16px, provide visible keyboard focus states, and design
both light and dark themes (don't naively invert — re-tune each token).

## 2. Typography

All faces are open-source (SIL OFL), free, and **self-hostable** — important for a
charity and for a strict content-security policy.

| Role | Typeface | Notes |
|---|---|---|
| Headings / display | **Source Serif 4** | Warm, dignified, editorial. Weight 600. |
| Body & UI | **Source Sans 3** | Clean, screen-legible. Weights 400/600. |
| Data & report figures | **Source Sans 3**, `tabular-nums` | Aligns columns in reports. |
| Urdu (Nastaliq) | **Noto Nastaliq Urdu** | For headings/quotes: چراغ شفا, صحت سب کے لیے. |
| Urdu / Arabic (UI) | **Noto Naskh Arabic** | For inline labels where Nastaliq is too tall. |

_Alternative all-sans pairing, if preferred: Headings **Libre Franklin**, Body
**Public Sans**._

**Type scale** (1.25 ratio): 0.8 / 1.0 / 1.25 / 1.563 / 1.953 / 2.441 rem.
Keep running text near 65 characters wide; `text-wrap: balance` on headings;
uppercase labels get ~0.14em letter-spacing.

## 3. Logo & motifs

- **Logo:** the family + red-crescent/cross mark. _Asset still needed_ — supply
  full-colour, reversed (for dark grounds), and single-colour versions.
- **Clear space:** keep padding equal to the height of the "T" around the logo.
- **Minimum size:** ~120px wide on screen; never stretch, recolour, or add
  effects.
- **Motifs** (use sparingly, one per view):
  - **Heart** — compassion (already in your materials).
  - **Crescent + cross** — healthcare.
  - **چراغ / diya lamp** — the "Beacon" (چراغ شفا), hope and guidance; pair with
    the Amber accent.

## 4. Layout & spacing

- Base spacing unit: **8px**; compose in multiples (8/16/24/32/48/64).
- Generous whitespace; calm, uncluttered — this is healthcare, not retail.
- Cards: 12px radius, 1px Border, soft shadow.
- Content max width ~720px for reading pages; wider grids for galleries/reports.

## 5. Imagery

- Real clinic, camp, and community photography; warm, natural light.
- **Dignity & consent:** never publish identifiable patient images without
  explicit consent; prefer wide/context shots over faces where consent is
  unclear. (This is a brand rule *and* a privacy rule.)
- Avoid stock clichés; show the actual people and place.

## 6. Voice & tone

- **Compassionate, dignified, clear.** Plain language; minimal medical jargon.
- **Community-first** and faith-respectful (Zakat, Sadaqa, sincerity).
- **Honest and specific** — real numbers, real stories, no over-claiming.
- **Bilingual by default** — English and Urdu given equal care; Pashto may follow.

## 7. Do / Don't

- ✅ Anchor on Teal Deep; spend Amber only on the donate action and lamp motif.
- ✅ Let whitespace and type carry the page.
- ✅ Give Urdu the same design care as English (right-to-left, proper Nastaliq).
- ❌ Don't mix Navy and Teal as co-equal primaries — Navy is heritage/logo only.
- ❌ Don't use Mint or Amber for small body text.
- ❌ Don't add gradients, heavy shadows, or decorative emoji as section markers.

## 8. Open items

- Supply the **logo** asset files (colour / reversed / mono).
- Confirm the **typeface** direction (serif+sans as above, or all-sans).
- Confirm **deep teal** as the standard primary (vs keeping heritage navy).
