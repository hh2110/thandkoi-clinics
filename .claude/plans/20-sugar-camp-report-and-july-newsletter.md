# Plan 20 — Sugar Camp report (6 Aug 2026) + July 2026 newsletter

**Status:** 📝 Drafted · **Date:** 2026-08-10

One-line summary: publish the 6 August 2026 Free Sugar Camp as a
`CampReportPage` (content only, no code), plan the July 2026 issue of the
Thandkoi Beacon against the *real* July figures, and decide what to do about
the 93 camp attendees that are missing from the data pipeline.

## Why this is one plan, and what needs a PR

Two of the three tracks are **content, not code** — the models already exist
and the inauguration report is the working template:

| Track | What it is | Needs a branch/PR? |
|---|---|---|
| A — Sugar Camp report | A new `CampReportPage`, same fields the Inauguration Report already uses | **No.** Content op — see [content-operations.md](../../docs/content-operations.md) |
| B — July newsletter | A new `NewsletterPage` using the existing Beacon blocks | **No** for the page itself; the *editorial decisions* below are the plan |
| C — Camp data in the pipeline | Parser/ingest change so a camp export can coexist with a normal OPD day | **Yes** — real code, needs its own plan + PR once decided |

This file exists for Track B's decisions and Track C's findings. Track A's
content is written out below ready to enter, and needs no code at all.

---

## Source material and how it was verified

