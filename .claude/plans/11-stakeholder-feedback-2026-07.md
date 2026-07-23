# Plan 11 — Stakeholder feedback triage (July 2026)

**One-line:** triage the maintainer's July 2026 review-round feedback (Google
Doc) into tracked, sequenced work — a backlog to slice into follow-up plans
(Stage 6), not a single-PR plan itself.

## Background — why now

The maintainer reviewed the live site and admin panel and left a long feedback
doc covering a data-integrity bug, daily-report UX, admin-panel features,
content/site changes, and process/tooling ideas. This plan exists to turn that
unstructured dump into a legible, prioritized set of tracks per Stage 1 of the
development lifecycle, so nothing is lost and nothing gets built on a guess.

**Source:** maintainer's Google Doc, "Feedback" (fetched 2026-07-22). Treat that
doc as a point-in-time capture — this plan is the durable, structured version;
the doc itself is not re-read going forward.

**Round 2 (2026-07-23 capture).** The same doc gained three more items after
B8/B9 shipped and merged that same day: the free-text summary (B8) renders
unstyled and is narratively too specific (a real re-identification risk, not
just polish), and the "Donors & Partners" nav item (D6) should come off the
main nav. Separately, the maintainer supplied a pre-built handoff bundle
(`~/Downloads/logo-update.zip`) fixing a dark-theme contrast bug on the
header logo (`logo.svg`'s dark wordmark goes near-invisible on the dark
theme) — not from the doc, but scoped into this plan as the same kind of
small maintainer-reported item. Filed as B10/B11 and D10/D11 below, same
"point-in-time capture, not re-read" rule as round 1.

## Milestones by track

### Track A — Data pipeline integrity (highest priority)

