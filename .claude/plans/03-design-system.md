# Plan 03 — Design System & Base Templates

_Status: Drafted · Depends on: 01 Project foundation, brand-guidelines.md dark-theme tokens · Next: 04 Core content pages_

## Goal

Turn [brand-guidelines.md](../../docs/brand-guidelines.md) into working code: CSS
design tokens (light **and** dark), self-hosted type, a real light/dark toggle,
and the base Wagtail templates (layout, header, footer, nav) every later page
builds on — plus the bilingual (EN/UR) routing and RTL plumbing, so Plan 04
onward can add real pages without also inventing the shell each time. No real
page content yet; this step is "any page extends `base.html` and looks right,
in either language, in either theme."

## Scope

**In scope**
- CSS design tokens (colour, type scale, spacing) translating
  brand-guidelines.md §2–4 into custom properties — both the light and dark
  neutral sets.
- A **user-facing light/dark theme toggle**: defaults to the visitor's OS
  preference, overridable and persisted, no flash of the wrong theme on load.
- Self-hosted web fonts (Archivo, Public Sans, Noto Nastaliq Urdu, Noto Naskh
  Arabic) — no font CDN calls.
- Base template (`base.html`): doctype, `<html lang>`/`dir` switching,
  favicon wiring (the new SVG/PNG set from `brand/`), meta tags, skip link.
- Header (logo, primary nav, language switcher, theme toggle) and footer
  (dark section, contact/bank-detail placeholder, socials placeholder)
  partials.
- Bilingual **scaffolding**: Django i18n settings, `/en/…` `/ur/…` URL
  routing, language switcher, RTL layout support for Urdu.
- Baseline accessibility: semantic landmarks, focus-visible states, skip
  link, `prefers-reduced-motion` respected.
- 404 / 500 error templates matching the brand, in both themes.

