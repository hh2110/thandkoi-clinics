# Thandkoi Clinics — Architecture & AI Capability Brief

_Last updated: 2026-07-19 · Status: planning_

## 1. Context

The Thandkoi Clinics is a not-for-profit, family-run primary care clinic in
Thandkoi, Swabi (Khyber Pakhtunkhwa, Pakistan), inaugurated on **16 May 2026**
and funded on a **Zakat / Sadaqa** model. Free consultation and examination are
offered to all patients; medicines and diagnostics are fully covered for Zakat
beneficiaries. Services span general medicine, paediatrics, gynaecology,
psychiatry, and telemedicine, with lab and imaging planned.

The clinic already produces newsletters, camp reports, and an organisational
profile, and runs medical software that exports Excel files. This project turns
that into (a) a public website and (b) an AI-native data pipeline that publishes
impact reports and generates newsletters — while keeping patient data private.

### Goals

1. A public website for the charity (about, team, services, reports,
   newsletters, gallery, donate placeholder, contact/bank details).
2. A daily pipeline: staff upload an Excel export → it is aggregated → a daily
   report page is published.
3. Extensibility: accept **new** export types in future without re-releasing
   code.
4. A funding-grade shopfront that can back applications for larger projects.

## 2. Guiding decisions

| Decision | Choice | Why |
|---|---|---|
| Who builds/owns it | Built as a custom app the charity owns (Git repo) | Full control of the pipeline + AI; not locked into a no-code tool |
| Maintainer skillset | **Python** expert, little/no JavaScript | Drives the stack choice |
| Budget | ~US$20–30 / month | Mostly free tiers + a few dollars of AI usage + domain |
| Domain | `thandkoiclinics.com` | Matches branding |
| Sequencing | **Website first**, pipeline second | Ship the shopfront, then automate |
| Raw patient data | **Never stored** — aggregate on upload, discard | Minimises PHI liability (clinician decision) |
| Admins | ≤ 20 people; most are **viewers of public pages** and need no login | Only 2–4 uploaders/approvers need accounts |

## 3. Technology stack

- **Django** — batteries-included web framework: authentication, ORM, admin,
  forms, migrations, secure defaults.
- **Wagtail** (a CMS built on Django) — a friendly content editor for
  non-technical staff, with a **draft → preview → publish** workflow that serves
  as the review gate for all published content.
- **HTMX** — the small amount of interactivity (upload, "generate newsletter"),
  written in HTML/Python with effectively no JavaScript.
- **pandas / openpyxl / xlrd** — Excel parsing and aggregation.
- **Anthropic Python SDK** — newsletter/report drafting, translation, schema
  inference, and the site assistant.
- **PostgreSQL** — aggregates and de-identified data only (never raw PHI).
- **Hosting** — Render or Railway (~$7/mo) + managed Postgres; static assets and
  any de-identified files in private object storage.

Everything is Python and lives in one codebase and one deployment.

## 4. Privacy posture (the core invariant)

The daily export contains full protected health information (PHI): patient name,
father's/husband's name, date of birth, address, vitals, complaints, diagnoses,
and prescribed medicines. Therefore:

1. **Raw PHI is never persisted.** On upload, the file is parsed and aggregated
   **in memory during the request**, then discarded. Two things are stored:
   de-identified aggregates, and a **de-identified row-level table** — direct
   identifiers (name, father's/husband's name, address) stripped on the way
   in, never written even transiently. The row-level table exists to support
   report types and date-range queries we haven't anticipated yet, without
   re-deriving new aggregate tables for every new question.
2. **The AI never sees a patient row.** Aggregation happens in Python first;
   only de-identified numbers and category counts are ever passed to a model.
3. **Numbers are deterministic.** Every published figure is computed in Python
   and injected into prompts; the model is instructed to use those exact numbers
   and never to invent statistics. The AI writes prose; Python does the counting.
4. **Human-in-the-loop.** All AI output lands as a Wagtail draft and is reviewed
   before it is published.

