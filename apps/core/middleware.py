"""Cache public page responses so repeat crawler hits never reach Postgres.

Why this exists — the compute bill, not page speed
--------------------------------------------------
Plan 23 stopped ``/healthz`` querying the database, which cut Neon compute burn
by 70% (6.38 → 1.92 CU-hr/day). It was not enough: measured 2026-08-16, the
free tier's 100 CU-hour allowance would still be exhausted around 23 August,
nine days before it resets, and an exhausted compute means the site is *down*
because every page reads Postgres.

The remaining load is not the WordPress scanners — those are ~112 requests in
three days. It is **~740 successful page loads a day** (`/en/{var}`, all HTTP
200) against a site Umami measures at ~15 human page views a day: non-JS
crawlers. Neon suspends after five idle minutes, so what costs money is not the
query, it's each request *restarting the five-minute clock*.

Hence a cache. Within a crawler burst — 9 hits inside 75 seconds is typical
here — the first request pays for the database and the rest are free.

Why hand-written instead of ``wagtail-cache`` (Plan 24 D1)
----------------------------------------------------------
Every dependency in ``pyproject.toml`` is pinned with an upper bound and CI
runs a separate supply-chain gate, so a new runtime dependency isn't free. More
to the point, the failure modes here — serving a logged-in editor's rendered
page to the public, or serving content after it was unpublished — are the kind
that must be *explicitly* testable rather than emergent from Django's
``Vary: Cookie`` handling. This module follows the same shape as
``apps/pipeline/middleware.py`` and ``config/observability.py``: plain,
heavily-commented functions the test suite can exercise directly.

The safety rule, and the one precondition that could change
-----------------------------------------------------------
:func:`should_cache_response` refuses to cache anything that sets a cookie.
That single check is what keeps session- and CSRF-establishing responses out of
a shared cache without reasoning about ``Vary`` at all.

**Checked, not assumed (2026-08-16): this site's public pages contain no forms
— no ``<form>`` outside the admin templates, and no ``csrf_token`` in any
template.** So the classic "cached page hands every visitor the same stale CSRF
token" hazard does not exist here. *If a public form is ever added, revisit
this module before shipping it*, because a cached form page is exactly how that
bug arrives.
"""

import logging

from django.core.cache import cache
from django.utils.cache import get_max_age

logger = logging.getLogger(__name__)

#: Cache-key namespace. Bumping this string invalidates every cached page at
#: once, which is the cheap escape hatch if a bad entry is ever suspected.
CACHE_KEY_PREFIX = "pagecache:v1"

#: Path prefixes never served from cache, whatever else is true. These are the
#: authenticated and per-user surfaces; caching any of them shared across
#: visitors would be a disclosure bug, not a staleness bug.
NEVER_CACHE_PREFIXES = (
    "/admin/",
    "/django-admin/",
    "/documents/",
)


def is_cacheable_request(request):
    """True when this request may be *served* from a shared cache.

    Deliberately conservative and positive: everything must be true, rather
    than a list of things that disqualify. ``GET`` only (never ``HEAD``, which
    would let a bodyless response poison a key a ``GET`` later reads).
    """
    if request.method != "GET":
        return False

    if any(request.path.startswith(prefix) for prefix in NEVER_CACHE_PREFIXES):
        return False

    # ``request.user`` is lazy, so touching it can hit the database — but only
    # for a request that actually carries a session cookie, which crawler
    # traffic (the whole point of this cache) does not. Checked last so the
    # cheap tests above short-circuit first.
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return False

    return True


def should_cache_response(request, response):
    """True when ``response`` is safe to *store* in a shared cache.

    ``Set-Cookie`` is the load-bearing check (see the module docstring): any
    response establishing a session or CSRF cookie must never be handed to a
    second visitor, and refusing on the header covers every way that arises.
    """
    if not is_cacheable_request(request):
        return False

    if response.status_code != 200:
        return False

    # Check BOTH representations. ``response.set_cookie()`` populates
    # ``response.cookies`` (a SimpleCookie) and does *not* add a Set-Cookie
    # header — that is only serialised later, by the WSGI handler, long after
    # middleware has run. A ``has_header("Set-Cookie")`` check alone therefore
    # returns False for every cookie Django itself sets, which would have let
    # session- and CSRF-establishing responses straight into the shared cache.
    # Caught by `test_a_response_that_sets_a_cookie_is_never_stored`, which
    # failed against exactly that mistake before this line was widened.
    if response.cookies or response.has_header("Set-Cookie"):
        return False

    # An explicit no-store/private from a view or another middleware outranks
    # us. ``get_max_age`` returns 0 for ``Cache-Control: max-age=0``.
    if response.has_header("Cache-Control"):
        cache_control = response["Cache-Control"].lower()
        if "no-store" in cache_control or "private" in cache_control:
            return False
        if get_max_age(response) == 0:
            return False

    # Streaming responses have no ``content`` to store, and reading one would
    # consume it.
    if getattr(response, "streaming", False):
        return False

    return True


def cache_key_for(request):
    """Namespaced key for a request.

    Includes the full path *and* query string, so the clinic dashboard's date
    ranges (``?start=…&end=…``) don't collide, and the language prefix
    (``/en/``, ``/ur/``) separates locales for free.
    """
    query = request.META.get("QUERY_STRING", "")
    suffix = f"?{query}" if query else ""
    return f"{CACHE_KEY_PREFIX}:{request.path}{suffix}"


