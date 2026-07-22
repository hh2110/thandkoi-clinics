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
- [ ] **C2.** Surface Anthropic API cost in the admin panel (needs a metering
      approach — Anthropic's API doesn't return cost per call; likely
      token-count × published rate, tracked per `IngestRun`/AI call and summed).
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
- [ ] **D2.** Relabel "Our impact so far" → "Our impact so far (updated at
      <date>)"; document/confirm how the figure is calculated (see open
      questions).
- [ ] **D3.** Implement "circle of care" on the home page (redesign, same
      underlying information — needs a design pass before implementation - i can do this with claude design).
- [ ] **D4.** Newsletter branding: the clay-lamp ("chiragh") image/motif; remove
      "چراغ شفا" from the Urdu home page per the maintainer's explicit ask (note:
      CLAUDE.md's project tagline currently includes "چراغ شفا" — this is a
      deliberate content change, not a doc contradiction; update CLAUDE.md's
      Bilingual section in the same change per the Stage 4 "docs are living" rule
      if the tagline is genuinely retired, or confirm it's page-scoped only).
- [ ] **D5.** Add a building photo to the home page — maintainer wants a few
      placement options proposed (e.g. hero background) before committing.
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
- [x] **D9.** Gallery: clicking a cropped thumbnail should open a full-size
      modal.
      **Done (2026-07-22, branch `feat/gallery-lightbox-modal`),** PR not yet
      opened. Native `<dialog>`, no JS library, per the site's minimal-JS
      convention.

  **Priority: P2** across the board — visible polish and content, not
  functional bugs. D3 and D5 need a short design/options pass before a task
  file is written (mirrors Stage 2 "design before building").

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

## Open questions (answer, not build)

These are the maintainer asking the team something, not requesting a feature —
answer directly, then decide whether the answer implies a task:

1. **"How is impact so far calculated?"** — trace and document the current
   calculation (likely in `apps/core/models.py` or a template tag); becomes D2
   if the answer needs restating on-page.
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

## Status (2026-07-22)

A1, B1–B7, C1, C3, C4, D1, D6, D7, D9 are **merged to `main`**: 8 PRs (#47–#54),
each reviewed (code-review-tc or a manual pass), fixed up, CI-green, and
squash-merged. The two flagged merge-order dependencies (the migration-number
collision between `feat/daily-report-ux-pass` and `feat/camp-report-upload-type`,
and the "department always empty" assumption needing
`chore/remove-provisional-schema-option` merged first) were both handled during
the merge sequence — `camp-report-upload-type` was rebased onto `main` after
the other two landed, its migration renumbered to `0005`, and its tests fixed
up where they still referenced the now-unregistered `clinic_daily_export_v1`
format.

Remaining, not yet ready to slice: B8/B9 (unblocked, not yet built this
round), C2, D2–D5, D8, E1, E2 — each still needs the design pass or
maintainer decision noted against it above.
