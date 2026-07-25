# Handoff: Mobile menu — current-page marker, Donate placement, Donate text colour

## Overview

Three small, related fixes to the primary navigation drawer
(`templates/partials/nav.html` + `static/css/components.css`), prompted by
feedback that the open mobile menu reads as "you are in Donate" no matter
which page you are on.

**Approved: option 1b**, which includes option 1a's colour fix. Plus a third
fix to the Donate button's text colour in dark mode (below). Option 1c
(page name in the `<summary>`) was **not** chosen — ignore it.

## About the design files

`Mobile Menu Options.dc.html` is a **design reference created in HTML** — a
prototype of the intended appearance, not production code. Recreate the
result in the existing Django templates and token-based CSS. The drawer in
the mock is drawn with the real values already in `components.css` (list
padding `--space-1 --space-2 --space-2`, `--space-1` gap, links 600 weight
with `padding-block: --space-1`, buttons 8px radius / `.65em 1.25em` / 600 /
`--font-size-sm`) so the mock and the component should line up 1:1.

Open the file in a browser to view it; `support.js` and `fonts/` are bundled
so it works offline. The mock uses literal hex values — **implement with the
tokens**, never the hexes.

## Fidelity

**High fidelity.** Everything here is a token change or a one-element move.

---

## Fix 1 — the current-page marker is invisible in dark mode

`components.css`:

```css
.primary-nav__list a[aria-current="page"] {
  color: var(--color-brand);
  text-decoration: underline;
  text-underline-offset: 0.25em;
}
```

`--color-brand` is `#086c7e` in **both** themes. On the dark drawer
(`--color-paper` `#0a3e48`) that measures **1.9:1** — far below WCAG AA's
4.5:1 — so the marker cannot be seen. In the light theme the same colour on
white is 6.1:1 and is fine.

**Change:** introduce a theme-aware token and use it here, alongside a weight
bump so the marker survives even when colour is missed.

```css
/* tokens.css, light block */
--color-nav-current: var(--color-brand);      /* #086c7e on #ffffff → 6.1:1 */
/* tokens.css, dark block(s) — both the media query and the [data-theme] blocks */
--color-nav-current: var(--color-pale-aqua);  /* #a0e0e8 on #0a3e48 → 8.0:1 */

/* components.css */
.primary-nav__list a[aria-current="page"] {
  color: var(--color-nav-current);
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 0.25em;
}
```

Note `tokens.css` defines the dark palette in three places (the
`prefers-color-scheme` media query and two `[data-theme]` blocks) — add the
token to all of them, as the neighbouring tokens do.

Applies to `.nav-dropdown__menu a[aria-current="page"]` too (Team, Gallery,
Contact), which inherits the same problem.

## Fix 2 — Donate leaves the nav list (option 1b)

Today Donate is the last `<li>` of `.primary-nav__list`:

```html
<li>
  <a class="button button--donate" href="/{{ lang }}/donate/">{% translate "Donate" %}</a>
</li>
```

Being a filled row inside the list of pages is what makes it read as the
selected page. Move it out of the `<ul>` into its own block between the list
and `.site-header__controls`:

```html
  </ul>

  <div class="primary-nav__cta">
    <p class="primary-nav__cta-text">
      {% translate "Zakat and Sadaqa keep care free for those who need it most." %}
    </p>
    <a class="button button--donate primary-nav__cta-button"
       href="/{{ lang }}/donate/">{% translate "Donate" %}</a>
  </div>

  <div class="site-header__controls">…</div>
```

CSS (mobile, i.e. the default — see Desktop below):

```css
.primary-nav__cta {
  border-block-start: 1px solid var(--color-border-default);
  padding: var(--space-2);
}
.primary-nav__cta-text {
  margin: 0 0 var(--space-1);
  color: var(--color-text-soft);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}
.primary-nav__cta-button {
  display: block;
  text-align: center;
}
```

