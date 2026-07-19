# Thandkoi Clinics

Website and data pipeline for **The Thandkoi Clinics** — a not-for-profit,
family-run primary care clinic in Thandkoi, Swabi (KPK, Pakistan), funded on a
Zakat / Sadaqa model.

The project has two parts:

1. **Public website** — about the charity, management structure, services, camp
   reports, newsletters, a photo gallery, daily/monthly impact reports, and a
   donate (Zakat/Sadaqa) placeholder with contact and bank details.
2. **AI-native data pipeline** — clinic staff upload a daily Excel export from
   the clinic software; the pipeline aggregates it (discarding raw patient data),
   publishes a daily report page, and generates a monthly newsletter on demand.

> **Privacy first:** raw patient data (PHI) is never stored and never sent to any
> AI model. Only de-identified aggregates leave the parser. See the brief below.

## Docs

- [Architecture & AI Capability Brief](docs/architecture-and-ai-brief.md)
- [Brand Guidelines](docs/brand-guidelines.md)

## Status

Early planning. Stack (proposed): Django + Wagtail + HTMX, PostgreSQL,
Anthropic Python SDK. See the brief for details.
