# Plan 26 — Free-text privacy architecture: stop sending raw clinical narrative

**One line.** Give donors a better answer to "what is this clinic treating?" by
moving it from a per-day AI summary over raw clinical narrative to **monthly**
theme counts under a per-cell suppression floor — where the themes are assigned
by a **language model running on our own infrastructure**, so the notes are read
intelligently but never leave, never persist, and can never be published as an
individual. Plus: fix the 10 live pages that already do.

**Status: 📝 Drafted.** This is a plan, not an implementation. Nothing in the
pipeline is changed by this branch.

**Answers:** `docs/ai-freetext-scrubbing-brief.md` (untracked — the maintainer's
brief). **Grounded by:** `docs/ai-freetext-risk-assessment.md` (untracked) and
`docs/ai-freetext-findings-2026-08-17.md` (untracked — the measurement detail
behind every number below, kept out of git deliberately; see D0).

---

## D0 — Why the evidence lives outside this file

The measurement identified 10 published pages that disclose an individual
patient's condition, with dates and verbatim text. Those pages carry `noindex`
(Plan 18a) but are publicly reachable. This repository is public, so writing
their dates here would make them findable from GitHub — amplifying exactly the
disclosure this plan exists to end. The detail therefore stays untracked in
`docs/ai-freetext-findings-2026-08-17.md`, alongside its two sibling documents,
and this file states the findings in aggregate. Any implementation task that
needs the affected dates reads them from there, not from git.

---

## 1. The reframing — the risk is not where we thought it was

The brief, and the risk assessment before it, framed the problem as *"patient
identifiers may be sitting in the seven free-text columns and we send them
verbatim to Anthropic."* That framing drove both proposed architectures: scrub
the identifiers before sending (Option A), or send nothing anywhere (Option B).

**Measured against 1,847 real non-blank entries from 661 production visits,
that framing is largely wrong in one direction and badly incomplete in the
other.**

**The columns are close to identifier-free, and now that is measured rather
than asserted.** Zero digit runs of seven or more. Zero CNIC-shaped strings.
Zero phone numbers, emails or URLs. Zero honorifics. Zero `s/o` / `d/o` / `w/o`.
Zero local place names. Zero Arabic-script text. **Zero hits against a
~100-name gazetteer of common Pakistani and Pashtun given names.** Three
entries contain an English relation word; two contain "Khan". The 17.9%
"Doctor" hit rate turned out to be our own parser's `"Doctor: "` role prefix
(`parser_tkc_daily_v1.py:348`), not a clinician being named.

The maintainer's 2026-07-23 assertion, which the risk assessment correctly
flagged as unverifiable from the repo, is now **substantially corroborated by
the data itself**. It is still not a control — a sample bounds the past, it does
not constrain the future, and the brief was right to say so — but it is no
longer a bare claim.

**And meanwhile, the actual harm has been happening in the other direction, in
public, for two months.** 10 of 64 published daily reports (16%) contain a
model-written sentence beginning "One patient…" or "Two patients…", attributing
a specific clinical fact to a specific individual, on a page that names the
village and the date. The groups those sentences describe had **3, 4 or 5
patients in them**. Two of the disclosures concern conditions that carry real
social stigma in this community.

The N=3 floor was working perfectly throughout: 0 published summaries were
below the floor, and the smallest published group was exactly 3. **That is the
failure, not a mitigation of it.** The floor guarantees the group contains at
least three people and then hands the model their narratives, and the model
picks one out. The risk assessment predicted this precisely — "a floor on group
size, not on distinctiveness" — and the production data confirms it.

**The consequence for the design is decisive:**

| | Stops the transfer to Anthropic? | Stops single-patient disclosure on the public page? |
|---|---|---|
| **A — tag, send, restore** | Partly (only what the detector catches) | **No.** There is no identifier to catch in these sentences. |
| **B — self-hosted model** | Yes | **No.** A local model writes "one patient with «diagnosis»" just as happily. |
| **C — counts only** | **Yes, completely** | **Yes**, structurally — a count of 1 cannot be published. |

Option A and Option B both answer the question the brief asked. **Neither
answers the question the data asked.** Only a design that never gives a model a
per-patient string can, because the disclosure comes from the narrative itself,
not from any identifier attached to it.

## 2. Option A — tag, send, restore: **rejected**