- **`Camp Attendance Report.xls`** (maintainer's Downloads, 2026-08-10) —
  the clinic software's patient-level export for 6 Aug 2026. **PHI.** Parsed
  in memory only via the repo's own `TkcDailyActivityV1Parser` plus a
  read-only pandas pass for the columns the parser deliberately ignores
  (fees, vitals, address). Nothing was written to disk or the database, and
  no raw row was printed. Per invariant #5 the file stays out of the repo.
- **`WhatsApp Image 2026-08-03 at 09.04.31 (1).jpeg`** — a finished-looking
  "THANDKOI BEACON / MONTHLY NEWSLETTER / JULY 2026" one-page design.
  Treated as a **proposal**, not a source of truth; every figure on it was
  checked against production.
- **`sugar-camp-pamphlet.png`** (Downloads) — the camp's own promotional
  pamphlet, which supplies the camp's name, partner, time and service list.
- **Production `pipeline_dailyaggregate`** (Neon `dawn-dream-80048612`),
  read-only, for the real July figures. De-identified counts only.
- **`/en/camp-reports/inauguration-report/`** — the live precedent Track A
  mirrors.

---

## Track A — Free Sugar Camp report ✅ Published 2026-08-10, as a newsletter issue

**Live at `/en/newsletters/free-sugar-camp/`** (page id 77), in the
newsletter/Beacon format.

### Why it moved out of the camp-reports archive

First published as a `CampReportPage` (id 76) at
`/en/camp-reports/free-sugar-camp-report/`. The maintainer then asked for the
newsletter's format instead. That is **not** something `CampReportPage` can
do: its `narrative` is a plain `RichTextField` and its `photos` StreamField
accepts only `ConsentedImageBlock`, so the impact stat band, highlights and
"In focus" splits — all newsletter-only blocks — would need a new StreamField,
a migration, a template rewrite and tests. A real branch and PR, in other
words, which is why this one ask flipped the earlier "no PR needed" answer.

Offered three routes; the maintainer chose **publish it as a newsletter issue**
(zero code). So:

- `NewsletterPage` "Free Sugar Camp" created and published — `issue_date`
  2026-08-06, `issue_label` "Camp Report" (the masthead reads
  "AUGUST 2026 · CAMP REPORT"), lede + `stat_band` + `highlights` + four
  prose paragraphs.
- The `CampReportPage` was **unpublished, not deleted** — reversible from the
  admin in one click if this is ever reconsidered.
- A permanent Wagtail redirect maps the old camp-report URL onto the new one,
  verified returning `301` in production, so nothing that was already shared
  breaks.

**Known cost of this route:** the Sugar Camp no longer appears in the
camp-reports archive or the `/reports/` camp teaser, and the Inauguration
Report is now the only camp report. If camps become regular, the better answer
is the model change (give `CampReportPage` the newsletter's blocks) rather
than filing every camp under Newsletters.

### Photos ✅ added 2026-08-10

Two camp photographs are live, with **consent confirmed by the maintainer** —
which is exactly what `ConsentedImageBlock.consent_confirmed` attests to
(brand-guidelines.md §5). The maintainer uploaded them to the Wagtail image
library directly (image ids 50 and 49); the blocks were then wired via the SSH
content-ops path.

The body's first two prose paragraphs became `feature_split` ("In focus")
blocks, each carrying one photo:

| Split | Image | Layout |
|---|---|---|
| "A free day of screening" (eyebrow "In focus") | id 50, welcome banner | photo left |
| "Who came" | id 49, waiting area | photo right (`reverse`), pull stats 93 / 61 |

Verified in a real browser: both splits render with the right photo on the
right side, the pull stats show, and the closing two paragraphs still follow.

**Note on the browser route.** The maintainer asked for the upload to be done
through Chrome. That stopped at the Wagtail login — entering a password is not
something the agent does — so the maintainer uploaded the images themselves and
the agent wired the blocks over SSH.

**Two things worth knowing about `feature_split`:**

- **It never renders `caption`.** `templates/blocks/newsletter_feature_split_block.html`
  outputs only the image and `alt_text`; the caption field comes along with
  `ConsentedImageBlock` but is ignored here. Captions were written and stored
  anyway, so they'd appear if the template ever grew support — but today they
  are invisible. Showing them is a template change, i.e. code and a PR.
- **Consent is enforced at render time, not just at save.** The template wraps
  the photo in `{% if value.photo.image and value.photo.consent_confirmed %}`,
  precisely so a photo written by a non-form path (an SSH snippet like this one,
  a migration, Plan 09's drafting flow) still cannot display unconsented. Worth
  keeping in mind: it means the gate held here by design, not by luck.

### The original camp-report publish (superseded)

Published 2026-08-10 via the agent-driven SSH path
([content-operations.md](../../docs/content-operations.md)) as page id 76.

Two things changed between the draft below and what shipped, both to match
the precedent rather than the draft:

- **Narrative markup.** The Inauguration Report's `narrative` is flowing
  `<p>` prose with no headings or lists, so the published version mirrors
  that voice instead of the headed/bulleted draft below. The figures are
  identical.
- **The PKR 20 registration fee is not mentioned at all** — option (b).
  Published first with the fee stated plainly, then **corrected the same day**:
  the maintainer confirmed the PKR 20 is a **bug in the clinic software's
  report**, not a charge anyone actually paid. The camp was free throughout,
  exactly as the pamphlet advertised. The paragraph now reads: "Every service
  at the camp was provided entirely free of cost, as advertised —
  consultations, diagnostic tests and medicines alike. No consultation,
  laboratory, ultrasound or pharmacy charge was recorded against any
  attendee." The BMI findings are included in full.

Still outstanding on the page: **no photos**. Any added later need
`consent_confirmed` ticked (brand-guidelines §5). No `report_document` is
attached either — the Inauguration Report has one, so a camp PDF could be
added the same way if one exists.



### The camp

From the pamphlet: a **Free Sugar Camp** — "a full day of diabetes
screening, diagnostics and treatment" — on **Wed 6 Aug 2026 from 10:00 AM**,
at The Thandkoi Clinics, Batarail, Thandkoi, Swabi, **in partnership with the
Diabetes General Hospital & Research Centre** (شوگر ہسپتال). Advertised
services: blood sugar screening, diagnostic tests, eye care, foot care,
nutrition advice, medicines & treatment — "ALL SERVICES 100% FREE".

The attendance data corroborates the pamphlet precisely: a median attendee
age of 54 and a median BMI of 30.0 is exactly the population a diabetes
screening camp draws.

### Verified figures (all de-identified, all recomputed from the export)

93 attendees recorded. (The sheet has 95 data rows; the parser's
phantom-continuation rule drops 2, and the pandas cross-check on a
non-blank `MR #` agrees on 93.)

| Measure | Value |
|---|---|
| Attendees | **93** |
| Women | 56 (60.2%) |
| Men | 31 (33.3%) |
| Sex not recorded | 6 (6.5%) |
| Median age | **54** (youngest 8, oldest 91) |
| Aged 50 or over | 61 (65.6%) |
| Aged under 18 | 1 (1.1%) |
| Vitals/BMI recorded for | 87 of 93 |
| Median BMI | **30.0** |
| BMI ≥ 25 (overweight or above) | 66 of 87 (75.9%) |
| BMI ≥ 30 (obese range) | 43 of 87 (49.4%) |
| Registration fee | PKR 20 per attendee, PKR 1,860 total — **spurious, a report bug; not published** (see Track C, finding 4) |
| Consultation / lab / ultrasound / pharmacy charges | **PKR 0** — none recorded against any attendee |
| Distinct localities in the address field | 22 (free text; indicative only) |

**What the export does not contain.** All seven clinical free-text columns —
Presenting Complaints, Investigation, Provisional Diagnosis, Prescribed
Medicine, Doctor's/Nurse's/Dietitian's Notes, Diet & Drug Compliance, Plan —
are **empty for all 93 attendees**, as are Next Visit Date and OPD Doctor. The
report therefore cannot say anything about what was diagnosed, prescribed or
followed up. Worth fixing at the next camp (Track C, finding 5).

### The PKR 20 registration fee — resolved 2026-08-10, option (b)

The pamphlet promised "ALL SERVICES 100% FREE", but the export charged every
attendee a PKR 20 registration fee (PKR 1,860 total). Raised as an open
question before publishing, with two options: (a) it's a token charge the
camp intended, say so plainly, or (b) it's an error and shouldn't be
mentioned.

**Answer: (b).** The maintainer confirmed the PKR 20 is a bug in the clinic
software's report — nobody paid it. The published page states the camp was
free throughout and says nothing about a fee. See Track C, finding 4, for why
this matters well beyond this page.

### Second editorial call: how much of the BMI finding to publish

The BMI numbers are the most valuable thing in this dataset — three quarters
of those screened were overweight or above, half in the obese range — and
they are the clearest possible justification for running the camp at all.
They are also a blunt thing to say about one's own community. They are fully
de-identified and aggregate, so there is no privacy objection; this is purely
a voice/tone call (brand-guidelines §6: "honest and specific"). The draft
includes them. Cut the "What the screening found" section if you'd rather not.

### Draft content — paste straight into the Wagtail admin

Create under **Camp reports** (`/en/camp-reports/`), same as the Inauguration
Report. Fields map 1:1 onto `CampReportPage`:

- **Title:** `Free Sugar Camp Report`
- **Camp date:** `2026-08-06`
- **Location:** `Batarail, Thandkoi, Swabi, KPK`
- **Report document:** none yet (optional field — attach a PDF later if one exists)
- **Photos:** none yet. Every photo needs `consent_confirmed` ticked before
  publish (brand-guidelines §5) — a camp crowd is exactly the case that gate
  was built for.
- **Narrative:**

> **Overview**
>
> On Wednesday 6 August 2026, The Thandkoi Clinics held a Free Sugar Camp — a
> full day of diabetes screening, diagnostics and treatment — in partnership
> with the Diabetes General Hospital & Research Centre. The camp opened at
> 10:00 AM and was open to everyone, with blood sugar screening, diagnostic
> tests, eye care, foot care, nutrition advice, medicines and treatment all
> provided at no charge. Ninety-three people came.
>
> **Who came**
>
> - Total attendees: 93
> - Women: 56 (60.2%)
> - Men: 31 (33.3%)
> - Median age: 54 — the youngest attendee was 8, the oldest 91
> - Aged 50 or over: 61 attendees (65.6%)
>
> This was overwhelmingly an adult and older-adult camp: only one attendee was
> under 18, and two thirds were 50 or older — the ages at which type 2
> diabetes and its complications do the most damage, and the group least
> likely to seek screening on their own.
>
> **What the screening found**
>
> Height, weight and vital signs were recorded for 87 of the 93 attendees.
> The median BMI was 30.0 — the threshold at which the obese range begins.
> Sixty-six of the 87 (75.9%) were in the overweight range or above, and 43
> (49.4%) were in the obese range. Raised body weight is the single largest
> modifiable risk factor for type 2 diabetes, and finding it at this rate in
> one morning is the clearest argument there is for running the camp again.
>
> **Cost to patients**
>
> Every service at the camp was provided entirely free of cost, as advertised
> — consultations, diagnostic tests and medicines alike. No consultation,
> laboratory, ultrasound or pharmacy charge was recorded against any attendee.
>
> **Reach**
>
> Attendees gave 22 different localities as their home address, so the camp
> drew well beyond Thandkoi itself.
>
> **With thanks**
>
> This camp was run in partnership with the Diabetes General Hospital &
> Research Centre, whose team joined ours for the day.

### Track A acceptance

- Page lives under the Camp reports index, `camp_date = 2026-08-06`, and
  appears above the Inauguration Report in the archive (it orders by
  `-camp_date`).
- Every published figure above matches the export. **No figure is estimated
  or rounded for effect.**
- Any photo added carries `consent_confirmed`.

---

## Track B — July 2026 newsletter (the Beacon)

### The July figures are real — most of them

Checked against production `pipeline_dailyaggregate` for 2026-07-01 →
2026-07-31 (**25 operating days**):

| Design claims | Production says | Verdict |
|---|---|---|
| 167 total patients | 167 | ✅ |
| 91 women (54.5%) | 91 | ✅ |
| 76 men (45.5%) | 76 | ✅ |
| 138 Zakat beneficiaries (82.6%) | 138 | ✅ |
| 29 regular patients (17.4%) | 29 | ✅ |
| 69 children (41.3%) / 98 adults (58.7%) | **68 / 99** | ❌ off by one |
| Age donut: 0–17: 34 · 18–35: 45 · 36–50: 35 · 51–65: 35 · 65+: 18 | **not computable, and wrong** | ❌ fabricated |
| "Largest age group 18–35 (45 patients)" | largest band is 19–55, with **73** | ❌ |
| "Average patients per day: 5–6" | **6.7** per operating day (167 ÷ 25) | ❌ ambiguous |

**The age donut is the serious one.** The pipeline stores exactly four age
bands — `0-5`, `6-18`, `19-55`, `56+` — and July's real distribution is
**0–5: 28 · 6–18: 40 · 19–55: 73 · 56+: 26**. The five buckets on the design
cannot be derived from that data, and they contradict it: the design puts 34
patients under 18 while the register has 68. Those five numbers, and the
"largest age group" callout built on them, have to be replaced with the four
real bands. Every other figure on the design is correct, which makes this the
kind of error that would sail through unnoticed.

The one-off in children/adults comes from the same place: with only age-band
data, "child" is the 0–18 approximation the daily report already uses
([Plan 14](14-freetext-summary-by-demographic-group.md)) — that gives
**68 children (40.7%) and 99 adults (59.3%)**.

"Average patients per day" needs to say *which* day it means: 6.7 per
operating day, or 5.4 across all 31 calendar days. Pick one and label it.

Related: the **"Patient trend — July 2026"** line chart draws an unbroken
line across 1–30 July, but the clinic operated on 25 of the month's days. An
unbroken line silently interpolates across the 6 closed days and reads as
"quiet day" rather than "closed" — the exact defect PR #124 fixed on the
site's own footfall chart. Reuse that treatment, or mark the closed days.

### Brand and identity problems

1. **The staff portraits and the building/consultation photos appear to be
   AI-generated.** brand-guidelines.md §5 asks for "real clinic, camp, and
   community photography" and says to use the logo's family illustration
   "rather than generic stock". Synthetic portraits are worse than stock
   here: they attach invented faces to three real, named members of staff.
   Replace with real photographs, or drop the portraits and keep the names,
   roles and qualifications.
2. **The masthead tagline is not the canonical Pashto line.** The design
   reads `هر چا ل پاره د امید او شفا چراغ`. The canonical line — in
   `templates/partials/footer.html:57`, `apps/core/factories.py:53`, and
   locked by a test in `apps/core/tests.py` — is
   `هر چا لپاره د شفا او امید څراغ`. Three differences: `لپاره` is split as
   `ل پاره`, the pairing is reversed (`امید او شفا` for `شفا او امید`), and
   `چراغ` is used for `څراغ`. Use the canonical string.
3. **The Beacon's series identity is the Urdu lockup `چراغِ شفا`**, a fixed
   template string in `apps/core/templates/core/newsletter_page.html`
   (Plan 11 D14 — deliberately *kept* for the newsletter when D4 retired it
   from the home page). The design replaces it with the Pashto tagline, so
   the printed issue and the web issue would carry different identities.
   Decide which is the Beacon's masthead and make both agree.
4. **"Telemedicine services — Now Live!"** — there is no telemedicine
   surface anywhere in this repo or on the live site. Confirm the service is
   genuinely running before announcing it in a newsletter.
5. **Staff titles differ from the seeded team list.** Design: "Dr. Ammar
   Ahmad — Medical Officer" and "Umar Jan — Accounts & Logistics Officer".
   Repo (`seed_core_content`): "Dr Ammar Fayyaz — In-charge Medical Officer"
   and "Umar Jan — Logistics & Accounts Assistant". Confirm which is current
   and fix the other.
6. The design prints the full bank account number and IBAN. Presumably
   deliberate for fundraising — just confirm it's meant to be public.

### If the July issue also goes on the site

The Beacon page type already carries everything this design needs, so this is
content, not code. `NewsletterPage` fields:

- `issue_date` `2026-07-01`; `issue_label` e.g. `July 2026`
- `summary` — the teaser used in the archive, masthead lede and home page
- `body`, from the existing blocks:
  - **Impact stat band** (max 1, exactly 3 stats) — the natural three are
    `167 patients served` · `138 Zakat-supported (82.6%)` · `25 clinic days`
  - **Highlights** (max 6) — the design's seven "July highlights" trimmed to
    six, minus any that don't survive the checks above (telemedicine)
  - **In-focus split** ×1–2, each with up to 2 pull stats — needs a real
    photo with `consent_confirmed`
  - **Paragraph** blocks for prose

Note the block limits (3 stats, 6 highlights, 2 pull stats) are enforced by
the model — the design's 5-stat and 7-highlight rows won't fit as-is.

### Track B acceptance

- Every number in the issue traces to `pipeline_dailyaggregate`, computed in
  Python — invariant #3. The age breakdown uses the four real bands.
- No AI-generated image of a real person ships.
- Masthead identity and tagline agree with the site.
- The issue is a **draft** until the maintainer approves it (invariant #4 —
  Plan 09's newsletter narrative is explicitly outside the auto-publish
  exception).

---

## Track C — the 93 camp attendees are missing from the pipeline (needs a decision)

This is the finding with the longest tail, and it is code, not content.

1. **The camp is not in the data.** Production has **16** visits for
   2026-08-06 — the normal OPD day. The camp's 93 attendees were never
   ingested. So the published daily report for 6 Aug understates that day by
   93 people, and August's monthly rollup, the `/reports/` footfall chart,
   the dashboard and the home impact band all miss the single biggest day the
   clinic has had.

2. **Uploading the camp export as-is would make it worse.**
   `ingest._ingest_one_date` supersedes a date **wholesale**:
   `DeidentifiedVisit.objects.filter(visit_date=clinic_date).delete()`
   followed by a `bulk_create` of the new rows. Uploading the camp file for
   6 Aug would therefore *delete* the 16 OPD visits and leave 93 — not 109.
   That replace-don't-append rule is deliberate and correct for a corrected
   re-upload; it just has no concept of two legitimate exports for one date.
   **Do not upload this file through the admin until this is resolved.**

3. **`Status = "Camp"` is a value the parser has never seen.**
   `parser_tkc_daily_v1` maps `zakat`/`regular` → `is_zakat_beneficiary`
   True/False and anything else → `None`. All 93 rows carry `Status = Camp`,
   so all 93 would land as `unknown_payment_type_patients` — a bucket that is
   currently **0 for every row in production**. The funding-mix chart and the
   dashboard's funding split would need to render a third category they have
   never had to show.

4. **The fee columns are not trustworthy — corrected 2026-08-10.** The camp
   export carries a non-zero `Registration Fee (PKR)` (a flat PKR 20 × 93 =
   PKR 1,860), and this plan originally read that as "the first real fee
   data" for Plan 16 Phase 2. **That was wrong.** The maintainer confirmed
   the PKR 20 is a **bug in the clinic software's report** — nobody paid it;
   the camp was free throughout. The correction has already been applied to
   the published camp report.

   The consequence is bigger than this one page: **[Plan 16](16-clinic-dashboard.md)
   Phase 2 (revenue) is parked waiting on exactly these fee columns, and the
   first sample of non-zero data in them turned out to be spurious.** Phase 2
   cannot treat a non-zero fee column as ground truth without first
   establishing, with the clinic team, which fee columns the software
   populates reliably and which it fabricates. Building a revenue surface on
   this column as it stands would publish invented income figures.

5. **No clinical data was captured at the camp.** All seven free-text
   columns are empty for all 93 attendees, so the camp contributes nothing to
   the free-text summary or the diagnosis-category breakdown, and every row
   would fall into `diagnosis_category = other`. If camps are going to be a
   recurring thing, capturing at least a provisional diagnosis is worth
   raising with the clinic team — it costs nothing at the point of care and
   it is the difference between "93 people came" and "here is what we found".

**The decision to make:** should camp attendance live in the same pipeline as
routine OPD visits at all? Both answers are defensible —

- **Keep them separate** (cheapest): camps stay narrative-only, as
  `CampReportPage` content with hand-entered figures, exactly like the
  inauguration report's 384. Nothing changes in the pipeline; the daily
  numbers keep meaning "routine clinic activity". The cost is that the site's
  headline totals permanently understate what the clinic actually does.
- **Bring them in** (a real plan): the export format needs a camp/visit-type
  dimension, ingest needs to hold more than one export per date, `Status =
  Camp` needs a mapping, and every consumer of the funding split needs to
  handle a third bucket. That is a proper plan-and-PR piece of work, not a
  quick fix.

**RESOLVED 2026-08-10 — keep them separate.** The maintainer's decision: the
camp's 93 attendees do **not** go into the daily report or the pipeline.

What follows from that:

- **Do not upload `Camp Attendance Report.xls`** through the admin. Findings 2
  and 3 above (the wholesale-supersede trap, the `Status = "Camp"` mapping, a
  third funding bucket) are all moot unless this is revisited — no code needed.
- **6 Aug 2026 correctly reads 16 visits** on the daily report. The pipeline's
  figures now mean "routine clinic activity", and camps are told as narrative
  content instead.
- **The site's headline totals deliberately exclude camps.** A legitimate
  definition, but now one worth being able to state: a reader comparing "93
  people at the camp" in the newsletter against the reports page's daily
  figures gets no hint the two count different things. Worth a line of copy on
  `/reports/` if camps recur.
- **Revisit only if camps become regular.** One camp a quarter doesn't justify
  the pipeline work; a monthly camp probably does.

Finding 5 (no clinical data captured at the camp) survives this decision
independently — it's about what the clinic records at the point of care, not
what the pipeline ingests, and is still worth raising before the next camp.

---

## Housekeeping found along the way

- **Three untracked prototype files are sitting in the main checkout**:
  `apps/pipeline/aggregation.py`, `apps/pipeline/intake.py`,
  `apps/pipeline/rendering.py` and
  `apps/pipeline/templates/pipeline/daily_report.html`. These are resurrected
  copies of the **Plan 02 prototype pipeline that commit `1c12ae2` deleted**
  ("chore(pipeline): remove the superseded Plan 02 prototype pipeline",
  PR #137). Nothing in the current pipeline imports them, and
  `aggregation.py` describes a `ClinicAggregate`/`by_diagnosis` shape that no
  longer exists. They should be deleted before someone reads them as live
  code. (`static/images/og-newsletter.png` and
  `templates/blocks/impact_stats_block.html` are also untracked — the latter
  is the block deleted in PR #107, per the same pattern.)
- **The plans index has two rows numbered 18** — "Free-text summary privacy
  remediation" and "Mobile menu + dashboard responsive revision". Stage 1's
  renumbering note applies; one should become 18a/20 or similar so the
  history stays legible.
