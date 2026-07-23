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
      **Done (2026-07-22, branch `fix/patient-count-mismatch`):** root cause was
      wrapped free-text continuation rows with no `MR #` counted as phantom
      visits; fixed + regression test added, PR not yet opened.

### Track B — Daily report page UX

- [x] **B1.** Center the blue-ribbon stat numbers.
- [x] **B2.** Fix dark-mode: the stat ribbon disappears (light-mode-only style bug).
- [x] **B3.** Relabel "By sex" → "By gender".
- [x] **B4.** Keep the Zakat vs. paid split; remove the new-vs-follow-up split.
- [x] **B5.** Remove the "by department" breakdown.
- [x] **B6.** Reduce the large vertical gaps between report sections.
- [x] **B7.** Reuse the "Our Work" page's intro-text pattern on the reports index
      and on every other thin-content page.
      **B1–B7 done (2026-07-22, branch `feat/daily-report-ux-pass`),** PR not
      yet opened. The same B3/B4/B5 fixes were also applied to the new camp
      upload report page (`feat/camp-report-upload-type`), since it shares the
      same parser limitations.
- [ ] **B8.** Claude-generated summary of free-text columns (Presenting
      Complaints, Investigation, Provisional Diagnosis, Prescribed Medicine,
      Doctor's/Nurse's/Dietitian's Notes, Diet & Drug Compliance, Plan).
- [ ] **B9.** Separate Claude prompt that flags which of those columns are
      empty, to prompt the clinic to fill them in.

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

### Track C — Admin panel

- [x] **C1.** Remove the now-unused "provisional schema" option from the upload
      format dropdown.
      **Done (2026-07-22, branch `chore/remove-provisional-schema-option`),**
      PR not yet opened. Kept the module (still used as test fixture data),
      just unregistered it from the dropdown.
- [x] **C2.** Surface Anthropic API cost in the admin panel (needs a metering
      approach — Anthropic's API doesn't return cost per call; likely
      token-count × published rate, tracked per `IngestRun`/AI call and summed).
      **Done (2026-07-23, branch `feat/admin-ai-cost-metering`),** PR not yet
      opened. New `AiCallLog` model (call site, model, input/output tokens,
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
- [x] **C3.** Add a "camp report" upload type: same `.xls` format as the daily
      export, plus a camp-title field on upload. Merge the "Reports" and "Camp
      Reports" nav items into one "Reports" menu with two sections (daily
      reports, other reports).
      **Done (2026-07-22, branch `feat/camp-report-upload-type`),** PR not yet
      opened. Added a `report_kind` discriminator so a camp and the clinic's
      own daily activity sharing a date never merge/collide — see that
      branch's commit message for the full design decision.
- [x] **C4.** Verify the configured Anthropic model is `claude-sonnet-5`
      end-to-end (CLAUDE.md says Opus for drafting/schema inference, Haiku for
      translation — confirm whether the maintainer wants Sonnet substituted in,
      or is asking to confirm the existing Opus/Haiku split; **open question**,
      see below).
      **Resolved (2026-07-22):** confirmed the split matched CLAUDE.md exactly
      (nothing was on Sonnet). Maintainer decision: keep `claude-haiku-4-5` for
      the daily summary sentence, switch newsletter drafting to
      `claude-sonnet-5` (branch `chore/newsletter-model-sonnet`).

  **Priority: P1** for C1/C3, **P2** for C2 (nice-to-have visibility, no
  functional blocker), **P0 (quick check, not a build)** for C4.

### Track D — Content & site pages

- [x] **D1.** Enlarge the top-left logo; consider icon-only (drop the wordmark).
      **Done (2026-07-22, branch `feat/bigger-logo`),** PR not yet opened.
      Swapped to the existing `logo-mark.svg` (icon-only), 2.5rem → 4rem.
- [ ] ~~**D5.** Add a building photo to the home page.~~ **Dropped (maintainer
      decision 2026-07-23)** — not part of this plan's remaining scope.
- [x] **D2.** Relabel "Our impact so far" → "Our impact so far (updated at
      <date>)"; document/confirm how the figure is calculated (see open
      questions).
      **Done (2026-07-23, branch `feat/impact-label-chiragh-branding`),** PR
      not yet opened. The figure was never computed — `ImpactStatBlock` is a
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
      **Done (2026-07-23, branch `feat/impact-label-chiragh-branding`),** PR
      not yet opened. Removed from two live occurrences — the site-wide
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
      **D6/D7 done (2026-07-22, branch `feat/donors-partners-page`),** PR not
      yet opened, placeholders throughout per maintainer decision. **Still
      needed from the maintainer: the Sugar Hospital and District Health
      Office logo files** — no image needed for named donors, by design.