**Out of scope** (later plans)
- Real page content and models (Home, About, Team, etc.) → Plan 04.
- Actual Urdu/Pashto translations of content → out of scope for now (see the
  [plans README](README.md#out-of-scope-for-now) — Bilingual generation).
  This step wires the *routing and layout* for two languages; it doesn't
  translate anything yet — there's no content to translate.
- Donate-specific styling beyond the Amber token already in the palette →
  Plan 05.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| CSS approach | Hand-written CSS with custom properties (design tokens), no framework | Small site, small maintainer team; a framework (Tailwind etc.) adds a build step and a JS toolchain footprint that don't pay for themselves here. Plain CSS + `:root` tokens is easy for a Python-only maintainer to read and change. |
| Font hosting | Self-hosted `.woff2` under `static/fonts/`, `@font-face` with `font-display: swap` | Matches brand-guidelines.md's "self-hostable" requirement; no third-party font CDN request. |
| Font subsetting | Latin subset for Archivo/Public Sans; full Arabic-script subset for Noto Nastaliq Urdu/Naskh Arabic | Keeps download size reasonable; Urdu needs the full glyph set. |
| i18n framework | Django's built-in i18n (`USE_I18N`, `LocaleMiddleware`, `i18n_patterns`, `{% trans %}`/`{% blocktrans %}`) | No third-party i18n package needed at this stage — Wagtail-specific translated *page content* (as opposed to UI string translation) is currently out of scope (see the plans README — Bilingual generation; likely `wagtail-localize` if that's picked up later). |
| Languages now | `en` (default), `ur` | Pashto (`ps`) stays a placeholder in `LANGUAGES` per CLAUDE.md ("Pashto may follow") but isn't built out this step. |
| RTL approach | CSS logical properties (`margin-inline-start`, `padding-inline-end`, etc.) over physical `left`/`right`, plus `dir="rtl"` on `<html>` for `ur` | Avoids a separate RTL stylesheet; one set of rules mirrors automatically. |
| Nav interactivity | Plain HTML/CSS (`<details>` for mobile nav disclosure) as the no-JS baseline; HTMX layered on later only if needed | Matches the "minimal JS" architecture decision — don't reach for JS until a later plan actually needs it (e.g. upload, newsletter generation). |
| Theme token layering | `:root` = light tokens (default) → `@media (prefers-color-scheme: dark)` overrides them → `:root[data-theme="dark"]` / `:root[data-theme="light"]` override *that* in both directions | Standard robust pattern: OS preference is the fallback signal, an explicit user choice always wins regardless of which direction it goes. Components read tokens, never the media query directly. |
| Theme persistence | `localStorage`, read by a small inline script in `<head>` (before any CSS paints) that sets `data-theme` on `<html>` | Avoids a flash of the wrong theme on load (the inline script runs before first paint). No cookie/server round-trip needed for a purely client-side preference. |
| Theme toggle | A small vanilla JS file (`static/js/theme-toggle.js`) toggling `data-theme` and writing `localStorage` — this is the one deliberate JS dependency in an otherwise no-JS plan | Necessary: there's no way to flip a stored client preference without JS. Degrades gracefully — with JS disabled, the toggle button doesn't render (progressive enhancement) and the site just follows OS preference via the media query. |

## Proposed file additions

```
static/
├── css/
│   ├── tokens.css        # custom properties: colour (light+dark), type scale, spacing
│   ├── base.css           # resets, typography, layout primitives
│   └── components.css     # header, footer, nav, buttons, cards, theme toggle
├── js/
│   └── theme-toggle.js    # the one deliberate JS dependency in this plan
├── fonts/
│   ├── archivo/           # Bold + ExtraBold, woff2, Latin subset
│   ├── public-sans/        # 400 + 600, woff2, Latin subset
│   └── noto/               # Nastaliq Urdu + Naskh Arabic, woff2
└── favicons/               # copied from brand/: favicon.svg, favicon-*.png
templates/
├── base.html               # includes the inline anti-FOUC theme script in <head>
├── 404.html
├── 500.html
└── partials/
    ├── header.html
    ├── footer.html
    ├── nav.html
    ├── language_switcher.html
    └── theme_toggle.html
apps/core/
└── templatetags/
    └── (only if a helper tag turns out to be needed — prefer plain Django/Wagtail tags first)
```

## Task checklist

1. **Design tokens** — `static/css/tokens.css`: every colour from
   brand-guidelines.md §2 (including the new dark-theme neutrals) as a custom
   property, layered `:root` → `@media (prefers-color-scheme: dark)` →
   `:root[data-theme]` per the decision above; the 1.25 type scale and 8px
   spacing scale as named tokens (theme-independent).
2. **Anti-FOUC inline script** — a small inline `<script>` in `base.html`'s
   `<head>`, before any stylesheet, that reads `localStorage` and sets
   `data-theme` on `<html>` synchronously — this is what prevents a flash of
   the wrong theme on load.
3. **Theme toggle** — `static/js/theme-toggle.js` (click handler: flip
   `data-theme`, write `localStorage`) and `partials/theme_toggle.html` (a
   `<button>` in the header, `aria-pressed` reflecting state, an accessible
   label, not just an icon).
4. **Fonts** — download/subset Archivo (Bold/ExtraBold), Public Sans (400/600),
   Noto Nastaliq Urdu, and Noto Naskh Arabic as `.woff2`; `@font-face` rules
   with `font-display: swap`; verify no network request to a font CDN.
5. **Base CSS** — `base.css` (resets, base typography using the tokens,
   8px-based spacing) and `components.css` (header/footer/nav/buttons/cards/
   theme toggle per brand-guidelines.md §4), all colour rules via tokens so
   both themes work with zero per-component dark-mode overrides.
6. **`base.html`** — doctype, `<html lang="{{ LANGUAGE_CODE }}" dir="{% if LANGUAGE_BIDI %}rtl{% else %}ltr{% endif %}">`, favicon links (SVG primary + PNG fallbacks + apple-touch-icon from the new `brand/` assets), skip-to-content link, `{% block content %}`.
7. **Header/nav** — logo (`brand/logo.svg`, already theme-agnostic per
   brand-guidelines.md §1), primary nav (**placeholder links**, confirmed —
   matching §5 Website structure in the architecture brief; the pages don't
   exist yet, so these can 404 or point at stub URLs until Plan 04), language
   switcher (EN ⇄ UR, preserving the current path), theme toggle.
8. **Footer** — dark section using the dark-theme palette tokens (same tokens
   the site-wide dark theme uses — see brand-guidelines.md's "Neutrals — dark
   theme"); placeholder blocks for contact/bank details and socials
   (config-driven, not hardcoded — matches the architecture brief's "contact
   and bank details are configured in the running application, not stored in
   this repository").
9. **i18n settings** — `USE_I18N = True`, `LocaleMiddleware`, `LANGUAGES = [("en", "English"), ("ur", "اردو")]`, `i18n_patterns` wrapping the URL conf, `LOCALE_PATHS` for `.po` files.
10. **RTL layout** — audit `components.css` for any physical `left`/`right`/`margin-left` etc. and convert to logical properties; verify the header/nav/footer mirror correctly when `dir="rtl"`.
11. **Error pages** — `404.html` / `500.html` extending `base.html`, brand-styled in both themes, no stack traces.
12. **Accessibility pass** — semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`), visible focus states (not just the default outline removed), `prefers-reduced-motion` respected, theme toggle has a real accessible name and `aria-pressed` state.
13. **Smoke tests** — extend Plan 01's test suite: home page (placeholder) renders in both `/en/` and `/ur/` with the correct `lang`/`dir` attributes; 404 page renders and is styled; the anti-FOUC script and theme toggle markup are present.

## Acceptance criteria

- Any template extending `base.html` inherits correct fonts, colours, and
  spacing with zero additional CSS.
- No request to a third-party font or icon CDN — `read_network_requests` (or
  equivalent) shows only same-origin font/asset requests.
- The theme toggle switches every token-driven colour on the page instantly;
  the choice persists across a reload; with no stored choice, the page
  matches the OS `prefers-color-scheme`; there is no visible flash of the
  wrong theme on load.
- Visiting `/ur/...` renders the layout mirrored (RTL), in Noto Nastaliq
  Urdu, with `<html lang="ur" dir="rtl">` — in both themes.
- The language switcher round-trips: switching language on any page returns
  to the equivalent path in the other language, not the homepage.
- 404 and 500 pages are brand-styled in both themes, not the Django
  defaults.
- Keyboard-only navigation reaches every header/footer/nav link and the
  theme toggle, with a visible focus indicator in both themes.
- `ruff check` and `pytest` (including the new template-rendering smoke
  tests) pass in CI.

## Resolved (was open questions)

- **Light/dark toggle**: confirmed wanted — built into this plan (see
  Scope and the theme-token decisions above). Not deferred.
- **Primary nav**: confirmed — keep the Plan 04 page list as placeholder nav
  (Home, About, Team, Our Work, Reports, Newsletters, Gallery, Donate,
  Contact); no separate real nav list to lock in now.