class PageCacheMiddleware:
    """Serve cached public pages; store the ones that are safe to store.

    Placed **last** in ``MIDDLEWARE``, i.e. innermost: a cache hit then skips
    the view and the whole Wagtail page lookup, which is the database work
    worth avoiding.

    It must **not** be moved to the top of the list. ``AuthenticationMiddleware``
    has to run first, or ``request.user`` is not set when
    :func:`is_cacheable_request` looks at it, and the "never serve a logged-in
    user from a shared cache" guard silently stops firing — the disclosure bug
    that guard exists to prevent.

    Everything listed above stays outer and still runs on a hit. That includes
    Wagtail's ``RedirectMiddleware``, which is harmless here: it only queries
    the database on a 404, and only 200s are ever cached.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout = get_cache_seconds()

        # 0 disables the cache entirely (Plan 24 D8) — the no-deploy rollback.
        if timeout <= 0 or not is_cacheable_request(request):
            return self.get_response(request)

        key = cache_key_for(request)
        cached = cache.get(key)
        if cached is not None:
            return cached

        response = self.get_response(request)

        if should_cache_response(request, response):
            # A template response has to be rendered before it can be stored;
            # by the time middleware sees it, Django has already done so, but
            # be explicit rather than storing an unrendered object.
            if hasattr(response, "render") and callable(response.render):
                response.add_post_render_callback(lambda r: cache.set(key, r, timeout))
            else:
                cache.set(key, response, timeout)

        return response


def get_cache_seconds():
    """Read the dialable TTL from settings, soft-failing to the default.

    Imported lazily from settings on each request so the value can be changed
    without a deploy in the same spirit as ``SENTRY_TRACES_SAMPLE_RATE`` —
    and so a bad value degrades to the default instead of breaking the site
    (Plan 24 D5).
    """
    from django.conf import settings

    return parse_cache_seconds(getattr(settings, "CACHE_PAGE_SECONDS", None))


#: Three hours. Long enough that a crawler returning hourly pays the database
#: only every third visit, short enough that content changing *without* a page
#: publish — a snippet, a settings object, which D4's signals don't catch —
#: self-heals the same working day.
DEFAULT_CACHE_SECONDS = 3 * 60 * 60


def parse_cache_seconds(raw, default=DEFAULT_CACHE_SECONDS):
    """Coerce ``CACHE_PAGE_SECONDS`` to a usable timeout.

    Mirrors ``observability.parse_sample_rate`` and
    ``database.parse_connect_timeout``: an operational dial must degrade to its
    default on a typo, never take the site down. ``0`` is honoured here (unlike
    in those two) because for a cache TTL, "off" is a meaningful and useful
    setting — it is this plan's rollback lever.
    """
    if raw is None or raw == "":
        return default

    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparseable CACHE_PAGE_SECONDS %r; using %s seconds",
            raw,
            default,
        )
        return default

    if seconds < 0:
        logger.warning(
            "Ignoring negative CACHE_PAGE_SECONDS %r; using %s seconds",
            raw,
            default,
        )
        return default

    return seconds


#: Registered as snippets, but internal admin logs that never render on a
#: public page. ``AiCallLog`` in particular is written on *every* AI call,
#: including inside the daily report's auto-publish, so invalidating on it
#: would clear the cache repeatedly for no reader-visible reason — quietly
#: undoing the compute saving this module exists for.
NEVER_PUBLIC_MODELS = frozenset({"pipeline.aicalllog", "pipeline.newsletterdraftrun"})


def _is_publicly_rendered(model):
    """True for models an editor changes that appear on a public page.

    The registries are read **here, at call time, not at connect time**. That
    is load-bearing: snippets are registered in ``wagtail_hooks.py``, which
    Wagtail imports *after* every ``AppConfig.ready()`` has run, so a version
    of this that looped over ``get_snippet_models()`` inside ``ready()`` would
    connect nothing at all and silently never invalidate.
    """
    from wagtail.contrib.settings.registry import registry as settings_registry
    from wagtail.snippets.models import get_snippet_models

    if model._meta.label_lower in NEVER_PUBLIC_MODELS:
        return False

    return model in set(get_snippet_models()) | set(settings_registry)


def clear_page_cache_for_model(sender, **kwargs):
    """``post_save``/``post_delete`` receiver for editor-facing content.

    Pages are not the only thing rendered into a cached page. Snippets and the
    settings singletons are edited in the admin and saved with **no page
    publish**, so :func:`clear_page_cache`'s Wagtail signals never fire for
    them. Without this, an editor correcting the clinic's bank details would
    see the old ones served for up to ``CACHE_PAGE_SECONDS`` — three hours of
    wrong account numbers on a donations page.

    Connected globally and filtered here rather than per-sender, for the
    registry-timing reason in :func:`_is_publicly_rendered`. The filter is a
    couple of set lookups, and the high-volume write path (an export upload's
    ``DeidentifiedVisit`` rows) doesn't reach it anyway — ``bulk_create`` emits
    no ``post_save``.
    """
    if not _is_publicly_rendered(sender):
        return
    clear_page_cache()


def clear_page_cache(**kwargs):
    """Drop every cached page. Wired to Wagtail's publish signals.

    Whole-cache rather than per-key by decision (Plan 24 D4): publishing is
    rare here and a partial invalidation that misses a path leaves withdrawn
    content publicly readable. ``**kwargs`` absorbs the signal arguments.
    """
    cache.clear()
    logger.info("Page cache cleared")