**What would do the detection, and at what recall.** The candidates are
rules-plus-gazetteer (Philter), general-purpose PII NER (Microsoft Presidio),
clinical NER (scispaCy/medspaCy), or a small model prompted to tag.

- **Philter** reports **99.92% recall** on the i2b2 2014 corpus and 99.46% on
  UCSF notes — the best published figure available, and it is purpose-built for
  clinical text.
- **Presidio**, evaluated on real radiation-oncology records rather than a
  benchmark, achieved **80.6% strict / 90.4% relaxed recall**; 9% of PII was
  missed outright. Person names were 44.1% of the PHI.
- **The recall figure for our population does not exist.** Every headline number
  above is Western names in US records. The FAccT '23 study *In the Name of
  Fairness* built 16 name sets varying by gender, race, popularity and decade,
  ran them through nine de-identification methods, and found statistically
  significant gaps along most demographic dimensions — specifically that the
  methods recognise **less popular White-associated names better than more
  popular Asian-associated names**. Pashto and Urdu names transliterated into
  English sit further out of distribution than the US-Asian names that study
  tested.

**Per the brief's instruction to say so plainly: this is an evidence gap, and it
is itself a finding.** There is no published recall figure for clinical
de-identification on transliterated Pashto/Urdu names, the only benchmark
touching Urdu clinical NER at all (BioUNER) had to be constructed because no
dataset existed, and the one study that measured demographic bias directly
points downward for our population. Any number we quoted would be borrowed from
a population that is not ours.

**Does restoration make sense? No — and this removes a whole class of bug, as
the brief anticipated.** Checked against all 64 published pages: the summaries
are aggregate thematic prose and never legitimately name an individual (zero
name-gazetteer hits, zero honorifics). There is nothing to substitute back. Any
tag/restore round trip would be pure machinery with no payload.

**Why it is rejected.** It would deploy a detector with unknown recall on our
names, against a corpus that measurement says contains essentially nothing for
it to detect — buying a false sense of safety — while leaving every one of the
10 real disclosures untouched, because "One patient was diagnosed with
«diagnosis»" has no identifier in it to scrub. It fails the brief's own test:
*design for the miss.* Here, even a perfect hit changes nothing.

## 3. Option B — self-hosted model: **not the primary control, but worth doing second**

The maintainer has asked for this to be weighed properly, both on merits and
because the operational knowledge transfers to other projects. Taking that
seriously:

**It does not solve the demonstrated problem.** A locally-hosted model handed
the same seven columns produces the same "one patient…" sentence. Self-hosting
changes *who sees the data*, not *what gets published*. That has to be said
first, because it is the thing the last two months of production data actually
proves.

**But it genuinely does retire the transfer question**, and it is far cheaper
here than anyone would guess — because the workload is tiny.

**Sizing, from the real corpus.** ~10 visits/day, ~1,400 characters of free text
per clinic day across all seven columns. That is roughly 400 input tokens and
~150 output tokens, **once per day**. This is not a GPU workload. Renting an
H100 (~$2–6/hr) or any always-on GPU for one inference a day would be absurd —
which is the honest answer on NodeShift and the GPU-marketplace tier generally:
it is the right tool for training and for sustained inference, and the wrong
tool for one 90-word generation per day.

**The proportionate shape is CPU inference on infrastructure we already use.**

- A distilled 1.7B model quantised to Q4_K_M is ~1.4 GB on disk; a 4B is
  ~2.6 GB. Small-model CPU inference at this size runs comfortably faster than
  the once-a-day cadence requires.
- The live Render service is **`starter` (512 MB RAM, 0.5 CPU) in the
  `singapore` region** (read from the live service, not `render.yaml` — see the
  standing warning in that file). **A model does not fit in the web service as
  it stands.**
- The right home is a **Render cron job**, billed per second of execution at
  instance rates with a ~$1/month floor. A Pro-sized cron (4 GB) running ~2
  minutes a day costs roughly **$1/month** — the floor, not the instance price.
- This also fixes an unrelated latency problem: summarisation currently runs
  synchronously inside the upload request via a `ThreadPoolExecutor`
  (`report_publishing.publish_daily_report`). Moving it to a deferred job is
  compatible with the existing auto-publish contract, which already ships the
  page when the call fails.

**Distil Labs is a good fit for the training half**, and is the part that
carries the transferable knowledge:

