# Plan 03 — Design System & Base Templates

_Status: Drafted · Depends on: 01 Project foundation · Next: 04 Core content pages_

## Goal

Turn [brand-guidelines.md](../../docs/brand-guidelines.md) into working code: CSS
design tokens, self-hosted type, and the base Wagtail templates (layout, header,
footer, nav) every later page builds on — plus the bilingual (EN/UR) routing
and RTL plumbing, so Plan 04 onward can add real pages without also inventing
the shell each time. No real page content yet; this step is "any page extends
`base.html` and looks right, in either language."

## Scope

**In scope**
- CSS design tokens (colour, type scale, spacing) translating
  brand-guidelines.md §2–4 into custom properties.
- Self-hosted web fonts (Archivo, Public Sans, Noto Nastaliq Urdu, Noto Naskh
  Arabic) — no font CDN calls.
- Base template (`base.html`): doctype, `<html lang>`/`dir` switching,
  favicon wiring (the new SVG/PNG set from `brand/`), meta tags, skip link.
- Header (logo, primary nav, language switcher) and footer (teal-deep dark
  section, contact/bank-detail placeholder, socials placeholder) partials.
- Bilingual **scaffolding**: Django i18n settings, `/en/…` `/ur/…` URL
  routing, language switcher, RTL layout support for Urdu.
- Baseline accessibility: semantic landmarks, focus-visible states, skip
  link, `prefers-reduced-motion` respected.
- 404 / 500 error templates matching the brand.

**Out of scope** (later plans)
- Real page content and models (Home, About, Team, etc.) → Plan 04.
- Actual Urdu/Pashto translations of content → Plan 10 (Bilingual
  generation). This step wires the *routing and layout* for two languages;
  it doesn't translate anything yet — there's no content to translate.
- Donate-specific styling beyond the Amber token already in the palette →
  Plan 05.
- A full site-wide light/dark theme toggle. The palette has tokens for
  *dark sections* (footer, hero-on-teal) per brand-guidelines.md §2, which
  this plan uses — but the site itself is light-by-default throughout. A
  user-facing theme toggle is a bigger feature than asked for; see open
  questions.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| CSS approach | Hand-written CSS with custom properties (design tokens), no framework | Small site, small maintainer team; a framework (Tailwind etc.) adds a build step and a JS toolchain footprint that don't pay for themselves here. Plain CSS + `:root` tokens is easy for a Python-only maintainer to read and change. |
| Font hosting | Self-hosted `.woff2` under `static/fonts/`, `@font-face` with `font-display: swap` | Matches brand-guidelines.md's "self-hostable" requirement; no third-party font CDN request. |
| Font subsetting | Latin subset for Archivo/Public Sans; full Arabic-script subset for Noto Nastaliq Urdu/Naskh Arabic | Keeps download size reasonable; Urdu needs the full glyph set. |
| i18n framework | Django's built-in i18n (`USE_I18N`, `LocaleMiddleware`, `i18n_patterns`, `{% trans %}`/`{% blocktrans %}`) | No third-party i18n package needed at this stage — Wagtail-specific translated *page content* (as opposed to UI string translation) is a Plan 10 concern (likely `wagtail-localize` then). |
| Languages now | `en` (default), `ur` | Pashto (`ps`) stays a placeholder in `LANGUAGES` per CLAUDE.md ("Pashto may follow") but isn't built out this step. |
| RTL approach | CSS logical properties (`margin-inline-start`, `padding-inline-end`, etc.) over physical `left`/`right`, plus `dir="rtl"` on `<html>` for `ur` | Avoids a separate RTL stylesheet; one set of rules mirrors automatically. |
| Nav interactivity | Plain HTML/CSS (`<details>` for mobile nav disclosure) as the no-JS baseline; HTMX layered on later only if needed | Matches the "minimal JS" architecture decision — don't reach for JS until a later plan actually needs it (e.g. upload, newsletter generation). |

## Proposed file additions

