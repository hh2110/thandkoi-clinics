"""
Base settings shared by every environment.

Environment-specific settings live in ``dev.py`` and ``prod.py``, which import
everything from here and then override. Select one with the
``DJANGO_SETTINGS_MODULE`` environment variable
(e.g. ``config.settings.dev`` or ``config.settings.prod``).

All secrets and per-environment values are read from the environment (via a
``.env`` file in local dev). Nothing sensitive is hard-coded here.
"""

from pathlib import Path

import environ

# config/settings/base.py -> config/settings -> config -> <repo root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Read a local .env if present. In production, real environment variables are
# used instead (Render injects them), so a missing .env file is fine.
env_file = BASE_DIR / ".env"
if env_file.exists():
    env.read_env(str(env_file))

# --- Core security ---------------------------------------------------------

# No insecure default: prod must supply SECRET_KEY. dev.py provides a
# development-only fallback so a fresh checkout can boot without a .env.
SECRET_KEY = env("SECRET_KEY", default=None)

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# --- Applications ----------------------------------------------------------

INSTALLED_APPS = [
    # Our apps
    "apps.core",
    "apps.accounts",
    "apps.pipeline",
    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    # Third-party used by Wagtail
    "modelcluster",
    "taggit",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Plan 16 task 16.3: `intcomma`, for the clinic dashboard's thousands
    # separators. Enabled rather than hand-rolled because `USE_THOUSAND_SEPARATOR`
    # is a site-wide switch that would also re-format every year, ID and
    # figure elsewhere on the site — this stays opt-in, one filter at a time.
    "django.contrib.humanize",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files in every environment; kept high in the
    # stack so it runs right after the security middleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Near the top on purpose (Plan 24 Track E). Answers obvious scanner probes
    # with a bare 404 before anything can touch the database. It MUST stay
    # above RedirectMiddleware — that middleware acts on the 404 *response*, so
    # short-circuiting from below it would still let it run a redirect lookup,
    # one of the seven queries a probe was measured to cost. Above
    # SessionMiddleware too, so a probe carrying a stale cookie can't trigger a
    # session load.
    "apps.core.middleware.ScannerShortCircuitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Must come after SessionMiddleware, before CommonMiddleware (Django
    # docs). Activates the request language from the /en/, /ur/ URL prefix
    # used by i18n_patterns in config/urls.py, and redirects unprefixed
    # public URLs to the detected language.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Must come BEFORE CsrfViewMiddleware: the CSRF check reads request.POST on
    # a POST, which parses the multipart body and locks request.upload_handlers.
    # This installs the memory-only handler for the clinic-export upload while
    # the body is still unparsed (the swap is impossible afterwards). See
    # apps/pipeline/middleware.py.
    "apps.pipeline.middleware.MemoryOnlyUploadHandlerMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
    # Last on purpose (Plan 24 Track A) = innermost, so a cache hit skips the
    # view and the whole Wagtail page lookup, which is the database work worth
    # avoiding. It must NOT be moved to the top: AuthenticationMiddleware has
    # to have run first, or `request.user` isn't set and the middleware's
    # "never serve a logged-in user from a shared cache" guard silently can't
    # fire. RedirectMiddleware stays outer and still runs on every request,
    # which is harmless — it only queries on a 404, and only 200s are cached.
    # See apps/core/middleware.py for why this is a compute measure, not a
    # speed one.
    "apps.core.middleware.PageCacheMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Exposes LANGUAGE_CODE / LANGUAGE_BIDI / LANGUAGES to every
                # template — base.html's <html lang dir> switch reads these.
                "django.template.context_processors.i18n",
                # Exposes site-wide Wagtail settings (Plan 04's Contact & Bank
                # Details singleton) to every template as `settings.<app>.<Model>`.
                # The footer and Contact page read the shared setting from here,
                # so editing it in /admin/ updates both with no redeploy.
                "wagtail.contrib.settings.context_processors.settings",
                # Exposes UMAMI_WEBSITE_ID (Plan 12 Track B) to every template —
                # base.html's analytics script tag reads it directly.
                "apps.core.context_processors.analytics",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database --------------------------------------------------------------

# Parsed from a single DATABASE_URL, e.g.
# postgres://user:pass@host:5432/dbname
# dev.py supplies a local Postgres default so a fresh checkout works with the
# bundled docker-compose service.
DATABASES = {
    "default": env.db("DATABASE_URL"),
}

# --- Password validation ---------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# --- Internationalisation --------------------------------------------------

# Content is English + Urdu (Pashto may follow); build with i18n on from day one.
LANGUAGE_CODE = "en"

# Native autonyms (how a language names itself), not English translations of
# the name — that's what shows in the language switcher.
LANGUAGES = [
    ("en", "English"),
    ("ur", "اردو"),
]

# .po files for UI-string translation (Plan 03 wires the directory; Plan 10
# is the first plan to actually add translated strings, content translation
# is a separate, wagtail-localize concern).
LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

# --- Static & media --------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Compressed + hashed filenames, served by WhiteNoise.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Wagtail ---------------------------------------------------------------

WAGTAIL_SITE_NAME = "The Thandkoi Clinics"

WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    },
}

