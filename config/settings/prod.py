"""
Production settings.

Everything sensitive comes from the environment — the process must fail loudly
if a required secret is missing, rather than fall back to an insecure default.
"""

from .base import *  # noqa: F403
from .base import STORAGES, env

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

# HttpOnly: neither cookie needs to be read by JS. Session cookie is HttpOnly
# by Django default already; CSRF is not (Django's default is False, for
# apps that read the token from JS) — no template here does that, the CSRF
# token is always rendered server-side via {% csrf_token %}, so this can be
# locked down (Plan 07 privacy/security guardrail).
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

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

# --- Media storage (user uploads) ------------------------------------------

# WhiteNoise serves STATIC files only — it deliberately does not serve MEDIA —
# and Render's container filesystem is ephemeral (no persistent disk), so
# user-uploaded media (Wagtail images/renditions and documents) must live in
# external object storage. We use an S3-compatible bucket (Cloudflare R2) via
# django-storages. Media is served directly from the bucket's public domain, so
# no Django ``/media/`` route is involved (that dev-only route stays behind
# DEBUG in config/urls.py). All five values are required in prod: the process
# fails loudly at startup if the bucket isn't configured, rather than silently
# writing uploads to a disk that vanishes on the next deploy.
STORAGES["default"] = {
    "BACKEND": "storages.backends.s3.S3Storage",
    "OPTIONS": {
        "bucket_name": env("MEDIA_BUCKET_NAME"),
        "endpoint_url": env("MEDIA_S3_ENDPOINT_URL"),
        "access_key": env("MEDIA_S3_ACCESS_KEY_ID"),
        "secret_key": env("MEDIA_S3_SECRET_ACCESS_KEY"),
        # Public host that serves the objects (the R2 public bucket URL or a
        # custom domain such as media.thandkoiclinics.com). URLs render as
        # https://<custom_domain>/<key>.
        "custom_domain": env("MEDIA_CUSTOM_DOMAIN"),
        # R2 ignores regions but the S3 client requires a value; "auto" is R2's.
        "region_name": "auto",
        # Public bucket: serve plain, cacheable URLs (no signed querystrings).
        "querystring_auth": False,
        # Wagtail renditions are content-addressed; never clobber an upload that
        # happens to share a name.
        "file_overwrite": False,
        # R2 does not support ACLs — sending one is rejected.
        "default_acl": None,
        "signature_version": "s3v4",
    },
}

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
