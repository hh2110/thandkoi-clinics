"""
Production settings.

Everything sensitive comes from the environment — the process must fail loudly
if a required secret is missing, rather than fall back to an insecure default.
"""

import sentry_sdk

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
        # Public host that serves the objects — a bare hostname, NO scheme and
        # no trailing slash (e.g. media.thandkoiclinics.com or pub-xxxx.r2.dev).
        # django-storages prepends https:// itself; a value like
        # "https://media.thandkoiclinics.com" would produce a broken
        # "https://https://…" URL for every file.
        "custom_domain": env("MEDIA_CUSTOM_DOMAIN"),
        # R2 ignores regions but the S3 client requires a value; "auto" is R2's.
        "region_name": "auto",
        # Public bucket: serve plain, cacheable URLs (no signed querystrings).
        "querystring_auth": False,
        # CDN cache hint for the public objects (renditions/documents are
        # effectively immutable once uploaded).
        "object_parameters": {"CacheControl": "public, max-age=86400"},
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

# --- Error tracking (Plan 12 Track A) ---------------------------------------

# Deliberately soft-fail, unlike every setting above: SENTRY_DSN is read with
# a blank default and the SDK is only initialized if it's non-empty, so a
# missing or revoked DSN degrades to "no error tracking," never a boot
# failure or a 500 (Plan 12 Decisions — observability must never become a new
# reason the site goes down).
SENTRY_DSN = env("SENTRY_DSN", default="")


def _sentry_before_send(event, hint):
    """Drop request bodies from every event before it leaves the process.

    This is the PHI-scrub belt to ``max_request_body_size="never"``'s braces
    (Plan 15 Track A1): the upload view receives a full patient export as a
    multipart request body, and an unhandled error anywhere in the request —
    not just in the upload path — would otherwise let Sentry attach that body
    (or a URL/form representation of it) to the event. A daily clinic export
    is raw PHI (CLAUDE.md invariant #1), so it must never cross into an
    external error-tracking service. We positively delete the request body
    representation rather than trust any single ``sentry_sdk.init`` knob to
    cover every shape it can take.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("body", None)
    return event


if SENTRY_DSN:
    # No release-tag env var is wired to the app yet (the Deploy workflow
    # passes the release commit to Render's deploy hook as a query param, not
    # as an env var — see .github/workflows/deploy.yml and scripts/release.sh).
    # RENDER_GIT_COMMIT is set automatically by Render for every build and is
    # the exact commit the deploying release tag points at, so it stands in
    # as the release identifier until a friendlier one is wired up.
    #
    # PHI scrubbing (Plan 15 Track A1) — this app handles raw patient exports
    # in-request (CLAUDE.md invariant #1), so error tracking must never carry
    # patient data out:
    #   * include_local_variables=False strips every frame-local from the
    #     stack traces Sentry captures — a parse/aggregation traceback would
    #     otherwise pin locals holding raw cell values or a whole DataFrame.
    #     Global, not targeted: for a PHI app the safe default is no
    #     frame-local capture anywhere; the marginal debugging loss is
    #     accepted (Plan 15 Decision 1).
    #   * max_request_body_size="never" tells the SDK not to read or attach
    #     request bodies at all — the upload view's body *is* a patient
    #     export. _sentry_before_send is the belt-and-braces backstop that
    #     positively drops any body representation that still slips through.
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        release=env.str("RENDER_GIT_COMMIT", default="") or None,
        environment="production",
        include_local_variables=False,
        max_request_body_size="never",
        before_send=_sentry_before_send,
    )