Layout in the mock: hairline above the block, `--space-2` padding all round,
the sentence at body size in `--color-text-soft`, then the full-width amber
button. Donate keeps its fill and its amber — it is simply no longer a row
among the pages.

**Desktop (≥56rem) must not change.** `.primary-nav::details-content` is a
flex row at that width, so the new `.primary-nav__cta` becomes a flex item
next to the list — inside the media query, drop its border and padding, hide
`.primary-nav__cta-text`, and let the button sit inline exactly where it does
now:

```css
@media (min-width: 56rem) {
  .primary-nav__cta { border-block-start: 0; padding: 0; }
  .primary-nav__cta-text { display: none; }
  .primary-nav__cta-button { display: inline-block; }
}
```

Check the desktop header at 1280px against the current build — the Donate
button should be pixel-identical.

## Fix 3 — Donate label colour in dark mode

`--color-donate-text` resolves to `var(--color-ink)` in the dark blocks, i.e.
near-white/pale on the amber fill — roughly 1.9:1, and it looks washed out.
The amber button should keep **dark ink text in both themes**:

```css
/* tokens.css — dark blocks */
--color-donate-text: #0e2025;   /* literal ink, not var(--color-ink), which flips */
```

`#0e2025` on `--color-amber-on-dark` `#e8b04a` is ~10:1. This matches the
mock. Same treatment for any other amber-filled button (the hero/footer CTA
if it uses `.button--donate`).

## Also worth doing (Dawood's second suggestion)

Link donation from body copy in a few places — home page impact band, the
Reports intro, the end of a daily report — so removing Donate from the nav
list costs nothing in reach. Use ordinary inline links, not more buttons.

## Design tokens used

| Token | Light | Dark |
|---|---|---|
| `--color-nav-current` (new) | `var(--color-brand)` `#086c7e` | `var(--color-pale-aqua)` `#a0e0e8` |
| `--color-donate-bg` | `#ce8a2c` | `#e8b04a` |
| `--color-donate-text` | `#ffffff` | `#0e2025` (changed) |
| `--color-text` | `#0e2025` | `#f2f6f6` |
| `--color-text-soft` | `#3e5257` | `#abb4b6` |
| `--color-border-default` | `#e0e7e8` | `#195a67` |
| `--color-paper` (drawer bg) | `#f2f6f6` | `#0a3e48` |

Contrast measurements quoted above: brand on dark drawer 1.9:1 · pale aqua on
dark drawer 8.0:1 · brand on white 6.1:1 · ink on amber-dark ~10:1 · amber
outline on dark drawer 6.0:1.

Spacing/geometry: `--space-1` `.5rem`, `--space-2` `1rem`; button radius 8px,
padding `.65em 1.25em`, weight 600, `--font-size-sm` `1rem`.

## Checklist

- [ ] Add `--color-nav-current` to the light block and all dark blocks in
      `tokens.css`
- [ ] Update `.primary-nav__list a[aria-current="page"]` (+ the dropdown
      equivalent) to use it, with `font-weight: 700`
- [ ] Move the Donate `<li>` out of `.primary-nav__list` into
      `.primary-nav__cta` in `nav.html`, with the supporting sentence
- [ ] Add `.primary-nav__cta` CSS and the ≥56rem overrides
- [ ] Set `--color-donate-text` to literal `#0e2025` in the dark blocks
- [ ] Urdu string for the new sentence
- [ ] Verify: desktop header unchanged at ≥56rem; drawer in both themes;
      current-page marker visible on every top-level page and on the three
      "More" pages
- [ ] Tests: `aria-current` still emitted on the right link; Donate link
      still present in the header markup (existing nav tests may assert it is
      inside the list — update them)

## Files in this bundle

| File | What it is |
|---|---|
| `Mobile Menu Options.dc.html` | The three options; **1a and 1b are approved**, 1c is not |
| `screenshots/option-1b-donate-out-of-list.png` | The approved drawer |
| `screenshots/option-1a-current-page-marker.png` | The colour fix, dark and light |
| `support.js`, `fonts/` | So the HTML opens offline |