- Free tier: **2 full training runs, task description plus as few as 10
  examples, and downloadable weights for self-hosting**. Paid training credits
  are $1,000 for 10 runs; their hosted inference is ~$0.04/M tokens on a
  dedicated H100 endpoint — irrelevant at our volume, and hosted inference would
  reintroduce the third-party transfer we are removing.
- `distil slm download --destination ./model <slm-id>` yields a tarball with the
  model, a LoRA adapter if used, a client and a README; serve with `llama.cpp`
  for CPU, or vLLM for concurrency we do not have. Their own framing — "a plain
  weights download if the model can never leave your network" — is exactly this
  use case.
- Students span ~100M–9B including the Qwen3 family, so a 0.6B–1.7B student is
  in range.

**D1 — if we train with Distil Labs, the training examples must be synthetic.**
Uploading real clinical notes to Distil Labs to train the model would move the
third-party transfer rather than remove it, and defeat the entire exercise.
Their workflow needs a task description and ~10 examples; this repo already
authors synthetic clinical fixtures for its tests, and the task (thematic
summarisation of short clinical strings) is generic enough that synthetic
training data should suffice. This must be an explicit decision at
implementation time, not an assumption.

**A distinction worth being precise about, because it cuts in Option B's
favour.** Renting a VM from an infrastructure provider is *not* the same
category of exposure as calling a model vendor's API. The clinic's de-identified
data already sits at rest on **Neon in `aws-ap-southeast-1`** and passes through
**Render in `singapore`**. A GPU or CPU VM from a similar infrastructure
provider is not a new class of processor — the data stays in our process memory
on rented hardware, exactly as it already does. That is a materially different
posture from submitting it to a model vendor for processing, and it is why
"self-hosted on rented infrastructure" is a real answer and not a fig leaf.

**Who maintains it.** One part-time maintainer. A model file baked into a build,
a quantisation choice, and a llama.cpp version to keep current is real ongoing
surface — small, but not zero, and it sits on the critical path of a daily
publish. That is the honest argument for doing Option C first and this second.

## 4. Option C — computed categorical aggregation: **the recommendation**

Send the model **nothing but counts**. Map free text to a fixed theme
vocabulary in Python, suppress every cell below a floor, and hand the model a
dict of `{theme: count}` to phrase. Raw text never leaves the database.

This is Plan 11 B11's parked option (b). **Its parking condition has been met.**
The condition on record was *"the tightened prompt still produces
identifying-feeling output in practice"* — it does, on 16% of published pages,
with group sizes of 3 to 5. The prompt-only fix chosen on 2026-07-23 has had two
months in production and has failed.

**Coverage, measured.** The obvious shortcut — reuse the existing
`diagnosis_category` mapping — **does not work**: it resolves to `other` for
**93.8%** of all 661 visits, because its source column is filled only 21.6% of
the time and the keyword list is thin. This is a correction to the brief's
framing, which suggested the codebase already computes what is needed. It does
not.

A first-pass symptom vocabulary written against **`presenting_complaints`**
(79.4% filled) instead covers **78.3%** of that column's entries. That is the
number to build on, and improving it is ordinary, reviewable, testable Python.

**Tested against the days that actually leaked.** With a per-theme cell floor of
3 applied in Python before the payload is built:

- The two days that produced the sharpest single-patient disclosures both
  reduce to an **empty payload — no model call is made at all**, and the page
  ships with its numbers.
- A day with 10 women seen survives with `body aches 3, fever 3, headache 3,
  supplements 3` — materially the same information the published prose carried,
  with real figures attached instead of "several".