- [x] **A1. Patient-count mismatch bug.** `TKC july 20th Stat.xls` (7 real
      patients) was uploaded and the pipeline reported 17 on the
      [2026-07-20 daily report](https://thandkoiclinics.com/en/reports/2026-07-20/).
      Likely a parsing/aggregation bug in `apps/pipeline/parser_tkc_daily_v1.py`
      or `DailyAggregate` computation — needs reproduction against the real file
      (`~/Downloads/TKC july 20th Stat.xls`) before a fix. Distinct from the
      500-error fix already shipped (`fix/upload-xls-500`, #46).
      **Priority: P0** — production data-integrity bug, user-facing wrong numbers.
      **Done (2026-07-22, branch `fix/patient-count-mismatch`),** merged PR
      #47. Root cause was wrapped free-text continuation rows with no `MR #`
      counted as phantom visits; fixed + regression test added.

### Track B — Daily report page UX

- [x] **B1.** Center the blue-ribbon stat numbers.
- [x] **B2.** Fix dark-mode: the stat ribbon disappears (light-mode-only style bug).
- [x] **B3.** Relabel "By sex" → "By gender".
- [x] **B4.** Keep the Zakat vs. paid split; remove the new-vs-follow-up split.
- [x] **B5.** Remove the "by department" breakdown.
- [x] **B6.** Reduce the large vertical gaps between report sections.
- [x] **B7.** Reuse the "Our Work" page's intro-text pattern on the reports index
      and on every other thin-content page.
      **B1–B7 done (2026-07-22, branch `feat/daily-report-ux-pass`),** merged
      PR #49. The same B3/B4/B5 fixes were also applied to the new camp
      upload report page (`feat/camp-report-upload-type`), since it shares the
      same parser limitations.
- [x] **B8.** Claude-generated summary of free-text columns (Presenting
      Complaints, Investigation, Provisional Diagnosis, Prescribed Medicine,
      Doctor's/Nurse's/Dietitian's Notes, Diet & Drug Compliance, Plan).
- [x] **B9.** Separate Claude prompt that flags which of those columns are
      empty, to prompt the clinic to fill them in.
      **B8/B9 done (2026-07-23, branch `feat/daily-report-freetext-summary`,
      merged PR #60),** initially shipped review-gated (draft fields + an
      approval checkbox), then widened to auto-publish (maintainer decision
      2026-07-23, `feat/freetext-summary-autopublish`) — same CLAUDE.md
      invariant #4 exception as the existing daily-summary sentence, no
      separate review step.

  **Priority: P1.**

  **Grounding gap (Stage 3) — resolved, maintainer decision 2026-07-22.**
  Plan 08's de-identification only covers **diagnosis** (mapped to a fixed
  category, raw text never persisted — `.claude/plans/08-data-pipeline.md`
  "De-identification" row), so B8/B9's other free-text columns looked like a
  CLAUDE.md invariant #2 conflict (never send patient data to a model). **The
  maintainer confirmed the clinic software's data-entry UI does not allow PII
  to be entered into these fields in the first place** — Presenting
  Complaints/Investigation/Notes/Plan are structurally free of patient
  identifiers by construction, not by a scrub step this codebase would need to
  build. B8/B9 are unblocked on that basis: the columns may be sent to Claude
  as captured, unmodified. This is a decision about *these specific columns*
  only — it does not reopen invariant #2 generally, and any *new* free-text
  column added later needs the same question asked explicitly, not assumed.

- [ ] **B10 (round 2, 2026-07-23).** Format B8's free-text summary to match
      the site's prose conventions. Currently
      `apps/pipeline/templates/pipeline/daily_report_page.html` dumps the
      whole summary into one raw `<p>{{ page.freetext_summary }}</p>`
      (line 56) — no headings, paragraphs, or lists, unlike the rest of the
      page (the gender/zakat breakdowns use `<ul class="prose"><li>...`) or
      the newsletter body (`apps/core/templates/core/newsletter_page.html`,
      real block-level HTML inside `.prose`). Mirror that pattern instead of
      the single-string dump.
      **Priority: P2** — cosmetic, no privacy or correctness stakes.
- [ ] **B11 (round 2, 2026-07-23).** Tighten B8's free-text summary so it
      can't produce individually-identifying narrative combinations. The
      maintainer's feedback (citing HHS/HIPAA Safe Harbor guidance) flags
      that combining a specific condition with an exact duration and
      circumstance — e.g. "recent miscarriage" + "pustules on the face for 5
      days" — acts as a fingerprint even with no name attached, and asks for
      aggregated/thematic phrasing instead (their example: "gastrointestinal
      distress (45%), musculoskeletal pain (30%)...").
      **Priority: P0** — real patient re-identification risk on a page that
      auto-publishes with no human review (CLAUDE.md invariant #4's
      exception).

      **Grounding (Stage 3) — resolved, maintainer decision 2026-07-23.**
      Confirmed against the code: `apps/pipeline/ai.py`'s
      `_FREETEXT_SUMMARY_SYSTEM_PROMPT` (~lines 319–326) asks the model to
      "summarize common themes" and forbids attributing anything to a
      *specific patient*, but has no instruction against combining a
      specific condition with an exact duration/circumstance into one
      narrative sentence — exactly the gap the maintainer flagged. Two ways
      to fix it were weighed: (a) tighten the prompt only — ban exact
      durations, ban single-case detail combinations, require
      frequency/thematic language; or (b) rebuild as computed categorical
      aggregation (Python-side theme counts/percentages, comparable effort
      to Plan 08's diagnosis-category mapping, closer to the doc's own
      numeric example and to CLAUDE.md invariant #3's "numbers are
      deterministic"). **Maintainer decision: (a), prompt-only** — smaller,
      faster, and addresses the sharpest concern (the fingerprint
      combination) without restructuring the pipeline. Categorical
      aggregation is parked (see "Parked, deliberately") rather than
      dropped. This change is scoped to *wording only* — it does not reopen
      whether the seven columns' raw text may reach the model (still yes,
      per the B8/B9 grounding above), and CLAUDE.md invariant #4's
      auto-publish exception conditions (fixed template, tested payload,
      non-blocking failure) still apply unchanged.

- [x] **B12 (2026-07-23).** Visual redesign of the daily report page, from a
      maintainer-supplied design handoff (`daily-report-update.zip`): three
      headline stats (Patients seen / Zakat / Regular, "New patients"
      dropped); "By diagnosis category" removed entirely; "By gender" + "By
      age band" consolidated into one Breakdown block (Gender 1/3 width
      beside Age 2/3, equal height); age rebanded to four fixed display
      bands (0–5, 6–18, 19–55, 56+) each with a person glyph; empty-columns
      flag renders as labelled chips instead of raw markdown text; free-text
      notes summary capped at ~50 words.
      **Done (2026-07-23, branch `feat/daily-report-redesign-b12`),** PR not
      yet opened.

      **Decision — age-band remap, no data migration (maintainer decision,
      2026-07-23).** Rebanding from the original six bands
      (0-4/5-12/13-17/18-40/41-60/61+) to the four new ones needs
      `parser_registry.age_band_for` and `DeidentifiedVisit.AGE_BAND_*`
      updated either way. The open question was whether to also add a data
      migration remapping *already-persisted* rows onto the new bands.
      Investigation found this can't be done accurately:
      `DeidentifiedVisit.age_band` only ever stores the band, never the raw
      age it was derived from (de-identification invariant #1), and three
      old bands straddle a new boundary — 5-12, 18-40, and, worst, 41-60
      (spanning both new 19-55 and 56+, up to ~25% of that band on the wrong
      side of the cut with no way to recover which rows). A majority-span
      approximation was proposed and rejected — **maintainer decision:
      delete pre-B12 ingests and re-upload the source exports instead**,
      which recomputes everything from scratch under the new bands via
      `age_band_for`, with no approximation. This PR therefore ships only
      the schema-level migration (`0010_alter_deidentifiedvisit_age_band`,
      choices metadata only, no data operation) — re-ingesting historical
      dates is a separate, manual, maintainer-run step, not part of this
      branch.

      **Reconciled against B10/B11 at rebase time.** B12 was branched off
      `main` before PR #74 ("forbid markdown in empty-columns-flag prompt;
      drop diagnosis-category section") landed, so `apps/pipeline/ai.py` and
      `apps/pipeline/tests.py` had overlapping edits to the freetext-summary
      and empty-columns-flag prompts — both independently converged on the
      same ~50-word cap (`max_tokens=120`, `MAX_FREETEXT_SUMMARY_LENGTH=600`).
      Resolved by rebasing B12 onto post-#74 `main`: kept #74's freetext-
      summary wording (it already dropped B12's own redundant "if a column
      has no entries, say so" clause) and kept B12's JSON-array restructure
      of the empty-columns-flag prompt (superseding #74's plain-sentence
      fix, since the chip UI needs a parseable list, not prose).

### Track C — Admin panel

- [x] **C1.** Remove the now-unused "provisional schema" option from the upload
      format dropdown.
      **Done (2026-07-22, branch `chore/remove-provisional-schema-option`),**
      merged PR #48. Kept the module (still used as test fixture data), just
      unregistered it from the dropdown.
- [x] **C2.** Surface Anthropic API cost in the admin panel (needs a metering
      approach — Anthropic's API doesn't return cost per call; likely
      token-count × published rate, tracked per `IngestRun`/AI call and summed).
      **Done (2026-07-23, branch `feat/admin-ai-cost-metering`),** merged PR
      #58 (see Status below for the rebase/review detail). New `AiCallLog`
      model (call site, model, input/output tokens,
      computed cost, timestamp) logged once per real Anthropic call in
      `apps.pipeline.ai` — including once per tool-use turn in the monthly
      newsletter's multi-turn loop. Cost computed via a new
      `apps.pipeline.ai_pricing` module holding Anthropic's published
      per-model USD-per-million-token rates (fetched live from
      platform.claude.com/docs/en/about-claude/pricing, 2026-07-23; Sonnet 5
      is on introductory pricing through 2026-08-31 — the module's comment
      flags the standard-rate update needed on that date). Registered as a
      read-only Wagtail snippet mirroring `NewsletterDraftRunViewSet`, with a
      running cost total shown above the listing. Deliberately no FK from
      `AiCallLog` back to `IngestRun`/`NewsletterDraftRun`/`DailyAggregate` —
      the three call sites have no common triggering record to hang one off
      (see the model's docstring for the per-call-site reasoning).
      **Follow-up (2026-07-23, branch `fix/meter-freetext-and-empty-columns-calls`):**
      the maintainer noticed the free-text summary (B8, doctor/nurse notes)
      never showed up in the cost log — only the daily-summary sentence did.
      Root cause: B8/B9 (`feat/daily-report-freetext-summary`, PR #60)
      shipped *before* this C2 branch, and neither branch wired the other's
      call sites in (`_draft_short_text`'s own docstring said as much).
      Fixed: `draft_freetext_summary`/`draft_empty_columns_flag` now pass
      `on_response` just like `draft_daily_summary_sentence`, with two new
      `CALL_SITE_FREETEXT_SUMMARY`/`CALL_SITE_EMPTY_COLUMNS_FLAG` choices on
      `AiCallLog`.
- [x] **C3.** Add a "camp report" upload type: same `.xls` format as the daily
      export, plus a camp-title field on upload. Merge the "Reports" and "Camp
      Reports" nav items into one "Reports" menu with two sections (daily
      reports, other reports).
      **Done (2026-07-22, branch `feat/camp-report-upload-type`),** merged PR
      #50. Added a `report_kind` discriminator so a camp and the clinic's
      own daily activity sharing a date never merge/collide — see that
      branch's commit message for the full design decision.
      **2026-07-23 update:** this feature was later removed entirely
      (maintainer decision — no generic/auto-parsed camp report system
      wanted; see branch `chore/remove-camp-upload-feature`). The
      `CampUploadReportPage` model, the `report_kind` discriminator, and the
      upload form's camp-title field are all gone; `CampReportPage` is
      hand-authored only again, with a simplified field set (see the
      2026-07-23 note on Plan 06).
- [x] **C4.** Verify the configured Anthropic model is `claude-sonnet-5`
      end-to-end (CLAUDE.md says Opus for drafting/schema inference, Haiku for
      translation — confirm whether the maintainer wants Sonnet substituted in,
      or is asking to confirm the existing Opus/Haiku split; **open question**,
      see below).
      **Resolved (2026-07-22):** confirmed the split matched CLAUDE.md exactly
      (nothing was on Sonnet). Maintainer decision: keep `claude-haiku-4-5` for
      the daily summary sentence, switch newsletter drafting to
      `claude-sonnet-5` (branch `chore/newsletter-model-sonnet`, merged PR
      #54).

  **Priority: P1** for C1/C3, **P2** for C2 (nice-to-have visibility, no
  functional blocker), **P0 (quick check, not a build)** for C4.

### Track D — Content & site pages

- [x] **D1.** Enlarge the top-left logo; consider icon-only (drop the wordmark).
      **Done (2026-07-22, merged PR #51).** ~~Swapped to `logo-mark.svg`
      (icon-only)~~ — that first pass was caught and reverted by code review
      within the same PR: `docs/brand-guidelines.md` reserves the icon-only
      mark for narrow contexts (avatar/app icon) and specifies the full
      lockup for header/footer/print, and dropping the wordmark would have
      removed the only visible on-page text naming the clinic for sighted
      visitors. Landed state: stays on the full `logo.svg` lockup, sized to
      `height:7rem` (~150px wide) to clear brand-guidelines.md's own ~140px
      legibility floor for the full lockup — this is what D11 (round 2)
      below builds on. **Correction (2026-07-23, this file):** this entry
      previously said "icon-only," which described the PR's first commit,
      not what actually merged — fixed as a stale-doc defect found while
      researching D11.
- [ ] ~~**D5.** Add a building photo to the home page.~~ **Dropped (maintainer
      decision 2026-07-23)** — not part of this plan's remaining scope.
- [x] **D2.** Relabel "Our impact so far" → "Our impact so far (updated at
      <date>)"; document/confirm how the figure is calculated (see open
      questions).
      **Done (2026-07-23, branch `feat/impact-label-chiragh-branding`),**
      merged PR #59. The figure was never computed — `ImpactStatBlock` is a
      hand-typed admin field; this adds an optional `as_of` date the admin
      sets manually alongside it. Documented in
      [docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md),
      with live computation deferred to the new Track F candidate below.
- [x] **D3.** Implement "circle of care" on the home page (redesign, same
      underlying information).
      **Done (2026-07-23, branch via PR #56),** merged to `main`. Six-wedge
      `CircleOfCareBlock` on `HomePage.body`, CMS-editable, capped at one per
      page.
- [x] **D4.** Newsletter branding: the clay-lamp ("chiragh") image/motif; remove
      "چراغ شفا" from the Urdu home page per the maintainer's explicit ask.
      **Done (2026-07-23, branch `feat/impact-label-chiragh-branding`),**
      merged PR #59. Removed from two live occurrences — the site-wide
      footer (renders on every page, not Home alone) and the Home page's
      hero tagline — plus matching seed/fixture data, and updated CLAUDE.md's
      Bilingual section. **Scope confirmed with the maintainer (2026-07-23):**
      the site-wide footer removal was intended, not Home-page-only — no
      further scope change needed. No chiragh asset exists yet, so a
      placeholder (mirroring the Donors & Partners page's pattern) was added
      to the newsletter archive page pending a real asset.
- [x] **D6.** New "Donors & Partners" page/menu item: organizational partners
      (Sugar Hospital, District Health Office) and named individual/in-kind
      donors (e.g. Basit — X-ray plant; one family — water coolers).
- [x] **D7.** Partner-logo carousel + in-kind donor examples on the donate page
      (style reference: [fwdr.org.pk](https://fwdr.org.pk/)); make "Thandkoi
      Clinics" more visually prominent on the home page.
      **D6/D7 done (2026-07-22, branch `feat/donors-partners-page`),** merged
      PR #53, placeholders throughout per maintainer decision. **Still
      needed from the maintainer: the Sugar Hospital and District Health
      Office logo files** — no image needed for named donors, by design.
- [x] **D8.** Main nav items should support dropdown submenus (groundwork for D6
      and the merged Reports menu in C3).
      **Revisited same day (2026-07-23)** — dropped that morning as "not part
      of this round," then reopened hours later by a maintainer design
      handoff (`~/Downloads/header.zip`) collapsing the header to a single
      row with a "More" dropdown (Team/Gallery/Contact). **Done (2026-07-23,
      branch `feat/single-row-header`),** merged PR #94 — plain nested
      `<details>`, no new JS.
- [x] **D9.** Gallery: clicking a cropped thumbnail should open a full-size
      modal.
      **Done (2026-07-22, branch `feat/gallery-lightbox-modal`),** merged PR
      #52. Native `<dialog>`, no JS library, per the site's minimal-JS
      convention.
- [ ] **D10 (round 2, 2026-07-23).** Remove the "Donors & Partners" nav item.
      **Grounding — resolved, maintainer decision 2026-07-23.** The doc says
      "delete them," which read ambiguous — nav link only, or the whole
      page? Checked before deciding: `DonatePage.get_context()`
      (`apps/core/models.py`) reads
      `DonorsPartnersPage.objects.live().first()` live and feeds it to the
      same `_partner_items()`/`_donor_items()` helpers D7's carousel uses —
      deleting the page would silently empty that carousel, not just remove
      a nav entry. **Maintainer decision: nav-only removal.** Remove the
      link (and its stale D8 dropdown-groundwork comment) from
      `templates/partials/nav.html`; the page, its content model, and the
      donate-page carousel stay live and reachable by direct URL.
      **Priority: P1.**
- [ ] **D11 (round 2, 2026-07-23).** Fix the header logo's dark-theme
      contrast bug: `logo.svg` has a hard-coded dark-navy wordmark, so on
      the dark theme "THE THANDKOI" sits near-invisible on the dark
      background. The maintainer supplied a ready-to-apply handoff bundle
      (`~/Downloads/logo-update.zip` → `handoff/logo-dark-fix/`, see
      `PROMPT.md` there) shipping both lockups and a CSS-only
      `:root[data-theme]` / `prefers-color-scheme` swap — no JS, no FOUC.
      Verified compatible with current `main` before accepting as-is: the
      live `.site-header__logo` rule (`static/css/components.css`) uses the
      full `logo.svg` lockup at `height:7rem; width:auto` — exactly what the
      bundle's CSS and `header.html` assume (D1's icon-only-mark idea was
      reconsidered and reverted per that file's own comment; the full
      lockup stayed), so this is a straight merge: copy
      `logo-reversed.png` into `static/images/`, apply the bundle's
      `header.html`, merge `_site-header__logo.css` into the existing
      `.site-header__logo` rule. The bundle's own notes flag a fully-vector
      SVG reversed lockup as a possible longer-term follow-up (needs
      re-tracing `logo.svg`, since it's a single merged auto-trace that
      can't be recoloured) — parked, not requested yet.
      **Priority: P1** — accessibility/legibility bug, dark theme is a
      first-class supported mode on this site.

  **Priority: P2** across the board for D1–D9 — visible polish and content,
  not functional bugs. D10/D11 carry their own priorities above.

### Track E — Process & tooling

- [x] **E1.** A repo skill that lets the maintainer request a website change and
      have Claude route it correctly: a code change, a Wagtail draft page, or a
      publish — aiming for an AI-native update workflow. Candidate first step
      toward a future "send a WhatsApp message to a thandkoi-clinics-assistant"
      flow.
      **Done (2026-07-23, branch `feat/route-change-request-skill`),** PR not
      yet opened. `.claude/skills/route-change-request/SKILL.md` — a
      classify-and-handoff skill, no new infrastructure per the research
      doc's recommendation: gathers context (CLAUDE.md, open plan items, the
      Wagtail page models), classifies into code change / Wagtail draft
      (`save_revision()` only, never `.publish()`, mirroring
      `newsletter_drafting.py`) / publish action, asks rather than guessing
      on ambiguity, and documents six worked examples covering all three
      routes plus a non-route (a question) and an ambiguity case.
- [ ] **E2.** Evaluate ingesting feedback already sitting in a WhatsApp group —
      maintainer flagged [whatsapp-claude-plugin](https://github.com/rich627/whatsapp-claude-plugin)
      as a possible option; needs a short options review (that plugin vs. a
      lighter alternative) before any build.

  **Priority: P2.** E1 has real leverage (every future small site edit gets
  cheaper) but is itself a small design exercise before it's a task file.

  **Options review done (2026-07-23):** see
  [11-e1-e2-research-2026-07.md](11-e1-e2-research-2026-07.md) — recommends
  building E1 now (a `route-change-request` skill, no new infra needed) and
  confirms E2's defer with a refinement (the flagged `whatsapp-claude-plugin`
  doesn't actually solve "import existing history"; manual copy-paste
  remains the durable zero-build answer unless this becomes a recurring
  pain point).

## Open questions (answer, not build)

These are the maintainer asking the team something, not requesting a feature —
answer directly, then decide whether the answer implies a task:

1. ~~**"How is impact so far calculated?"**~~ **Answered, via D2
   (2026-07-23):** it isn't — `ImpactStatBlock` is a hand-typed admin field,
   not a computation. Documented in
   [docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md),
   with live computation deferred to the new Track F candidate below.
2. **"Does the home-page 'latest daily report' link expect a picture?"** —
   check the current template/content model for that link and confirm.
3. **"How do I upload a newsletter?"** (example file: "May June TTC Newsletter"
   in `~/Downloads`) — walk through the existing Wagtail flow (Plan 06 shipped
   Newsletter archives); if the flow is unclear, that's a UX gap, not a doc gap.
4. **"How do I do a monthly report — and could reports be generic (monthly,
   camp, or anything)?"** — needs a short workflow design (Stage 2) before it
   becomes a task; likely folds into C3's camp-report work as a shared "report
   type" concept rather than a bespoke monthly path.
5. **Contact/Follow section updates** — maintainer needs to supply the actual
   content (what to display) before this is actionable; not blocked on us.

## Parked, deliberately

- **WhatsApp group feedback ingestion (E2)** — parked pending the short options
  review; revisit once E1 (the update-routing skill) exists, since the same
  routing logic likely underpins both.
- **Bilingual generation of any new content** (D4's Urdu tagline change is a
  removal, not generation, so it's unaffected) — already parked repo-wide per
  the Plans README "Out of scope" section; nothing here reopens it.
- **D5 (home-page building photo)** — dropped (maintainer decision
  2026-07-23), not just deferred; no condition noted for revisiting, so treat
  as fully out of scope unless the maintainer raises it again.
- **D8 (nav dropdown submenus)** — no longer parked; reopened same day (see
  D8's own row above) via `feat/single-row-header`, PR #94.
- **B11's categorical aggregation** (Python-computed theme counts/percentages
  for the free-text summary, matching the doc's own "GI 45%, MSK 30%..."
  example) — parked in favour of the prompt-only fix (maintainer decision
  2026-07-23). Condition to revisit: the tightened prompt still produces
  identifying-feeling output in practice, or the maintainer asks for the
  doc's numeric-example style directly.
- **D10's page/content deletion** — parked; nav-only removal for now
  (maintainer decision 2026-07-23). Condition to revisit: the maintainer
  explicitly asks to remove the page itself, at which point D7's carousel
  needs its own data-source decision too.
- **D11's reversed SVG wordmark** — parked; the handoff bundle's PNG lockup
  ships as-is. Condition to revisit: the maintainer explicitly asks for a
  fully-vector header (the handoff's own `PROMPT.md` notes this needs a
  re-trace of `logo.svg`, not just a recolour).

## Candidates from notes (not yet milestones)

### F. Multi-day camp upload + live "impact so far" aggregation (2026-07-23)

Maintainer idea, captured raw, not yet slotted into a session:

- **F1. Multi-day camp file upload.** A single camp-report upload may cover
  several calendar days of data (currently C3's camp upload assumes one file
  = one date + one camp title). Instead: parse the file, group rows by date,
  and auto-generate one daily-report page per distinct date found in the
  file, each carrying its own `DailyAggregate`.
- **F2. Live "impact so far" home-page stats.** Currently `ImpactStatBlock`
  (`apps/core/blocks.py:19-35`) is a hand-typed `CharBlock` — its own docstring
  already anticipates this: "Real figures are entered by hand for now; Plan
  08's pipeline supplies computed ones later." F2 is that later: replace (or
  supplement) the hand-typed stat values with a live aggregation across
  `DailyAggregate` rows (sum of visits/patients etc., across daily + camp
  reports), so the home page reflects real cumulative totals rather than a
  manually maintained string. This is the natural pairing with F1: more
  camp-day reports flowing in only matters to "impact so far" if that number
  is actually computed from them.

**Maintainer decisions (2026-07-23), resolving the open questions:**

- **Upload scope:** both upload types — generalize the date-grouping/split
  logic so a daily-clinic export *or* a camp upload may contain multiple
  dates in one file, each producing its own report page.
- **Stat scope:** keep camp-sourced numbers distinguishable from regular
  clinic numbers in the live aggregate (e.g. "X clinic patients + Y camp
  patients"), not folded into one combined total — `report_kind` (from C3)
  is the natural discriminator to aggregate on separately.
- **Time window:** all-time since first upload — sum every `DailyAggregate`
  row ever ingested, matching the current hand-typed framing ("467+ children
  treated to date").

**Follow-up action:** still needs its own short Stage 2 planning pass before
it's sliced into tasks — specifically: does the parser already carry a
per-row date column to group on for both upload formats, or does that need
confirming per format first; and how `DailyAggregate` should be queried
per-`report_kind` for the live stat without a per-request full-table scan
becoming a home-page performance concern as data grows.

**F2's Stage 2 planning pass is done:** see
[11-f2-live-impact-stats-planning.md](11-f2-live-impact-stats-planning.md)
(2026-07-23) — settles the data layer (a new `apps/pipeline/impact_stats.py`
module, DB-side grouped `Sum()`, no new index/caching needed at this clinic's
scale), confirms `ImpactStatsBlock` stays untouched with the live stats as a
new unconditional section mirroring `get_latest_report()`'s pattern, and
notes F2 has no dependency on F1 — it works today against whatever
`DailyAggregate` rows already exist. F1 (multi-day upload) still needs its
own planning pass before either is sliced into a numbered plan.

## Reference material

- Source feedback: maintainer's Google Doc, "Feedback" (2026-07-22 capture;
  round 2 items B10/B11/D10 from the same doc, 2026-07-23 capture).
- Handoff bundle: `~/Downloads/logo-update.zip`
  (`handoff/logo-dark-fix/PROMPT.md`), maintainer-supplied 2026-07-23,
  source for D11.
- [docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md) —
  overall design; Track B's AI items must be checked against this before
  slicing.
- [CLAUDE.md](../../CLAUDE.md) — privacy invariants (Track B8/B9/B11 gate) and
  the Bilingual section (Track D4).
- [.claude/plans/08-data-pipeline.md](08-data-pipeline.md) — current
  de-identification scope, cited in the Track B grounding gap.
- [fwdr.org.pk](https://fwdr.org.pk/) — style reference for Track D7.
- [whatsapp-claude-plugin](https://github.com/rich627/whatsapp-claude-plugin) —
  candidate for Track E2.

## Status (2026-07-23)

A1, B1–B7, C1, C3, C4, D1, D3, D6, D7, D9 are **merged to `main`**: 9 PRs
(#47–#54, #56), each reviewed (code-review-tc or a manual pass), fixed up,
CI-green, and squash-merged. The two flagged merge-order dependencies (the
migration-number collision between `feat/daily-report-ux-pass` and
`feat/camp-report-upload-type`, and the "department always empty" assumption
needing `chore/remove-provisional-schema-option` merged first) were both
handled during the merge sequence — `camp-report-upload-type` was rebased onto
`main` after the other two landed, its migration renumbered to `0005`, and its
tests fixed up where they still referenced the now-unregistered
`clinic_daily_export_v1` format. D3 landed later as PR #56, migration
renumbered to `0007` for the same reason.

**Dropped, not slotted into any session:** D5 (building photo — no condition
to revisit). D8 (nav dropdown submenus) was dropped here too, same day, but
reopened hours later — see D8's own row above.

**Four sessions run in parallel (maintainer decision 2026-07-23), each its
own branch:**

1. **B8 + B9** — `feat/daily-report-freetext-summary`, PR #60, merged. Went
   through several rounds of code-review-tc (a re-ingest-time draft-blanking
   bug, a content-hash dedup decision reversed after a second review pass —
   see `ParsedVisitRow._canonical_tuple`'s comment — sanity-check bounds too
   tight for their own `max_tokens`, Urdu text getting JSON-escaped before
   reaching the model, a wrapped-continuation-row data-loss bug, and
   cleanup). Shipped review-gated (draft fields + an admin approval
   checkbox) — see the follow-up below for why that changed.
2. **C2** — `feat/admin-ai-cost-metering`, PR #58, merged (rebased onto
   main after B8/B9 to resolve a migration-number collision, same pattern as
   past merges in this plan — renumbered `0006`/`0007` to `0007`/`0008`).
   Went through several rounds of code-review-tc (a logging-failure-
   discards-a-good-response bug, a `cost_usd` precision bug that truncated
   small calls to $0.00, and cleanup).
3. **Track D remainder (D2 + D4)** — `feat/impact-label-chiragh-branding`,
   PR #59, merged. Fixed a bare-caption rendering bug via code-review-tc,
   plus a maintainer scope confirmation on D4 (site-wide footer removal was
   intended).
4. **E1 + E2 research** — done, no build. See
   [11-e1-e2-research-2026-07.md](11-e1-e2-research-2026-07.md).

Plus a status-tracking session (`docs/plan-11-status-2026-07-23`, PR #57,
merged) for this file's own updates.

**Follow-up, same day:** B8/B9 shipped review-gated per CLAUDE.md invariant
#4's default rule (new AI-authored content needs human approval before
publishing). The maintainer then decided to widen invariant #4's one narrow
exception (previously scoped only to the daily-summary sentence, Plan 08) to
also cover B8's free-text summary and B9's empty-columns flag — both now
auto-publish alongside the numbers, same as the sentence. Branch
`feat/freetext-summary-autopublish` drops the `_draft`/`_approved` fields in
favour of plain `freetext_summary`/`empty_columns_flag` fields, and CLAUDE.md
invariant #4 is amended with the dated widening note.

**Unrelated to this plan, landed on `main` during the same session:** PR #61,
`fix(pipeline): drop Other/unknown and Unrecorded rows from report
gender/zakat cards` — bundled into the same deploy as this plan's work
simply because it merged to `main` first; not part of Plan 11's scope.

**Round 2 (2026-07-23), triaged not yet built:** B10, B11, D10, D11 above —
scoped, grounded, and decided (each has a maintainer decision recorded
inline) but no branches opened yet. Expected as four independent
branches/PRs, no cross-track dependency: `fix/freetext-summary-formatting`
(B10), `fix/freetext-summary-privacy` (B11), `chore/remove-donors-nav`
(D10), `fix/logo-dark-theme` (D11) — names indicative, confirm at
branch-creation time. Each goes through `code-review-tc` before a draft PR,
per CLAUDE.md's per-branch review rule; B11 is P0 (real re-identification
risk on an auto-publishing page) and should be sequenced first among the
four.
