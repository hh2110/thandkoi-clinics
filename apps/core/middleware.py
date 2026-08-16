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
from django.http import HttpResponseNotFound
from django.utils.cache import get_max_age

logger = logging.getLogger(__name__)


# --- Scanner short-circuit (Plan 24 Track E) ---------------------------------
#
# Measured 2026-08-16, after Track A's cache shipped: the cache works (two page
# loads served with the Neon compute asleep and zero database contact), but the
# burn rate only fell ~6%, because the bottleneck moved. What now wakes the
# compute is largely **404s from vulnerability scanners**, which Track A
# deliberately never caches — it stores 200s only.
#
# Each such probe cost **seven** database queries — measured, by disabling the
# short-circuit and watching ``test_a_scanner_probe_costs_zero_database_queries``
# report "Expected to perform 0 queries but 7 were done" — and, far more
# expensively, restarted Neon's five-minute idle clock. They come from three
# places:
#
#   1. Wagtail's catch-all looking the path up in the page tree.
#   2. ``RedirectMiddleware`` firing on the 404 and looking for a redirect.
#   3. ``404.html`` extending ``base.html``, whose footer and navigation read
#      site settings through Wagtail's settings context processor.
#
# A scanner gets nothing from a branded 404 page, so recognising the obviously
# bogus paths and answering with a bare 404 — no page lookup, no redirect
# lookup, no template — removes all three.
#
# Caught in the act: a ``Not Found: /wp-admin/install.php`` at 20:54:49 on
# 2026-08-16 was the last request keeping the compute awake before it suspended.

#: Suffixes that can never be legitimate here. This is the single
#: highest-value rule: a Django/Wagtail site serves **no PHP under any
#: circumstance**, so one check covers ``wp-login.php``, ``install.php``,
#: ``xmlrpc.php``, ``phpmyadmin/index.php`` and most of the long tail without
#: anyone maintaining a list of bots.
SCANNER_SUFFIXES = (".php", ".asp", ".aspx", ".jsp", ".cgi")

#: Substrings that mark a request as a scanner probe wherever they appear in
#: the path. Substring rather than prefix matching on purpose: the same
#: scanners hit both ``/wp-admin/…`` and ``/en/wp-admin/…`` (a bare probe gets
#: language-prefixed by ``LocaleMiddleware`` first).
#:
#: **Kept deliberately narrow.** Every entry is either WordPress-specific or a
#: dotfile that no page slug could produce. Generic English words are excluded
#: even when scanners use them: the same scan on 2026-08-16 probed ``/news/``
#: and ``/blog/``, and this clinic could legitimately publish either, so
#: blocking them would break a real page the day someone adds it. A missed
#: probe costs one wake; a wrongly-blocked page is a broken site.
SCANNER_PATH_MARKERS = (
    "/wp-admin",
    "/wp-includes",
    "/wp-content",
    "/wp-json",
    "/wp-login",
    "/wp/",
    "/wordpress/",
    "wlwmanifest",
    "/xmlrpc",
    "/phpmyadmin",
    "/.env",
    "/.git/",
    "/.aws",
    "/.ssh",
)

#: Deliberately NOT blocked, recorded so nobody adds it later thinking it was
#: an oversight: ``/.well-known/``. Render terminates TLS at its edge so the
#: app should never see an ACME challenge — but "should never" is not "cannot",
#: and 404ing a certificate-renewal challenge would break HTTPS for the whole
#: site. That is a catastrophic downside against saving at most one wake.


def is_scanner_path(path):
    """True for paths only a vulnerability scanner would ask for.

    Pure string matching — no database, no settings, nothing that could make
    the cheap path expensive.
    """
    lowered = path.lower()
    if lowered.endswith(SCANNER_SUFFIXES):
        return True
    return any(marker in lowered for marker in SCANNER_PATH_MARKERS)


class ScannerShortCircuitMiddleware:
    """Answer obvious scanner probes with a bare 404, touching no database.

    Placement is load-bearing and it must stay **above**
    ``wagtail.contrib.redirects.middleware.RedirectMiddleware`` in
    ``MIDDLEWARE``. ``RedirectMiddleware`` acts on the 404 *response*, so a
    short-circuit from below it would still let it run its redirect lookup —
    one of the three queries this exists to avoid. Above it, it never sees the
    request at all.

    It is also above ``SessionMiddleware`` and ``AuthenticationMiddleware``, so
    a probe carrying a stale cookie cannot trigger a session load either.

    Returns a plain body rather than rendering ``404.html`` **on purpose**:
    that template extends ``base.html``, whose footer reads
    ``ContactBankSettings`` from the database. Rendering a branded 404 for a
    bot would reintroduce the very query being removed, and a scanner gains
    nothing from it. Humans who mistype a URL are unaffected — their paths
    don't match these patterns, so they still get the normal branded page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_scanner_path(request.path):
            return HttpResponseNotFound(b"Not Found")
        return self.get_response(request)


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


def _cache_get(key):
    """Read from the cache, treating any failure as a miss.

    The cache is an optimisation; it must never be able to take the site down.
    ``FileBasedCache`` touches the filesystem on every read and write, so a
    full disk, a read-only mount, or a permissions change would otherwise raise
    on *every request* and turn a cost optimisation into a total outage.

    This is the same principle ``config/database.py`` was written around after
    the 2026-07-26 outage: a blip in a dependency should degrade the site, not
    wedge it. Here degrading means "serve the page from the database", which is
    exactly what happened before this middleware existed.
    """
    try:
        return cache.get(key)
    except Exception:  # noqa: BLE001 - any cache failure is just a miss
        logger.warning("Page cache read failed; serving uncached", exc_info=True)
        return None


def _cache_set(key, response, timeout):
    """Write to the cache, swallowing any failure. See :func:`_cache_get`."""
    try:
        cache.set(key, response, timeout)
    except Exception:  # noqa: BLE001 - failing to cache is not a failed request
        logger.warning("Page cache write failed; not cached", exc_info=True)


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
        cached = _cache_get(key)
        if cached is not None:
            return cached

        response = self.get_response(request)

        if should_cache_response(request, response):
            # A template response has to be rendered before it can be stored;
            # by the time middleware sees it, Django has already done so, but
            # be explicit rather than storing an unrendered object.
            if hasattr(response, "render") and callable(response.render):
                response.add_post_render_callback(lambda r: _cache_set(key, r, timeout))
            else:
                _cache_set(key, response, timeout)

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
