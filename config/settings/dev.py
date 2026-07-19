"""
Development settings.

Sensible, insecure-by-design defaults so a fresh checkout boots without a
``.env``. Never used in production (``DJANGO_SETTINGS_MODULE`` selects
``config.settings.prod`` there).
"""

from .base import *  # noqa: F403
from .base import STORAGES, env

DEBUG = env.bool("DEBUG", default=True)

# Development-only key. Overridden by SECRET_KEY from the environment if set.
# Safe to commit because it is only ever used with DEBUG on, locally.
SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-dev-key-not-for-production-use-only",  # noqa: S106
)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "0.0.0.0"],  # noqa: S104
)

# Local Postgres, matching docker-compose.yml. Override with DATABASE_URL.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://thandkoi:thandkoi@localhost:5432/thandkoi",
    ),
}

# Print emails to the console instead of sending them.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# In dev, let WhiteNoise serve straight from the static source dirs via Django's
# finders, so `collectstatic` isn't required just to run the app or the tests.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

# Use plain (non-manifest) static storage in dev — the hashed-manifest backend
# in base.py requires `collectstatic` to have run, which we don't want locally.
STORAGES["staticfiles"]["BACKEND"] = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
)

# Show Wagtail's more verbose page-editing niceties in dev.
WAGTAIL_ENABLE_UPDATE_CHECK = False