```
static/
├── css/
│   ├── tokens.css        # custom properties: colour, type scale, spacing
│   ├── base.css           # resets, typography, layout primitives
│   └── components.css     # header, footer, nav, buttons, cards
├── fonts/
│   ├── archivo/           # Bold + ExtraBold, woff2, Latin subset
│   ├── public-sans/        # 400 + 600, woff2, Latin subset
│   └── noto/               # Nastaliq Urdu + Naskh Arabic, woff2
└── favicons/               # copied from brand/: favicon.svg, favicon-*.png
templates/
├── base.html
├── 404.html
├── 500.html
└── partials/
    ├── header.html
    ├── footer.html
    ├── nav.html
    └── language_switcher.html
apps/core/
└── templatetags/
    └── (only if a helper tag turns out to be needed — prefer plain Django/Wagtail tags first)
```

## Task checklist

1. **Design tokens** — `static/css/tokens.css`: every colour from
   brand-guidelines.md §2 as a custom property (`--teal-brand`, `--amber-light`,
   etc.), the 1.25 type scale, and the 8px spacing scale, all as named tokens.
2. **Fonts** — download/subset Archivo (Bold/ExtraBold), Public Sans (400/600),
   Noto Nastaliq Urdu, and Noto Naskh Arabic as `.woff2`; `@font-face` rules
   with `font-display: swap`; verify no network request to a font CDN.
3. **Base CSS** — `base.css` (resets, base typography using the tokens,
   8px-based spacing) and `components.css` (header/footer/nav/buttons/cards
   per brand-guidelines.md §4).
4. **`base.html`** — doctype, `<html lang="{{ LANGUAGE_CODE }}" dir="{% if LANGUAGE_BIDI %}rtl{% else %}ltr{% endif %}">`, favicon links (SVG primary + PNG fallbacks + apple-touch-icon from the new `brand/` assets), skip-to-content link, `{% block content %}`.
5. **Header/nav** — logo (`brand/logo.svg`), primary nav (placeholder links
   matching §5 Website structure in the architecture brief — the pages don't
   exist yet, so these can 404 or point at stub URLs until Plan 04), language
   switcher (EN ⇄ UR, preserving the current path).
6. **Footer** — teal-deep dark section using the on-dark palette tokens;
   placeholder blocks for contact/bank details and socials (config-driven,
   not hardcoded — matches the architecture brief's "contact and bank details
   are configured in the running application, not stored in this repository").
7. **i18n settings** — `USE_I18N = True`, `LocaleMiddleware`, `LANGUAGES = [("en", "English"), ("ur", "اردو")]`, `i18n_patterns` wrapping the URL conf, `LOCALE_PATHS` for `.po` files.
8. **RTL layout** — audit `components.css` for any physical `left`/`right`/`margin-left` etc. and convert to logical properties; verify the header/nav/footer mirror correctly when `dir="rtl"`.
9. **Error pages** — `404.html` / `500.html` extending `base.html`, brand-styled, no stack traces.
10. **Accessibility pass** — semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`), visible focus states (not just the default outline removed), `prefers-reduced-motion` respected if any transitions are added.
11. **Smoke tests** — extend Plan 01's test suite: home page (placeholder) renders in both `/en/` and `/ur/` with the correct `lang`/`dir` attributes; 404 page renders and is styled.

## Acceptance criteria

- Any template extending `base.html` inherits correct fonts, colours, and
  spacing with zero additional CSS.
- No request to a third-party font or icon CDN — `read_network_requests` (or
  equivalent) shows only same-origin font/asset requests.
- Visiting `/ur/...` renders the layout mirrored (RTL), in Noto Nastaliq
  Urdu, with `<html lang="ur" dir="rtl">`.
- The language switcher round-trips: switching language on any page returns
  to the equivalent path in the other language, not the homepage.
- 404 and 500 pages are brand-styled, not the Django defaults.
- Keyboard-only navigation reaches every header/footer/nav link with a
  visible focus indicator.
- `ruff check` and `pytest` (including the new template-rendering smoke
  tests) pass in CI.

## Open questions for the maintainer

- Confirm no user-facing light/dark theme toggle is wanted for the site
  itself right now (the palette's dark-section tokens are used for the
  footer regardless of this answer — this is only about a toggle for the
  *whole page*).
- Any real primary-nav item list to lock in now, or keep the Plan-04 page
  list as the placeholder nav (Home, About, Team, Our Work, Reports,
  Newsletters, Gallery, Donate, Contact)?