- [ ] **D8.** Main nav items should support dropdown submenus (groundwork for D6
      and the merged Reports menu in C3).
      **Dropped for future implementation (maintainer decision 2026-07-23)** —
      not part of this round's remaining-work sessions; revisit as its own
      plan/task when nav complexity actually demands it.
- [x] **D9.** Gallery: clicking a cropped thumbnail should open a full-size
      modal.
      **Done (2026-07-22, branch `feat/gallery-lightbox-modal`),** PR not yet
      opened. Native `<dialog>`, no JS library, per the site's minimal-JS
      convention.

  **Priority: P2** across the board — visible polish and content, not
  functional bugs.

### Track E — Process & tooling

- [ ] **E1.** A repo skill that lets the maintainer request a website change and
      have Claude route it correctly: a code change, a Wagtail draft page, or a
      publish — aiming for an AI-native update workflow. Candidate first step
      toward a future "send a WhatsApp message to a thandkoi-clinics-assistant"
      flow.
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
- **D8 (nav dropdown submenus)** — dropped for future implementation
  (maintainer decision 2026-07-23). Condition to bring back: revisit once nav
  complexity (more top-level items, or another grouped menu beyond C3's merged
  Reports menu) actually demands it — not speculatively.

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

## Reference material

- Source feedback: maintainer's Google Doc, "Feedback" (2026-07-22 capture).
- [docs/architecture-and-ai-brief.md](../../docs/architecture-and-ai-brief.md) —
  overall design; Track B's AI items must be checked against this before
  slicing.
- [CLAUDE.md](../../CLAUDE.md) — privacy invariants (Track B8/B9 gate) and the
  Bilingual section (Track D4).
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
to revisit), D8 (nav dropdown submenus — parked until nav complexity actually
demands it, see "Parked, deliberately").

**Four sessions run in parallel (maintainer decision 2026-07-23), each its
own branch — status of each as of this write-up:**

1. **B8 + B9** — `feat/daily-report-freetext-summary`. Implemented, tested,
   through two rounds of code-review-tc fixes (a re-ingest-time draft
   blanking bug, a content-hash dedup decision reversed after a second review
   pass — see `ParsedVisitRow._canonical_tuple`'s comment — sanity-check
   bounds too tight for their own `max_tokens`, and cleanup). Re-review in
   progress; PR not yet opened.
2. **C2** — `feat/admin-ai-cost-metering`. Implemented, tested, through two
   rounds of code-review-tc fixes (a logging-failure-discards-a-good-response
   bug, a `cost_usd` precision bug that truncated small calls to $0.00).
   Re-review in progress; PR not yet opened.
3. **Track D remainder (D2 + D4)** — `feat/impact-label-chiragh-branding`.
   Implemented, tested, through code-review-tc fixes (a bare-caption
   rendering bug) plus a maintainer scope confirmation on D4 (site-wide
   footer removal was intended). Marked done above; PR not yet opened.
4. **E1 + E2 research** — done, no build. See
   [11-e1-e2-research-2026-07.md](11-e1-e2-research-2026-07.md).

None of the three code branches are merged yet — each still needs its
review loop to land clean, then a draft PR, then CI, before merge and
deploy.
