# Plan 05 — Donate Placeholder

_Status: Drafted · Depends on: 01 Project foundation, 03 Design system & base templates, 04 Core content pages · Next: 06 Newsletters, Camp Reports & Gallery_

## Goal

A Donate page carrying the Zakat/Sadaqa message and a way to actually give —
bank transfer details plus "contact us to arrange it another way." No payment
processing, no checkout, no donor accounts: per
[architecture-and-ai-brief.md §5](../../docs/architecture-and-ai-brief.md) this
is explicitly a **placeholder**, and per the safety rules this assistant
operates under, an AI-built site should never execute financial transactions
on anyone's behalf regardless — the "placeholder" scope was independently the
right call before that even applies.

Once this page exists, Plan 04's Home page `DonateCTABlock` (built pointing
at nothing) gets pointed at it — a content-entry step, not a code change (see
Plan 04's "Where content lives: code vs. CMS" for why that distinction
matters here too).

## Scope

**In scope**
- A `DonatePage` with Zakat/Sadaqa messaging and a bank-transfer "how to
  give" section.
- Reusing Plan 04's **Contact & Bank Details** setting for the actual bank
  fields — not a second copy of them.
- The Amber donate-CTA styling (brand-guidelines.md §2) applied to this
  page's primary action and anywhere else a donate link appears (header/
  footer, Home's CTA).

**Out of scope** (later, if ever)
- Any online payment/checkout flow (card, JazzCash, Easypaisa, etc.) — not
  planned; this assistant wouldn't build a live money-movement flow even if
  asked, and the architecture brief never called for one. If this is ever
  wanted, it needs its own plan, explicit scoping, and almost certainly a
  third-party payment processor rather than anything custom.
- Donor accounts, donation tracking, or receipts — no transactions are
  processed, so there's nothing to track or issue a receipt for. A donor
  wanting a receipt is a "contact us" case, same as arranging an in-kind
  gift.
- Funding-grade grant-application spin-outs (architecture brief goal 4) —
  that reuses aggregate data from the pipeline (Plan 08/09), unrelated to
  this static page.

## Source material

Same source PDF as Plan 04 (`The Thandkoi Clinics final V15.pdf`):

- **p.18 — "Giving with Purpose"**: *"Every resident of Thandkoi and its
  surrounding areas deserves access to quality healthcare that is free,
  accessible, and delivered with dignity. Thandkoi Clinics brings this
  vision to life by advancing the principle of universal health coverage
  through a transparent, accountable, and registered framework built upon
  the spirit of zakat, sadqah, and voluntary giving."* — the page's core
  message, ready to use as-is or adapt.
- **p.19 — bank details**: already the subject of Plan 04's Contact & Bank
  Details setting; this plan doesn't re-source them, it reuses that same
  setting so there's one place they're ever entered or corrected.

As with Plan 04: this is reference material for the post-deploy content-entry
pass, not text this plan's PR commits to the repo.

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Page model | `DonatePage`, plain `RichTextField`s (message, how-to-give steps) | Predictable content, no flexibility needed — same reasoning Plan 04 used for About/Contact. |
| Bank details | Rendered from Plan 04's existing Contact & Bank Details setting, **not** re-entered as separate fields on `DonatePage` | One source of truth. If it lived in two places, a bank-detail correction would need two edits, and they'd eventually drift. |
| Zakat vs. Sadaqa framing | One page, explains both (Zakat has specific Islamic eligibility/calculation rules; Sadaqa is general voluntary giving) rather than two separate pages | Matches the source PDF's single unified message; splitting into two pages would be more structure than the content warrants. |
| "Another way to give" | A CTA to the Contact page (and/or direct `tel:`/`mailto:` links pulled from the same setting) for in-kind gifts, receipts, or questions | Keeps this page from needing any form/backend — consistent with Plan 04's Contact page decision (no contact form, no spam-handling surface). |
| Donate CTA styling | Amber (`#CE8A2C` light / `#E8B04A` dark) everywhere a donate link appears, per brand-guidelines.md | Already-established brand decision; this plan is what actually wires it into markup. |

## Task checklist (code — this plan's PR)

1. **`DonatePage` model** — message `RichTextField`, how-to-give
   `RichTextField` or a short `StreamField` if the steps benefit from
   structure (numbered list block); no bank-detail fields (reuses the
   setting).
2. **Template** — renders the message, then bank details pulled live from
   the Contact & Bank Details setting, then a "prefer another way to give?"
   CTA to Contact/`tel:`/`mailto:`. Amber styling on the primary action per
   brand-guidelines.md §2/§4.
3. **Wire up Home's CTA** — confirm `DonateCTABlock`'s link field can target
   this new page type (no code change needed if Plan 04 built it as a
   generic `PageChooserBlock`, per that plan's design — this step just
   verifies it).
4. **Wire up header/footer** — any existing donate link in nav/footer
   (added in Plan 03/04 as a placeholder) now resolves here.
5. **Tests** — smoke test (renders 200); a test that bank details shown on
   this page match the Contact & Bank Details setting (guards against ever
   accidentally duplicating/hardcoding them later).

## Content entry checklist (post-deploy, via Wagtail admin — not part of this PR)

1. `DonatePage` message and how-to-give copy, from source PDF p.18.
2. Point Home's `DonateCTABlock` at the new Donate page.
3. Point any header/footer donate link at the new page.
4. (Bank details themselves were already entered in Plan 04 — nothing to
   redo here.)

## Acceptance criteria

- The Donate page renders the Zakat/Sadaqa message and the live bank
  details from the shared setting — editing the setting updates this page
  with no code change or redeploy.
- No form, no payment widget, no third-party script on this page — matches
  CLAUDE.md's "no analytics or third-party scripts by default" guardrail.
- The donate CTA (wherever it appears — Home, header, footer) uses Amber,
  not Coral or Teal.
- `ruff check` and `pytest` pass in CI.

## Open questions for the maintainer

- Is the single-page Zakat + Sadaqa framing right, or does the clinic want
  them visually/structurally distinguished (e.g. separate sections with
  their own headings) rather than one blended message?
- Any specific "in-kind" giving options (medicine donations, equipment,
  volunteering) to mention alongside bank transfer, or keep this strictly
  to monetary giving for now?
