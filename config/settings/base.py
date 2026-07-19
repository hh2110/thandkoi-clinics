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
    "apps.pipeline",
    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files in every environment; kept high in the
    # stack so it runs right after the security middleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Must come after SessionMiddleware, before CommonMiddleware (Django
    # docs). Activates the request language from the /en/, /ur/ URL prefix
    # used by i18n_patterns in config/urls.py, and redirects unprefixed
    # public URLs to the detected language.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
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
                # Contact/bank/social placeholders for the footer — config,
                # not hardcoded content (see apps/core/context_processors.py).
                "apps.core.context_processors.org_contact",
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

# --- Org contact / bank / socials (site footer placeholders) ---------------
# "Contact and bank details are configured in the running application, not
# stored in this repository" (architecture brief). Plan 03 wires the footer
# to read these rather than hardcoding placeholder text; Plan 05 (Donate)
# will likely move bank details into a proper Wagtail-editable settings model
# once there's real content to manage — env vars are enough for now.
ORG_CONTACT_EMAIL = env("ORG_CONTACT_EMAIL", default="")
ORG_CONTACT_PHONE = env("ORG_CONTACT_PHONE", default="")
ORG_BANK_DETAILS = env("ORG_BANK_DETAILS", default="")
ORG_SOCIAL_LINKS = env.dict("ORG_SOCIAL_LINKS", default={})