# Base URL used by Wagtail e.g. in notification emails; overridden per env.
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")

# Restrict document file types to a safe set (no Excel exports, ever).
WAGTAILDOCS_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "gif", "webp"]

# --- Traffic analytics (Plan 12 Track B) ------------------------------------
# Umami Cloud website ID. Blank by default — with no value set, base.html
# renders no script tag at all, so a fresh checkout, local dev, and CI behave
# identically to before this existed. This is a public, non-sensitive value
# (it ships in every page's HTML source either way), unlike SENTRY_DSN, so it
# doesn't need Render's secret handling — a plain env var is enough.
UMAMI_WEBSITE_ID = env("UMAMI_WEBSITE_ID", default="")

# --- Page cache (Plan 24 Track A) -------------------------------------------
# This exists to keep Neon's compute asleep, not to make pages faster: each
# uncached request restarts Neon's five-minute idle clock, and ~740 crawler
# page-loads a day were enough to burn the free tier's whole allowance. See
# apps/core/middleware.py for the full reasoning.
#
# FileBasedCache rather than LocMemCache (D2): gunicorn runs multiple workers
# and LocMem is per-process, so each worker would keep its own copy and the hit
# rate — the only thing that matters here — would be divided by the worker
# count. A file cache is shared by every worker on the instance and needs no
# new service. Render's disk is ephemeral per deploy, which is fine: a cold
# cache after a deploy costs one repopulation, not correctness.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": env("CACHE_DIR", default=str(BASE_DIR / ".page-cache")),
        # Bounded so a runaway crawl over unique query strings can't fill the
        # disk; Django culls a third of entries when the count is exceeded.
        "OPTIONS": {"MAX_ENTRIES": 2000},
    }
}

# Seconds to keep a cached page. Dialable from the Render dashboard with no
# deploy, like DB_CONNECT_TIMEOUT and SENTRY_TRACES_SAMPLE_RATE. **0 turns the
# cache off entirely** — that is this plan's rollback lever (D8). Read as a
# string and coerced in apps.core.middleware.parse_cache_seconds so a blank or
# mistyped value degrades to the default instead of breaking boot.
CACHE_PAGE_SECONDS = env("CACHE_PAGE_SECONDS", default="")

# --- Org contact / bank / socials ------------------------------------------
# "Contact and bank details are configured in the running application, not
# stored in this repository" (architecture brief). Plan 03 read these from
# env vars as a footer placeholder; Plan 04 replaces that with a proper
# Wagtail-editable singleton — the ``ContactBankSettings`` site setting in
# apps/core/models.py — so a non-technical admin edits them in /admin/ and both
# the footer and the Contact page update with no redeploy. Nothing sensitive
# lives in the repo or the environment any more.
