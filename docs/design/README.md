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

## Clinic dashboard handoff (2026-07-25)

A second, later design reference: the maintainer-supplied handoff bundle for
**[Plan 16](../../.claude/plans/16-clinic-dashboard.md)** — the range-aggregate
clinic dashboard, the daily report's revenue section, and the two approved
dashboard entry points.

| File | What it is |
|---|---|
| `clinic-dashboard-handoff.md` | The handoff spec itself — layout, tokens, copy, interaction, revenue-optional behaviour, checklist |
| `prototypes/clinic-dashboard.dc.html` | Work item 1 — the dashboard (presets and date inputs work) |
| `prototypes/daily-report-revenue.dc.html` | Work item 2 — daily report incl. the new Revenue section |
| `prototypes/dashboard-entry-points.dc.html` | Work item 3 — options 1a and 1c (approved) plus 1b/1d (**not** chosen) |
| `prototypes/mobile-date-range-options.dc.html` | The three mobile range-picker options; **1c approved** and folded into the dashboard prototype |
| `clinic-dashboard/*.png` | Screenshots of all of the above, dashboard top-to-bottom, both approved entry points, and the range picker at desktop + mobile |

Same caveats as above, plus two specific to this bundle: the prototypes always
show the revenue surfaces (they carry **invented** sample revenue), and the
handoff's own token table lists a `--color-track` that does not exist in
`tokens.css` — Plan 16 D4 reuses `--color-border-default` instead. The bundle's
`fonts/` and `support.js` (included only so it rendered offline) are not
committed, matching the existing prototypes here.

> **Revised 2026-07-25** (second bundle, `updates.zip`). `clinic-dashboard-handoff.md`
> and `prototypes/clinic-dashboard.dc.html` here are the **revision**, not the
> version Plan 16 built against. Two things changed: the header's range
> controls became the approved mobile option 1c (a preset *tile grid* over a
> date card with a visible Apply, one markup at every width, all 44px targets)
> in place of the pill group and borderless inputs; and the revenue table moved
> from a 1.75fr column beside Funding split / Gender to full width above them,
> inside a horizontal scroller. A new "Responsive" section replaces the page's
> media queries with auto-fitting grids. Implemented in
> **[Plan 18](../../.claude/plans/18-mobile-menu-and-dashboard-responsive.md)**
> Track B, where D9 records the one deliberate divergence (page padding).

## Mobile menu handoff (2026-07-25)

Shipped in the same `updates.zip` bundle as the dashboard revision above, but a
separate work item: three fixes to the primary nav drawer, prompted by feedback
that the open mobile menu read as "you are in Donate" whatever page you were on.
Implemented in **[Plan 18](../../.claude/plans/18-mobile-menu-and-dashboard-responsive.md)**
Track A.

| File | What it is |
|---|---|
| `mobile-menu-handoff.md` | The handoff spec — the three fixes, their contrast measurements, tokens and checklist |
| `prototypes/mobile-menu-options.dc.html` | The options; **1a and 1b approved**, 1c (page name in the `<summary>`) **not** chosen |
| `mobile-menu/option-1a-current-page-marker.png` | The colour fix, dark and light |
| `mobile-menu/option-1b-donate-out-of-list.png` | The approved drawer, Donate out of the page list |

One thing in it is already true of this repo and needs no change: the handoff
asks for a second rule on `.nav-dropdown__menu a[aria-current="page"]`, but the
"More" flyout is an `<li>` *inside* `.primary-nav__list`, so the existing
descendant selector already reaches Team / Gallery / Contact (Plan 18 D2, pinned
by `apps/core/test_nav.py`). Its "Also worth doing" suggestion — inline donation
links in body copy — is deliberately **not** implemented; see Plan 18 D7.