```
Clinic software ──export──▶ daily .xls/.xlsx
                                   │  (login-only upload, HTTPS)
                                   ▼
              ┌──────────── DJANGO / WAGTAIL APP ───────────┐
              │  Parser registry (pandas)                   │
              │   • one parser per export format            │
              │   • clean / dedup / strip identifiers       │
              │   • RAW FILE DISCARDED here ✗               │
              │            │                                │
              │   de-identified aggregates + row-level table│
              │            ▼                                │
              │        PostgreSQL  ◀── permanent             │
              │            │                                │
              │   ┌────────┴─────────┐                      │
              │   ▼                  ▼                      │
              │  Public report    Anthropic API             │
              │  pages (numbers)  (aggregates only)         │
              │                    → draft newsletter/report │
              └──────────────────────────────────────────────┘
                     │                        │
             Public website          Wagtail admin (2–4 users)
        (about, team, gallery,      • upload daily export
         reports, newsletters,      • trigger monthly newsletter
         donate placeholder)          + add photos/notes → review
```

## 5. Website structure

- **Home** — mission, impact numbers, latest report/newsletter, donate CTA
- **About** — vision, mission, objectives, quality-of-care model, partners
- **Team / Management** — founders, officers, committees
- **Our Work** — services, infrastructure, camp reports
- **Reports** — auto-generated daily (high-level) and monthly report pages
- **Newsletters** — archive
- **Gallery** — photos
- **Donate (Zakat/Sadaqa)** — placeholder: bank details + "contact us to donate"
- **Contact** — phone, email, socials, bank details, location
- **Admin (login only)** — upload, generate, review, download de-identified data

> Contact and bank details are configured in the running application, not stored
> in this repository.

## 6. AI-native capability

"AI-native" here means the model is a first-class layer for ingesting data,
drafting content, translating, and answering questions — always behind the
privacy invariant in §4. Three tiers:

### 6.1 Ingest — understand new data (supports goal 3)

For a **new** export format, an agentic step (Claude with tools via the Python
SDK) inspects the file's **structure** — column names, dtypes, a de-identified or
synthetic sample — infers the schema, and proposes aggregations. A human
approves once; the result becomes a saved parser. New report types onboard
without a code release. The model sees column shapes, never real patient rows.

### 6.2 Generate — content from aggregates, reviewed by a human

- **Daily report page** — a short narrative wrapped around deterministic numbers.
- **Monthly newsletter** — the "one-shot prompt with tooling": the model receives
  the month's aggregates + the admin's notes + photos and calls small tools
  (`get_month_stats`, `get_trend_vs_last_month`, `get_previous_newsletter` for
  voice consistency) to draft the newsletter as a Wagtail draft for review.
- **Bilingual output** — English + Urdu (and Pashto), auto-drafted and reviewed;
  meaningful accessibility for the local community.
- **Funding-grade spin-outs (goal 4)** — executive summaries and impact
  narratives generated from the same aggregates for grant applications.

### 6.3 Interact — grounded Q&A

- **Public site assistant** — retrieval-augmented over *published* pages only, so
  answers to donor/visitor questions are grounded in the charity's own content.
- **Internal "ask your data"** — a chat over the *aggregate* tables for
  management (never patient-level).

### Model selection

| Task | Model | Model ID |
|---|---|---|
| Newsletter/report drafting, schema inference | Claude Opus 4.8 | `claude-opus-4-8` |
| Translation, image alt-text, summaries, site assistant | Claude Haiku 4.5 | `claude-haiku-4-5` |

These are small text calls over aggregate payloads, so real spend is a few
dollars per month — within budget.

### Where it lives in the app

A dedicated `ai` module wraps the Anthropic Python SDK and exposes the tool
functions. Wagtail content models carry an `ai_draft` field alongside the
human-approved published state. The parser registry and the de-identification
boundary sit upstream of the `ai` module, so the AI layer cannot reach raw data
by construction.

## 7. Roadmap

1. **Website (first):** informational pages, team, services, camp reports,
   newsletter archive, gallery, donate placeholder, contact/bank details.
2. **Pipeline core:** authenticated upload, parser registry, aggregate-and-discard,
   daily report page.
3. **AI generation:** monthly newsletter with tooling + human review; bilingual
   drafting.
4. **Interaction:** public site assistant; internal "ask your data".
5. **Future:** additional export types via agentic schema inference; funding-
   application exports.

## 8. Open items

- ~~Confirm domain registration for `thandkoiclinics.com`.~~ Registered via
  Cloudflare Registrar, 2026-07-19.
- Confirm the list of admin accounts (uploaders/approvers).
- ~~Provide logo and brand assets.~~ Done — see
  [brand-guidelines.md](brand-guidelines.md).
- ~~Decide whether to retain the optional de-identified row-level table or
  keep aggregates only.~~ Decided — retain the de-identified row-level table
  (see §4).
