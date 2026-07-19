"""
Production settings.

Everything sensitive comes from the environment — the process must fail loudly
if a required secret is missing, rather than fall back to an insecure default.
"""

from .base import *  # noqa: F403
from .base import env

# Fail fast if these are not provided by the environment.
DEBUG = False

SECRET_KEY = env("SECRET_KEY")

# Locked down: only the hosts we explicitly allow. On Render this is the
# service's external hostname (RENDER_EXTERNAL_HOSTNAME) plus any custom domain.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# DATABASE_URL is required in production (managed Postgres).
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# --- Security hardening ----------------------------------------------------

# TLS is terminated by the platform (Render) proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# CSRF trusted origins must be full scheme://host entries; derived from the
# allowed hosts unless explicitly provided.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[f"https://{host}" for host in ALLOWED_HOSTS if host != "*"],
)

# --- Logging ---------------------------------------------------------------

# Plain console logging; the platform captures stdout/stderr.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
}
