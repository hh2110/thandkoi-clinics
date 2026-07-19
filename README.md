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

## Tech stack

Django 5.2 (LTS) + Wagtail 7.4 (CMS) + HTMX, PostgreSQL, served by gunicorn with
WhiteNoise for static files. Dependencies are managed with
[uv](https://docs.astral.sh/uv/); linting/formatting with
[ruff](https://docs.astral.sh/ruff/); tests with pytest + pytest-django. Config
comes from the environment via `django-environ`.

## Local development

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (manages Python
  3.12 and the virtualenv for you)
- Docker (for the local PostgreSQL service), or a local PostgreSQL 16 server

### Setup

```bash
# 1. Install the pinned Python + all dependencies into a local .venv
uv sync

# 2. Create your local env file and adjust if needed (safe defaults included)
cp .env.example .env

# 3. Start PostgreSQL (matches DATABASE_URL in .env.example)
docker compose up -d

# 4. Apply database migrations
uv run python manage.py migrate

# 5. Create an admin login for the Wagtail admin
uv run python manage.py createsuperuser
```

### Run

```bash
uv run python manage.py runserver
```

- Site: <http://localhost:8000/>
- Wagtail admin: <http://localhost:8000/admin/>
- Health check: <http://localhost:8000/healthz> (returns `{"status": "ok"}`)

> On a fresh database the site root is Wagtail's default welcome page. Sign in to
> the admin and add a **Home page** (the `HomePage` type), then set it as the
> site's root page under **Settings → Sites**.

### Quality checks

```bash
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pytest                # tests
uv run pre-commit install    # enable the git pre-commit hooks (ruff)
```

### Settings modules

Settings are split under `config/settings/`:

- `config.settings.dev` — local development (default for `manage.py`)
- `config.settings.prod` — production (default for `wsgi`/`asgi`); `DEBUG=False`,
  locked-down `ALLOWED_HOSTS`, security headers on

Select one with the `DJANGO_SETTINGS_MODULE` environment variable.

## Deployment

Production runs on [Render](https://render.com/) (Starter compute) against a
single [Neon](https://neon.tech/) Postgres database, described by
[`render.yaml`](render.yaml). Deploys are **manual and tag-based** — merging to
`main` never changes production by itself; a person runs the `Deploy` workflow
against a chosen release tag. Full flow, rollback, versioning, and how AI
content is reviewed separately are in **[docs/deploying.md](docs/deploying.md)**.

## Docs

- [Deploying](docs/deploying.md)
- [Architecture & AI Capability Brief](docs/architecture-and-ai-brief.md)
- [Brand Guidelines](docs/brand-guidelines.md)
- [Build plans](.claude/plans/README.md)
