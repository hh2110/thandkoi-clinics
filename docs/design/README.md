# Design reference

Visual reference for the site's look, produced during planning of
**[Plan 03.5](../../.claude/plans/03.5-design-enhancements.md)** (page layout
components) and **[Plan 04](../../.claude/plans/04-core-content-pages.md)** (core
content pages). These are the "looks right" target the acceptance criteria in
those plans point at.

Everything here is built strictly on the merged Plan 03 design system — the same
`tokens.css` custom properties, the real `logo.svg`, Archivo + Public Sans, and
the brand-guidelines colour rules (coral = cross/heart motif only; amber =
Donate only). Both light and dark themes are shown.

## Images

| File | What it shows |
|---|---|
| `home-proposed-light.png` | Target Home page, light theme — full page |
| `home-proposed-dark.png` | Target Home page, dark theme — full page |
| `site-baseline-light.png` | What renders **today** (Plan 03 chrome + near-empty home shell) — the before-state |

The target Home page composes the Plan 03.5 layout kit: sticky header, hero
(headline + Zakat/Sadaqa CTA + Urdu tagline + floating stat card), impact-stat
band, "What we do" service cards, latest-daily-report feature split,
gallery-preview grid, and a Teal-Deep donate band.

## Prototypes

`prototypes/*.dc.html` are the interactive source files the images were captured
from. They are **design prototypes, not production code** — they use inline
styles (a prototyping constraint) and an external component runtime, so they do
not run inside this Django/Wagtail project. The production implementation is
class-based CSS reading the same tokens (see Plan 03.5). They are committed only
for provenance and so the interactive light/dark reference travels with the repo.

> Note: numbers in the mockups (e.g. "128 patients", "36k+") are **illustrative
> only**. Real figures come from the CMS (Plan 04 impact stats) and the data
> pipeline (Plan 08). Photos are placeholders — see the dignity & consent rule
> in `docs/brand-guidelines.md` §5.
