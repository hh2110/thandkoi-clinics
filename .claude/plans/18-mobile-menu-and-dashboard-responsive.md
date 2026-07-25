# Plan 18 — Mobile menu fixes + dashboard responsive revision

**One-line:** two small, unrelated-by-code but same-handoff design fixes —
the primary nav drawer (current-page marker, Donate placement, Donate label
colour) and the clinic dashboard's revised range controls / full-width
revenue layout — shipped together as one PR because both come from a single
updated handoff bundle.

## Background — why now

The maintainer supplied an updated design handoff bundle
(`~/Downloads/updates.zip`, 2026-07-25). It is a **revision of the Plan 16
bundle** plus one genuinely new work item:

- `README.md` — the same clinic-dashboard handoff already committed at
  [`docs/design/clinic-dashboard-handoff.md`](../../docs/design/clinic-dashboard-handoff.md),
  **revised**: the range controls are re-specified as the approved mobile
  option 1c ("everything visible"), the revenue table moves from a 1.75fr
  side-by-side layout to full width inside a horizontal scroller, and a new
  "Responsive" section replaces the page's media queries with auto-fitting
  grids.
- `mobile-menu/README.md` — **new work item**: three fixes to the primary
  nav drawer, approved as option 1b (which subsumes option 1a's colour fix)
  plus a Donate label-colour fix. Option 1c (page name in the `<summary>`)
  was not chosen.

Plan 16 shipped work items 1 and 3 of the original bundle (PRs #131, #132,
#134, #139, #141) and parked work item 2 (revenue) as Phase 2 pending fee
columns in the clinic software. **Nothing in this revision changes that**:
the revised revenue layout is still gated on `has_revenue`, still inert
today, and still needs no template work when Phase 2 lands. So this plan is
purely the delta: CSS/markup for the controls and the layout switch, and the
new nav work.

Grounded against the real code before drafting (2026-07-25) — `tokens.css`'s
three theme blocks, `components.css`'s `.primary-nav` rules and the 56rem
breakpoint, `templates/partials/nav.html`, `static/css/dashboard.css`,
`apps/pipeline/templates/pipeline/clinic_dashboard_page.html`, and the
existing dashboard/entry-point tests. That pass turned up four places where
the handoff's stated assumptions do not match the repo — see D1, D2, D5 and
D7.

## Goal & scope

**Goal:** the open mobile drawer no longer reads as "you are in Donate", the
current-page marker is visible in dark mode, and the clinic dashboard's
header controls and revenue section match the revised handoff at every
width.

### In scope

**Track A — mobile menu** (`mobile-menu/README.md`'s checklist, in full)

- New `--color-nav-current` token in all four theme blocks of `tokens.css`.
- `.primary-nav__list a[aria-current="page"]` reads it, plus
  `font-weight: 700`.
- Donate moves out of `.primary-nav__list` into a new `.primary-nav__cta`
  block with a supporting sentence; `.primary-nav__cta` CSS plus the ≥56rem
  overrides that keep the desktop header pixel-identical.
- `--color-donate-text` becomes a literal `#0e2025` in the two dark blocks.
- Tests: `aria-current` still emitted, Donate still in the header markup and
  now outside the list, the CTA sentence present.

**Track B — dashboard responsive revision** (the revised `README.md`)

- Range controls: one `min(100%, 520px)` stack — a preset **tile grid**
  (`repeat(auto-fit, minmax(92px, 1fr))`, 44px tall) above a **date card**
  whose From/To fields and Apply button flex-wrap.
- Revenue section: full width, one column; rows in an `overflow-x: auto`
  wrapper at `min-width: 520px`; Funding split + Gender move **beneath** the
  table as `repeat(auto-fit, minmax(260px, 1fr))`.
- KPI row `repeat(auto-fit, minmax(210px, 1fr))`; age bands
  `repeat(auto-fit, minmax(150px, 1fr))`; page padding `clamp()`.
- The page's two `max-width` media queries go away — the auto-fitting grids
  replace them (D6).
- Update the committed handoff doc to the revised revision, and commit the
  new mobile-menu handoff alongside it.

### Out of scope

- **The handoff's "Also worth doing" suggestion** — inline donation links in
  the home impact band, the Reports intro and the end of a daily report.
  Deliberately parked: see D7.
- **Phase 2 revenue** — unchanged from Plan 16. The revised revenue markup
  is still written against `has_revenue` and still renders nothing today.
- **The footfall chart's internals.** The handoff still describes a
  div-and-flexbox chart; this repo renders SVG (Plan 16 D2). The revision's
  chart notes are the same as Plan 16's, already reconciled — see D5.

## Decisions

- **D1 — `--color-nav-current` is added even though `--color-stat-value`
  already resolves to the same light/dark pair.** `--color-stat-value` is
  `var(--color-brand)` in light and `var(--color-pale-aqua)` in dark, i.e.
  byte-identical to what the handoff asks for. Reusing it was considered and
  rejected: it is named for stat-band figures, and `dashboard.css` already
  borrows it twice for non-stat controls with an apologetic comment. A
  second borrow would make the name meaningless. A distinct semantic token
  costs four lines and lets either surface move independently. The handoff
  asks for this name explicitly.
- **D2 — the dropdown needs no separate selector.** The handoff says the fix
  "applies to `.nav-dropdown__menu a[aria-current="page"]` too". It already
  does: the "More" flyout is an `<li>` inside `.primary-nav__list`, so
  `.primary-nav__list a[aria-current="page"]` (0,3,0) already matches Team /
  Gallery / Contact and outranks `.nav-dropdown__menu a:hover` (0,2,0). No
  second rule is added; a test covers a dropdown page so this stays true.
- **D3 — `--color-donate-text` becomes a literal `#0e2025`, declared once in
  `:root` for both themes.** The handoff's reasoning ("not
  `var(--color-ink)`, which flips") is exactly the rationale already written
  into `tokens.css` for `--color-footer-text`. It goes further than the
  handoff's token table in one respect, and deliberately: that table leaves
  light at `#ffffff` while its own prose says the button should keep "dark
  ink text in both themes". D10 explains why the prose is right and the
  table is a description of a value nothing ever rendered — white on
  Amber-on-Light is ~2.6:1, and shipping it would have been a regression.
  Declared once rather than per-theme, following `--color-on-brand`'s
  precedent for a token that doesn't flip, so the two halves cannot drift
  apart again.
- **D10 — button-styled anchors are excluded from `base.css`'s themed anchor
  rules.** Found by measuring the rendered page, not by reading the diff:
  after D3 the Donate label was *still* pale aqua. `base.css` colours links
  at `:root[data-theme="dark"] a` — (0,2,1) — and every `.button--*` variant
  sets its colour at (0,1,0), so for any visitor who had picked a theme by
  hand the link colour won and **every filled button on the site** rendered
  `--color-pale-aqua` on its own fill: ~2.2:1 on Donate's amber, ~2.4:1 on
  `.button--primary`'s teal. The OS-preference path never showed it (that
  rule is only (0,0,1)), which is why it survived this long. Fixed at the
  source with `a:not(:where(.button))` — `:where()` contributes zero
  specificity, so the rules keep exactly the weight they had and simply stop
  matching buttons. Chosen over bumping six button rules to three-class
  selectors, which would have left the same trap for the next variant. This
  is wider than the handoff asked for, and is the same defect it describes.
- **D11 — the desktop Donate button is *not* pixel-identical, by 16px of
  position and 5px of height.** The handoff asks for pixel-identity at
  1280px; measured against `origin/main` in the browser, the header bar and
  theme toggle are byte-identical but Donate moves from x=950/h=43 to
  x=966/h=48. Both deltas are main's anomaly, not the branch's: inside the
  list, `.primary-nav__list a { padding-block: var(--space-1) }` (0,2,0)
  overrode `.button`'s own `0.65em` padding and squashed the button 5px
  shorter than every other button on the site, and the 16px is the list's
  trailing space becoming the CTA block's `--space-3` gap — the same gap
  that separates every other pair of nav items. Out of the list the button
  renders at the geometry the handoff's own mock specifies (radius 8px,
  padding `.65em 1.25em`). Accepted rather than re-squashed.
- **D4 — the CTA sentence is a new translatable string, not a Wagtail
  field.** Every other string in `nav.html` is a `{% translate %}` literal;
  the nav is not editable content. `locale/` holds no compiled catalogs yet
  (the repo has no `.po` files at all), so "Urdu string" here means the
  string is wrapped and extractable, same as every existing nav label — not
  that a translation is added.
- **D5 — the chart is untouched.** The revision's "Responsive" table says
  the chart "simply narrows" because its bars are `flex:1`. This repo's
  chart is server-rendered SVG with `min-width: 560px` inside
  `.dash-chart__scroll` (Plan 16 D2), which already achieves the stated
  goal — a bounded bar count that scrolls rather than crushes. Rewriting it
  as flexbox divs to match the prototype's mechanism would lose the shared
  geometry module and the hover tooltip. Not done.
- **D6 — the media queries are removed, not kept alongside the auto-fit
  grids.** Keeping both would mean two sources of truth for the same
  breakpoint behaviour, and the `max-width: 40rem` KPI rule
  (`grid-template-columns: 1fr`) directly contradicts
  `repeat(auto-fit, minmax(210px, 1fr))`, which should give two-up at 40rem.
  The revised handoff is explicit: "No media queries are needed anywhere on
  this page."
- **D7 — the "Also worth doing" donation links are parked.** Its stated
  premise is that moving Donate out of the nav list costs reach. Under the
  approved option 1b it does not: Donate stays in the header at every width,
  in the drawer on mobile and inline on desktop, with an added supporting
  sentence it did not have before. The suggestion is also not in the
  handoff's own checklist, and it lands in three unrelated templates
  (home band, reports index, daily report), each of which is a copy change
  better made deliberately with the maintainer than folded into a nav fix.
  Recorded here so bringing it back is a decision, not an oversight.
- **D9 — only the block half of the handoff's page padding is taken.** The
  revision asks for `clamp(1.25rem,4vw,2.75rem) clamp(1rem,4vw,2.5rem) 4rem`.
  The inline half is `.wrapper`'s job (`base.css`), and the site header and
  footer use the same `.wrapper` — insetting this page's content to 2.5rem
  while the header stays at 1rem would leave the two visibly misaligned at
  desktop width. The prototype is a standalone page with no site chrome to
  line up with. Block padding is taken, rounded onto the spacing scale
  (`clamp(var(--space-3), 4vw, var(--space-6))`), which is what actually
  tightens the page on a phone.
- **D8 — the `--color-track` token still does not exist.** Plan 16 D4
  resolved this once: the handoff's `--color-track` (light `#e6eded`) is
  within three hex points of `--color-border-default` (`#e0e7e8`), which is
  what `.dr__bar-track` already uses. The revision repeats the token without
  adding it to the repo. Unchanged: `dashboard.css` keeps reading
  `--color-border-default`.

## Precedent map (Stage 7)

| Element | Precedent it mirrors |
|---|---|
| `--color-nav-current` in four theme blocks | `--color-stat-value` (Plan 11 D12) — same "one token, one problem, all four blocks" shape |
| Literal `#0e2025` for `--color-donate-text` | `--color-footer-text: #f2f6f6` and its comment, `tokens.css` |
| `.primary-nav__cta` + its ≥56rem override | `.site-header__controls`, which already does exactly this (mobile padding + hairline, neutralised at 56rem) |
| Preset tile grid | `.dash__age-grid` / `.dash__kpis` — plain CSS grid on a page-scoped block |
| Date card flex-wrap | `.dash__dates` today; `.dash-chart__head`'s `flex-wrap: wrap` |
| Revenue `overflow-x: auto` wrapper | `.dash-chart__scroll` + `.dash-chart__plot`'s `min-width`, same page |
| Nav tests | `apps/pipeline/test_dashboard_entry_points.py` — assert on rendered markup via the test client |
| Handoff doc committed for provenance | `docs/design/clinic-dashboard-handoff.md` (Plan 16) |

## Feature flag (Stage 6)

**No flag.** Both tracks are CSS/markup changes to already-live surfaces with
no partial state: either the drawer has the new CTA block or it does not.
Rollback is a revert. Consistent with every prior plan in this repo — see the
plans index preamble.

## Tasks

- [x] **18.1 — tokens.** `--color-nav-current` in `:root`, the
      `prefers-color-scheme: dark` block and both `[data-theme]` blocks;
      `--color-donate-text` literal in the two dark blocks.
- [x] **18.2 — nav markup + CSS.** Donate out of the list into
      `.primary-nav__cta`; current-page marker rule; `.primary-nav__cta`
      styles and the ≥56rem neutralisation.
- [x] **18.3 — dashboard range controls.** Tile grid + date card, template
      and CSS.
- [x] **18.4 — dashboard revenue layout + responsive.** Full-width revenue
      with a scroller, side cards beneath as auto-fit, KPI/age auto-fit,
      `clamp()` page padding, media queries removed.
- [x] **18.5 — docs.** Refresh `docs/design/clinic-dashboard-handoff.md` to
      the revised revision; add `docs/design/mobile-menu-handoff.md` and its
      screenshots/prototype.
- [x] **18.6 — tests.** Nav (`aria-current` on a top-level and a dropdown
      page, Donate outside the list but present in the header, CTA sentence,
      the two token guards, and D10's anchor-specificity guard) and dashboard
      (range-control markup, no-revenue layout still renders both side
      cards). Every new guard was mutation-tested — reverted deliberately and
      confirmed red — before being kept.

## Acceptance criteria

- Open drawer on mobile: the current page is underlined, bold, and readable
  in both themes; Donate sits below a hairline with its sentence, not as a
  list row.
- Desktop header at 1280px: bar and theme toggle unchanged from `main`;
  Donate moves 16px and grows 5px, both explained and accepted in D11.
- Donate label is dark ink on amber in both themes, and `.button--primary` /
  `.button--outline` get their own colours back under an explicit theme
  choice (D10).
- Dashboard at 390 / 768 / 1280px: presets are a tile grid (3-up then 5-up),
  the date card wraps Apply to full width on a phone, KPIs go 3-up → 2-up →
  1-up, age bands 4-up → 2-up, and both side cards sit beneath a
  (currently absent) revenue table two-up at full width.
- All dashboard tap targets in the range controls are 44px.
- `pytest` green; `ruff` clean.

## Release plan (Stage 10)

**How it ships.** Merged to `main`, deployed by the existing manual
`workflow_dispatch` release job against a dated tag. No migration, no new
setting, no new dependency — CSS, one template move, one new template block
and tests.

**Who gets access, when.** Everyone, immediately on deploy. Both surfaces are
public and already live; this changes how they look, not who can see them.

**Who is informed.** The maintainer (the handoff's author, Dawood by
proxy) — the drawer change is visible enough to be worth a note, and D7's
parked suggestion needs a decision.

**Gating check.** The dashboard and nav pages render in both themes at 390px
and 1280px, screenshotted from a live server, plus a green suite.

**Rollback trigger.** Any report that the desktop header shifted, or that
Donate became hard to find. Revert the PR — nothing here is stateful.
