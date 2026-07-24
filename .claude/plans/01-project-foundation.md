# Plan 01 — Project Foundation

_Status: Drafted · Depends on: none · Next: 02 Development lifecycle & environments_

## Goal

A running, deployable Django + Wagtail project with clean settings, a database,
CI, and developer tooling — the skeleton every later step builds on. No clinic
content or pipeline yet; this step is "empty app boots, admin loads, CI green,
deploy configured."

## Scope

**In scope**
- Django + Wagtail project scaffold and repository layout.
- Dependency management and pinned versions.
- Split settings (base / dev / prod) with environment-driven config.
- PostgreSQL for local + prod; a health-check page.
- Developer tooling: formatter/linter, tests, pre-commit, editorconfig.
- CI (GitHub Actions: lint + test).
- Deployment configuration for the chosen host (not necessarily a live deploy).

**Out of scope** (later plans)
- Any clinic-specific pages or models → Plans 02–05.
- Auth roles → Plan 06. Pipeline/AI → Plans 07–09. Deploy hardening → out of
  scope for now (see the [plans README](README.md#out-of-scope-for-now) —
  Ops hardening).

## Proposed decisions (confirm before building)

| Choice | Proposed | Notes |
|---|---|---|
| Python | 3.12 | Pin via `.python-version`. |
| Django / Wagtail | Django 5.x / Wagtail 6.x (latest stable) | Wagtail pins its supported Django range. |
| Dependency manager | **uv** (`pyproject.toml` + `uv.lock`) | Fast; Python-expert friendly. Fallback: pip-tools. |
| Local database | PostgreSQL via `docker-compose` | Mirrors prod. Optional SQLite fallback for quick runs. |
| Config | `django-environ` reading `.env` | Keeps secrets out of code. |
| ORM / migrations | **Django ORM + Django's built-in migrations** (`makemigrations`/`migrate`) | Not SQLAlchemy/Alembic — Wagtail's pages, admin, permissions, and tree structure are all built on the Django ORM, so a second ORM would mean two migration systems tracking overlapping schema with no real benefit. Django's migrations *are* the migration tooling here. |
| Lint / format | **ruff** (lint + format) | Replaces black + isort + flake8. |
| Tests | pytest + pytest-django + **factory_boy** | factory_boy for model fixtures in integration tests, instead of hand-rolled `Model.objects.create(...)` calls in every test. |
| Pre-commit | `pre-commit` running ruff | |
| Host | **Render** via `render.yaml` blueprint | Alternative: Railway. |
| WSGI/ASGI server | gunicorn | |
| Static files | WhiteNoise | Simple static serving for a small site. |

## Proposed repository layout

```
thandkoi-clinics/
├── CLAUDE.md
├── README.md
├── pyproject.toml            # deps + tool config (ruff, pytest)
├── uv.lock
├── .python-version
├── .env.example              # documented, safe placeholder values
├── .pre-commit-config.yaml
├── docker-compose.yml        # local Postgres
├── render.yaml               # deploy blueprint
├── manage.py
├── config/                   # project package
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/                     # our Django/Wagtail apps live here
│   └── core/                 # base templates, health check, home placeholder
│       ├── __init__.py
│       ├── apps.py
│       ├── models.py         # minimal Wagtail HomePage placeholder
│       ├── templates/
│       └── migrations/
├── templates/                # project-level base templates
├── static/                   # source static assets
├── docs/
│   └── architecture-and-ai-brief.md
├── .claude/
└── .github/
    └── workflows/
        └── ci.yml
```

## Task checklist

1. **Bootstrap tooling** — `pyproject.toml`, `.python-version`, ruff + pytest
   config, `.editorconfig`, `.pre-commit-config.yaml`.
2. **Create the project** — `wagtail start` (or `django-admin startproject`) into
   the `config/` layout; move settings into `config/settings/` (base/dev/prod).
3. **Config & secrets** — wire `django-environ`; add `.env.example`; confirm
   `.env` is gitignored (it is). `SECRET_KEY`, `DATABASE_URL`, `DEBUG`,
   `ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE` come from env.
4. **Database** — `docker-compose.yml` with Postgres; `DATABASE_URL` for local +
   prod; run initial Django migrations (`makemigrations` + `migrate`).
5. **Core app** — `apps/core` with a minimal Wagtail `HomePage` placeholder and a
   `/healthz` view returning 200; project `base.html`.
6. **Static** — WhiteNoise; `collectstatic` works.
7. **Tests** — one smoke test (home renders 200, `/healthz` returns 200); a
   `factory_boy` factory for the `HomePage` placeholder so later plans have a
   pattern to extend rather than inventing one per app.
8. **CI** — `.github/workflows/ci.yml`: install (uv), ruff check, run pytest
   against a Postgres service container.
9. **Deploy config** — `render.yaml` (web service + Postgres), gunicorn start
   command, `collectstatic` build step, env vars documented in `.env.example`.
10. **README update** — local-run instructions (setup, migrate, run, test).

## Acceptance criteria

- `uv sync` (or documented equivalent) installs the environment cleanly.
- `python manage.py migrate` and `runserver` work against local Postgres.
- The home page renders and the Wagtail admin (`/admin/`) loads locally.
- `/healthz` returns HTTP 200.
- `ruff check` passes; `pytest` passes (smoke test green).
- CI is green on the PR.
- `render.yaml` is present and reviewed (a live deploy is optional this step).
- No secrets committed; `.env.example` documents every required variable.

## Privacy guardrails to bake in now

- Confirm `.gitignore` blocks `*.xls`, `*.xlsx`, `/uploads/`, `/data/`, `.env`.
- No analytics or third-party scripts that could leak data by default.
  > **2026-07-24:** the "by default" always left room for a deliberate,
  > recorded opt-in later — [Plan 12](12-observability.md) is that decision,
  > adding a cookieless, aggregate-only traffic analytics script for exactly
  > that reason. This bullet's intent (no *silent* tracking) still stands.
- `DEBUG=False` and a locked-down `ALLOWED_HOSTS` in prod settings.

## Decided (was open questions)

- **uv** over pip-tools — confirmed, no objection raised.
- **Render** over Railway — confirmed; Plan 02's production hosting decision is
  Render-specific, so this also locks Render in for that plan.
- **Config-only** for this step — `render.yaml` present and reviewed, but no
  live deploy. The live production deploy is
  [Plan 02](02-development-lifecycle.md)'s job, once there's a CD pipeline and
  an approval gate to deploy through.
- **Python 3.12** — kept as proposed; no reason raised to move to 3.13 yet.
- **factory_boy** for integration-test fixtures — confirmed, added to the Tests
  row and task checklist.
- **DB migrations** — Django's own migration framework, not a separate tool;
  it's what step 4 of the task checklist runs.
- **SQLAlchemy / Alembic** — not used. Wagtail requires the Django ORM for its
  own models (pages, admin, permissions), so introducing SQLAlchemy would mean
  running two ORMs and two migration systems side by side for no benefit.
  Django ORM + Django migrations is the only migration tooling in this stack.