**Is a counts-built version distinguishable to a reader?** On this evidence it
is *better*: "of 10 women seen, 3 with fever, 3 with body aches" is more useful
to a donor than "several patients presented with…", and it is the numeric style
the maintainer asked for in B11 in the first place ("gastrointestinal distress
(45%), musculoskeletal pain (30%)"). **Caveat, honestly stated: the generation
half of this test did not run** — the local API key returns 401, so there is no
generated prose to compare side by side, and I have not fabricated one. The
suppression result is real; the prose comparison is outstanding and is the
first task below.

**Two things counts-only does not solve, stated plainly:**

1. **It loses nuance the free text carries.** Themes not in the vocabulary
   (21.7% of complaint entries today) become invisible rather than
   mischaracterised. That is the right failure direction, but it is a real loss.
2. **Counts are not automatically safe.** "1 patient with hypertension" out of
   10 is still a small-cell disclosure. The floor is what makes the design safe,
   not the counting. The win is that the floor is now **enforceable in Python on
   a number**, instead of requested of a model in prose.

## 4a. The purpose these summaries serve — and why the *unit* is wrong

**Maintainer, 2026-08-17: the summaries exist so the clinic's donors know what
is being treated.** That is the requirement, and it reframes the design more
usefully than anything above, because it separates the thing donors want from
the thing that creates the risk.

**The date is the identifier.** "One of four women, at this named village
clinic, on 4 July" is identifying. "Among the 287 patients seen in June" is not.
Nothing about a donor's question requires knowing which Tuesday — they want to
know what this clinic treats and what their money paid for. So the
informativeness and the risk separate cleanly along the **time axis**, not the
content axis. Aggregating over a month is the single most effective
de-identification move available here, and it costs the donor nothing.

**Measured across the full 64-day history**, counting `(unit, theme)` cells:

| Aggregation unit | Non-zero cells | Cells ≥3 | **Cells ≥5** | Largest cell |
|---|---:|---:|---:|---:|
| **Per day** | 333 | 58 | **8** | 8 |
| **Per month** | 48 | 43 | **36** | **41** |

At a cell floor of 5, the daily unit yields **8 publishable facts in three
months**. The monthly unit yields **36** — roughly nine themes every month,
every month, with cells up to 41.

**This also explains §3's 58 blank-but-eligible slots.** At ~10 visits a day the
daily page never had enough data to support a summary. The feature could only
ever be empty or unsafe; there was no third option, and both failure modes
duly appeared in production. The defect was never really the prompt — it was
asking a per-day unit to carry a per-month question.

**A monthly view is strictly more informative to a donor, not less.** June's
287 visits give fever 41, body aches 31, respiratory 26, musculoskeletal 21,
headache 15, gastrointestinal 12, ear/eye 11 — nine to twelve themes with real
denominators, expressible as shares ("14% of June's visits were fever"). It
also supports the thing a daily page structurally cannot: **trend**.
Hypertension ran 4 → 19 → 7 across June/July/August, which is a real,
donor-relevant story that no single day could ever show.

**D4 — the surface, and the invariant-#4 bonus.** The natural homes already
exist: Plan 13's rolling 30-day chart on `/reports/`, Plan 16's dashboard range
aggregation, and Plan 09's monthly newsletter. Putting the prose in the
**monthly newsletter** has a structural advantage worth taking: the newsletter
is human-reviewed before publishing under CLAUDE.md invariant #4's normal rule.
So moving it there means **the auto-publish exception for `freetext_summary`
can simply be retired** rather than re-engineered — one fewer widened exception
to defend, and a human reads every word before a donor does.

**What the daily page keeps.** Its deterministic numbers — visit counts,
gender/age splits, funding mix, the empty-column chips, the daily summary
sentence over aggregates. Those are unaffected. Only the per-day free-text prose
retires.

## 5. Recommendation

**Options B and C merge. Do not do Option A at all.**

The final shape is **C's data architecture powered by B's model**: a
locally-hosted language model reads the raw notes and assigns themes (B — so
there is no keyword vocabulary to maintain, and it generalises to whatever
clinic staff actually type), the themes are aggregated to **monthly** counts
under a cell-suppression floor (C — so the published output can never describe
an individual), and the narrative is discarded once classified (D5).

The two options were never really rivals. B answers "how do we read the text
without sending it away"; C answers "what unit can we safely publish". Each
leaves the other's problem open — B alone still publishes single-patient
sentences, C alone needs a regex someone has to curate. Together they close
both.

Sequenced, cheapest and most urgent first:

**Phase 0 — stop the bleeding (hours, no architecture change).**
1. **Correct the 10 live pages**, in the shape of Plan 18a's
   `scrub_subfloor_freetext_summaries` — a management command plus a re-run
   confirming zero remaining — but **rewriting rather than blanking**. Reading
   the full published text (not the extracts) shows the disclosure is the
   *trailing sentence* in 10 of the 11 affected group-summaries, with the
   aggregate prose before it sound; only one needs restructuring, because there
   the offending clause is the opener. So the command carries a hardcoded
   `{(date, group): new_text}` map of human-approved edits — not regenerated
   summaries, since re-running the model over the same free text can reproduce
   the same defect. The exact before/after for all 11 is in the untracked
   findings doc §7, along with the two to do first.
2. **Add a publish-time regex guard** in Python that blanks any summary
   attributing to an individual. It must catch **`another`** as well as
   `one patient` / `two patients` — measured across all 64 pages, `another`
   occurs twice and both times introduces a *second* singled-out individual,
   which a naive "one patient" guard would miss. Pronouns and "a woman/man/
   child" score zero today but belong in the set. This is a control, not prompt
   wording, and it can be negative-tested. Worth shipping even though Phase 1
   makes it largely redundant — defence in depth on an auto-published surface.
3. **Enable HIPAA readiness** in the Anthropic Console (see D2).
4. **Fix `README.md` line 17**, which still claims on `main` that patient data is
   "never stored and never sent to any AI model". It is neither, and the repo is
   public.
5. **Reword Plan 25's privacy notice** before PR #169 merges — "No name, no
   identifier" now has measurement behind it, but should say what is true: the
   fields are believed identifier-free because of how the clinic software
   constrains entry *and* because we measured 1,847 entries and found none, that
   this is not a guarantee about future entries, and that the text is sent to
   Anthropic in the United States.

**Phase 1 — move the donor answer to a monthly unit (days).**
6. **A locally-hosted language model classifies each visit** against a small,
   stable taxonomy (~15 clinical concepts plus `uncategorised`), running
   in-process at ingest. See D7 — this replaces the regex vocabulary as the
   primary mechanism, at the maintainer's direction (2026-08-17), and it is the
   right call: a hand-maintained keyword list is exactly the kind of artefact
   that rots in a one-part-time-maintainer project, and the measured 78.3%
   coverage is the evidence for that, not against it.
7. Compute theme counts **per calendar month** (and/or rolling 30 days, reusing
   Plan 16's range aggregation), as counts *and* shares of visits. Apply
   `MIN_CELL = 5` suppression in Python — affordable at monthly denominators,
   where 36 of 48 cells clear it.
8. Publish it as a "What we treated" section on `/reports/` and in the monthly
   newsletter, which is human-reviewed (D4). Any prose is drafted from the
   suppressed counts alone — never from free text.
9. **Retire the daily `freetext_summary` entirely**: drop the three fields from
   the page, delete `build_freetext_summary_payload` and the free-text columns
   from every payload path, and retire invariant #4's auto-publish exception for
   it. `MIN_GROUP_VISITS_TO_SUMMARISE` goes with it — with no per-day summary
   there is no group to floor.
10. The daily page keeps every deterministic number it has today.

**D5 — once the daily summary retires, stop *storing* the narrative too.**
Verified by grep: the only things that touch the seven free-text columns are
the model definition, `parser_tkc_daily_v1`, `ingest.py`'s writer, and
`freetext.py`'s payload builder. **No template renders them. No dashboard,
report, newsletter or admin view reads them.** So the moment Phase 1 retires
the free-text summary, those columns have *zero* consumers — written once at
ingest and never read by anything, forever.

The right move is therefore to **classify at ingest and discard the narrative
in-request**: run the theme vocabulary over each row while the upload is being
parsed, store the resulting theme flags on `DeidentifiedVisit`, and never write
the raw text at all. Then drop the seven columns in a migration and purge what
is already stored.

This is worth doing for its own sake, because it changes the security posture
qualitatively rather than incrementally:

- **It restores CLAUDE.md invariant #1** ("never persist raw PHI"), which the
  Plan 11 B8 decision effectively suspended for these seven columns. The
  invariant goes back to meaning what it says.
- **It removes the at-rest exposure entirely.** Today ~90,000 characters of raw
  clinical narrative sit in Neon. After this, none do. There is no breach
  surface because there is nothing to breach.
- **It retires the load-bearing assumption.** The 2026-07-23 claim — that the
  clinic's UI structurally cannot accept an identifier into these fields — stops
  mattering at all. It does not matter whether a nurse *could* type a name into
  a notes field, because the string is classified and discarded inside the
  request that parsed it. The unverifiable assertion the risk assessment was
  built around simply stops being part of the design.
- **It makes the aggregation cheaper**, since themes are computed once at ingest
  rather than re-derived on every read.

The cost is that re-classifying historical visits under an improved vocabulary
becomes impossible — the source text is gone. That is a real trade and should be
made deliberately: extend the vocabulary while the text is still there, measure
coverage, and only then discard. Sequencing note: **Phase 1 before D5**, so the
vocabulary is proven against real data before the data is destroyed.

**D7 — a local language model does the classification, not a regex**
(maintainer direction, 2026-08-17, and it supersedes the earlier D6 framing
that had this as an optional Phase 2).

*The objection, which is correct:* the point of using a model is that it
generalises. It recognises "burning micturition", "temp 101", a misspelling, a
transliterated Urdu word, and a presentation nobody anticipated — none of which
a keyword list handles without someone forever adding strings to it. Asking a
part-time maintainer to curate a spelling list is how the feature quietly
degrades.

*The resolution:* the model reads the raw notes, and it reads them **on our own
infrastructure**. Nothing about the privacy architecture changes — the text is
classified inside the request that parsed it and then discarded (D5); no free
text ever crosses a network boundary. What changes is that the classifier is a
model rather than a regex, so there is no vocabulary to maintain.

*What you maintain instead:* a taxonomy of ~15 clinical **concepts**, not
strings. "Is there a category for maternal health?" is a question that comes up
once or twice a year; "did they type micturition or micturation?" is one that
never stops. That difference is the whole argument.

*What this does to invariant #3* ("numbers are deterministic — all published
figures are computed in Python"). This is a genuine widening and must be decided
deliberately, not assumed:

- The **classification** becomes model-derived. The **counts** do not: each
  visit's labels are stored once at ingest, and every published figure is then
  a `count(*)` in SQL over stored flags — reproducible, auditable, and
  recomputable without re-running any model.
- The model never sees a number and never produces one. Invariant #3's actual
  hazard — a model inventing or restating a statistic — is untouched.
- **Self-hosting makes this *more* deterministic than the status quo, not
  less.** Pinned local weights classify the same input identically for as long
  as we keep them. The daily-summary and newsletter calls this project already
  depends on run against a hosted model that can change underneath us with no
  notice. This is the stronger position.
- Store the classifier's model identifier and version alongside the flags, so a
  future change in labelling is attributable rather than mysterious.

*The regex does not disappear — it becomes the test oracle.* Keep the keyword
vocabulary in the test suite only, asserting the model agrees on the obvious
cases (fever, cough, back pain). That is a real CI smoke test on classifier
quality with no production dependency, and it turns the 78.3% measurement into
a regression baseline rather than a maintenance burden.

*Operational consequence, and the one real cost.* Classification now sits on the
ingest path, so the model must be reachable when an upload happens, and the
Render `starter` instance (512 MB) cannot host it. Two shapes, and the choice is
a genuine privacy/cost trade for the maintainer:

| | How it works | Raw text at rest | Cost |
|---|---|---|---|
| **A. Classify in-request** | A small private Render service runs the model; the web app calls it during ingest, then discards the text | **Never persisted** | ~$25/mo (2 GB Standard, 1–1.7B Q4) |
| **B. Classify nightly** | Text is stored, a cron job classifies and then purges it | Persisted **< 24 h**, never long-term | ~$1/mo (cron only) |

A is the cleaner privacy story; B gets most of the benefit for a twentieth of
the cost and still ends the indefinite retention that is the actual problem
today. **Recommendation: B to start**, because it is reversible, cheap, and the
sub-24-hour window is a vastly smaller exposure than the current forever; move
to A if the clinic's data ever warrants it.

*If classification fails*, the upload must fail loudly rather than silently
storing unclassified visits — ingest is a human-triggered admin action, so a
visible error is the correct behaviour. Under shape B, unclassified text is
retried on the next run and only purged once classification has succeeded.

**Phase 2 — the distillation itself (the transferable-knowledge piece).**
10. Distil the classifier with Distil Labs on synthetic examples (D1), download
    the weights (`distil slm download`), quantise, and serve with `llama.cpp`.
    A ~1.7B Q4 student is ~1.4 GB. Start with an off-the-shelf small instruct
    model to prove the shape end to end, then distil to shrink and sharpen it —
    the fallback if distillation underperforms is simply the larger
    off-the-shelf model, which keeps the privacy properties either way.

**D2 — HIPAA readiness, not ZDR.** The risk assessment recommended requesting
zero data retention through Anthropic sales, and dismissed HIPAA readiness as a
US-law framework irrelevant to a Pakistani clinic. Anthropic's current
documentation reverses that: HIPAA readiness is **self-serve in the Console**
with a standard BAA, applies "a broader set of privacy and security safeguards
than ZDR (encryption, access controls, and audit logging…)", and the docs state
plainly *"If your organization handles PHI, HIPAA readiness is the arrangement
to use; you do not also need ZDR."* It is the better action and needs no sales
call. **Two catches, both load-bearing:** enablement is **permanent and cannot
be disabled**, and **Claude Code is not covered**. So it must be enabled on a
**separate Anthropic organization** holding only this pipeline's API key — not
the org the maintainer uses for Claude Code. Enabling it also gives a contract
that explicitly contemplates health data, which is the cleanest available answer
to the DPA Schedule 1 Part B.3 "special categories: None" mismatch the risk
assessment identified.

**D3 — data residency correction.** The risk assessment's transfer path
"Pakistan → UK (Render; check the region) → US" is **wrong**. Read from the live
service and the live Neon project: Render is `singapore`, Neon is
`aws-ap-southeast-1`. There is no UK leg. The path is Pakistan → Singapore →
US. This matters to the §4a jurisdiction question, and it should be corrected in
the risk assessment before anyone reasons from it.

## 6. The failure mode — designing for the miss

**Option A's miss:** the detector does not recognise a Pashto name, the
identifier ships to Anthropic, and nothing anywhere detects it. Unbounded, and
undetectable.

**Option C's miss:** a complaint uses a word not in the vocabulary, so it lands
in no theme. The consequence is that **the summary does not mention it**. The
payload still contains only integers. There is no input under which a
free-text string can reach the model, because the code path that would carry one
no longer exists.

That asymmetry is the whole argument. Under A, a miss is a leak. Under C, a
miss is a slightly less complete sentence. The blast radius of the worst case
drops from "a patient's name and condition reach a US processor and we never
know" to "fever was under-counted this week."

**The residual risk C does not remove**, stated explicitly:
- Counts still describe a real, small population. The cell floor is the control,
  and it must be tested, not assumed.
- The monthly newsletter still carries operator-typed admin notes and photo
  captions to `claude-sonnet-5` (`build_monthly_newsletter_user_message`) —
  outside every control here, and outside this plan. Flagged, not fixed.
- The 245 unclassified capitalised-token entries (findings doc §2) are the one
  place a name could still be hiding in the stored data. Under C they never
  reach a model regardless, but they are still stored, and the maintainer should
  eyeball them once.

## 7. The test that can fail

The current guardrail tests cannot falsify the safety claim: they assert that
values from the *identifier columns* never reach the payload, using a fixture
whose free text this codebase authored. Under Option C the assertions become
trivial to write and genuinely falsifiable:

1. **No free text, at all.** Build a fixture where all seven free-text columns
   contain unique sentinel strings. Assert that **no sentinel appears anywhere
   in the serialised payload**. This goes red the instant anyone reintroduces a
   free-text field, and it cannot pass by construction — the sentinels are
   adversarial, not representative.
2. **Every published integer clears the floor.** A property-style test over
   generated visit sets asserting that no cell below `MIN_CELL` ever appears in
   the payload, for any input.
3. **The payload is integers only.** Assert every leaf value in the serialised
   body is an `int` or a known theme key from the fixed vocabulary. Any string
   of unbounded provenance fails the type assertion.
4. **The publish-time phrasing guard goes red when broken.** Per the standing
   note on retargeted guards, deliberately break the guard and confirm the test
   fails — a guard that cannot be shown to fail is not a guard.
5. **A canary on the column list.** Assert the seven-column tuple is unchanged,
   so a future export-schema change (27 → 34 columns happened in August 2026)
   forces the grounding question to be asked again rather than silently
   invalidating a decision.

Test 1 is the one the current design cannot have and the new one gets for free,
and it is the direct answer to the brief's fourth requirement.

## 8. Cost and maintenance

| | One-off | Monthly | Maintenance burden |
|---|---|---|---|
| **A — detector** | Days of integration + an evaluation we cannot source data for | $0–20 | A detector, a gazetteer, a model version, and an unquantifiable recall claim |
| **B — self-hosted** | Days: distillation, quantisation, cron job, model in build | **~$1** (Render cron, per-second billing, $1 floor) | Model file, llama.cpp version, one more failure mode on the daily publish |
| **C — counts only** | Days: vocabulary + payload + tests | **$0** (input tokens shrink) | One keyword vocabulary, reviewed like any other Python |

Option C is cheaper to run than today, because the payload shrinks from ~1,400
characters of narrative to a few dozen integers. Option B's real cost is
attention, not money.

## 9. Migration path, including what has already been sent

- **Already transmitted.** Real clinical free text has gone to Anthropic daily
  since 2026-07-23, over visits ingested from 2026-05-18. Under the default
  30-day retention, anything sent before roughly 17 July 2026 is already
  deleted; roughly the last 30 days may still be within the window. Enabling
  HIPAA readiness or ZDR now is **not retroactive** — if deletion of prior
  inputs matters, it must be asked of Anthropic directly, and asked early (see
  the risk assessment's §6.7 note that duties of this kind tend to be
  time-bound).
- **Already published.** The 10 pages are the urgent item and are Phase 0.1.
  Plan 18a is the precedent and it worked; reuse its shape.
- **No data migration.** `DeidentifiedVisit` keeps its columns; Option C simply
  stops reading them into a payload. Whether to *also* stop storing them is a
  separate question worth asking once C ships — under C they have no consumer
  left except the dashboard, and a column with no consumer is a liability.

## 10. Parked, deliberately

- **Option A in any form.** Condition to revisit: a measurement finds a
  non-trivial identifier rate in the residual 245 entries, *and* a design is
  proposed that still sends free text.
- **GPU hosting (NodeShift and the wider GPU marketplace tier).** Condition to
  revisit: a workload appears that actually needs sustained inference — e.g. the
  parked bilingual generation, or the "ask your data" assistant. For one
  90-word generation a day it is the wrong instrument, but it is the right one
  for the distillation run itself if that is done on rented hardware rather than
  Distil Labs' free tier.
- **Dropping the per-group prose entirely** — *no longer parked; adopted, with
  the substance relocated rather than deleted.* The risk assessment proposed
  dropping it and the maintainer's objection was that donors want to know what
  is being treated, which is correct and is the actual requirement (§4a). The
  resolution is that the **daily** prose retires and the donor question is
  answered **monthly**, where it is both safer and 4.5× richer. Nothing the
  maintainer asked for is lost.
- **A per-day narrative in any form.** Condition to revisit: clinic-day volume
  rises far enough that per-day cells routinely clear a floor of 5. At ~10
  visits/day it is nowhere close — 8 such cells existed in three months.
- **The monthly newsletter's operator-typed notes and captions.** Out of scope
  here; needs its own decision.

## 11. Still needs a lawyer, not an engineer

Unchanged from the risk assessment's §6, with two updates:
- **Q2 (the DPA's "special categories: None" mismatch)** has a likely practical
  answer now — enable HIPAA readiness and get a BAA that contemplates PHI (D2).
  Whether that cures the mismatch for a non-US controller is still a lawyer's
  call.
- **Q1 (does UK GDPR apply)** should be re-asked against the corrected
  residency facts in D3: there is no UK processing leg at all.

## References

- `docs/ai-freetext-scrubbing-brief.md`, `docs/ai-freetext-risk-assessment.md`,
  `docs/ai-freetext-findings-2026-08-17.md` — all untracked (D0).
- Plan 11 Track B8/B9/B11 — the original decision and the parked option now
  being revisited. Plan 14 — the three-group split. Plan 15 Track C3 — the N=3
  floor. Plan 18a — the precedent for scrubbing published summaries.
- [Philter (npj Digital Medicine)](https://www.nature.com/articles/s41746-020-0258-y) — 99.92% recall on i2b2 2014.
- [Presidio evaluation, radiation oncology EMR](https://www.sciencedirect.com/science/article/abs/pii/S1386505622001940) — 80.6% strict recall.
- [*In the Name of Fairness*, FAccT '23](https://dl.acm.org/doi/abs/10.1145/3593013.3593982) — demographic bias in de-identification recall.
- [Anthropic: API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) — ZDR and HIPAA readiness (D2).
- [Distil Labs pricing](https://www.distillabs.ai/pricing/) and [deployment guide](https://www.distillabs.ai/learn/how-to-deploy-a-fine-tuned-small-language-model/).
