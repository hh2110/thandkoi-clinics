# Plan 05 — Donate Placeholder

_Status: In progress · Depends on: 01 Project foundation, 03 Design system & base templates, 04 Core content pages · Next: 06 Newsletters, Camp Reports & Gallery_

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
- A `DonatePage` with **distinct Zakat and Sadaqa sections** (each with its
  own heading and short description) and a bank-transfer "how to give"
  section.
- An **in-kind giving section** (medicine, equipment, volunteering, etc.)
  routing to Contact / `tel:` / `mailto:` to arrange — no form/backend.
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
| Zakat vs. Sadaqa framing | **One page, two structurally distinct sections** — a **Zakat** section and a **Sadaqa** section, each with its own heading and a short description (Zakat: specific Islamic eligibility/calculation rules; Sadaqa: general voluntary giving) | **Maintainer decision:** distinguish the two rather than blend them into one message. Still one page (not two), but the reader can clearly tell which form of giving is which. |
| In-kind giving | **Included** — a dedicated section listing in-kind options (e.g. **medicine donations, equipment, volunteering**) alongside monetary bank transfer, each routing to the Contact page / `tel:` / `mailto:` to arrange | **Maintainer decision:** yes, surface in-kind giving, not monetary-only. Keeps this page form-free/backendless — arranging an in-kind gift is a "contact us" case, consistent with Plan 04's no-contact-form decision. |
| "Another way to give" | A CTA to the Contact page (and/or direct `tel:`/`mailto:` links pulled from the same setting) for receipts or questions not covered by the giving sections above | Keeps this page from needing any form/backend — consistent with Plan 04's Contact page decision (no contact form, no spam-handling surface). |
| Donate CTA styling | Amber (`#CE8A2C` light / `#E8B04A` dark) everywhere a donate link appears, per brand-guidelines.md | Already-established brand decision; this plan is what actually wires it into markup. |

## Feature flag

**No flag** — deliberate, same reasoning as Plan 04: a single Wagtail page,
invisible until published in `/admin/`, so Wagtail's publish step is the gate.
Reuses Plan 04's existing setting (no new data surface). No online payment path
exists to gate. Ships on merge + deploy; the page is published and Home's donate
CTA pointed at it as post-deploy content steps.

## Precedent map

New-repo note: by this plan Plan 04 is merged, so nearly everything mirrors an
existing in-repo pattern — this is a small plan precisely because it reuses.

| Element | Precedent to mirror | Where |
|---|---|---|
| Plain `RichTextField` page model | Plan 04's About / Contact page models | Plan 04 (in repo) |
| Reusing the Contact & Bank Details setting (not re-entering fields) | Plan 04's `BaseSiteSetting` singleton | Plan 04 (in repo) |
| Section layout (CTA band, section rhythm) | Plan 03.5's `partials/sections/cta_band.html` + section classes | Plan 03.5 (in repo) |
| Amber donate-CTA styling | Plan 03 button styles + brand-guidelines.md §2/§4 (amber = Donate only) | Plan 03 + brand guide (in repo) |
| Setting-match guard test | Plan 04's "Contact page reflects the setting" test | Plan 04 (in repo) |
| **Zakat vs. Sadaqa two-section structure** | **No precedent** — a straightforward structural split; grounded in the maintainer decision + source PDF p.18, not invention | maintainer decision |

## Task checklist (code — this plan's PR)

1. **`DonatePage` model** — separate `RichTextField`s (or a short
   `StreamField`) for the **Zakat** section and the **Sadaqa** section (each
   heading + short description), a how-to-give section, and an **in-kind
   giving** section; no bank-detail fields (reuses the setting).
2. **Template** — renders the Zakat and Sadaqa sections distinctly, then bank
   details pulled live from the Contact & Bank Details setting, then the
   in-kind giving options, then a "prefer another way to give?" CTA to
   Contact/`tel:`/`mailto:`. Amber styling on the primary action per
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

1. `DonatePage` copy: the Zakat section, the Sadaqa section, how-to-give
   steps, and the in-kind giving options — message from source PDF p.18.
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

## Resolved questions (answered by the maintainer)

- **Zakat + Sadaqa framing** → **distinguish them**: one page, but two
  structurally distinct sections (each its own heading + short description),
  not one blended message.
- **In-kind giving** → **include it**: a dedicated section listing options
  such as medicine donations, equipment, and volunteering, alongside monetary
  bank transfer — each routing to Contact to arrange (no form/backend).

## Release plan

- **How it ships:** merge → additive migration → deploy pipeline (staging →
  verify → production). Post-deploy content steps: enter the Donate copy (source
  PDF p.18), then point Home's `DonateCTABlock` and any header/footer donate link
  at the new page (content edits, no redeploy).
- **Gating check:** smoke test + the bank-details-match-the-setting guard test
  green in CI; on staging, confirm the bank details render live from the shared
  setting, the primary action is **amber** (not coral/teal), and there is no
  form, payment widget, or third-party script on the page.
- **Who gets access:** the public (everyone), once published.
- **Who's informed:** maintainer (and whichever Administrator enters the copy).
  No external audience.
- **Rollback trigger:** unpublish the page or unset the CTA link in the admin
  (instant, no redeploy); code revert only for a model/migration defect.
