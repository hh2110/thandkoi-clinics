"""Plain Django views that sit outside the Wagtail page tree."""

from django.db import connection
from django.http import HttpResponse, JsonResponse

#: Plan 18. Deliberately does NOT disallow the daily report pages, even
#: though those are the pages we want out of search results. The two
#: mechanisms pull in opposite directions: a crawler must be allowed to
#: *fetch* a page before it can read the ``noindex`` meta tag telling it to
#: drop the page. Disallowing ``/reports/`` here would strand any
#: already-indexed URL in the index permanently, because Google would never
#: re-fetch it to learn it should go. So removal from the index is the meta
#: tag's job (see ``pipeline/daily_report_page.html``) and this file covers
#: only the admin surfaces, which have nothing to gain from being crawled.
#: Agents disallowed outright (Plan 24 Track B, D6). These exist to scrape
#: content for training corpora or resale, not to refer readers to the clinic,
#: so there is nothing to lose by turning them away.
#:
#: **Googlebot and Bingbot are deliberately absent and must stay absent.** A
#: not-for-profit clinic needs to be findable; suppressing search indexing to
#: save compute would trade the site's purpose for its hosting bill.
_SCRAPER_AGENTS = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "anthropic-ai",
    "CCBot",
    "Google-Extended",  # Gemini training corpus — NOT Googlebot's indexing
    "PerplexityBot",
    "Bytespider",
    "Amazonbot",
    "meta-externalagent",
    "Applebot-Extended",
    "Diffbot",
    "omgili",
)

_SCRAPER_RULES = "\n\n".join(
    f"User-agent: {agent}\nDisallow: /" for agent in _SCRAPER_AGENTS
)

#: Plan 18. Deliberately does NOT disallow the daily report pages, even
#: though those are the pages we want out of search results. The two
#: mechanisms pull in opposite directions: a crawler must be allowed to
#: *fetch* a page before it can read the ``noindex`` meta tag telling it to
#: drop the page. Disallowing ``/reports/`` here would strand any
#: already-indexed URL in the index permanently, because Google would never
#: re-fetch it to learn it should go. So removal from the index is the meta
#: tag's job (see ``pipeline/daily_report_page.html``) and this file covers
#: only the admin surfaces, which have nothing to gain from being crawled.
#:
#: Plan 24 adds the crawl budget half. ``Crawl-delay`` is honoured by Bing and
#: Yandex and ignored by Google (which has its own rate control), and the
#: scraper block above is honoured only by crawlers that choose to be polite.
#: **This is advisory and is not the fix** — the crawlers costing the most
#: compute may well be exactly the ones ignoring this file. The page cache in
#: ``apps.core.middleware`` is what actually bounds the cost.
ROBOTS_TXT = f"""User-agent: *
Disallow: /admin/
Disallow: /django-admin/
Crawl-delay: 10

{_SCRAPER_RULES}
"""


def healthz(request):
    """
    Liveness probe. Answers "is this process serving?" and nothing else.

    **This view must never touch the database** (Plan 23 D1). It used to run a
    ``SELECT 1``, and that single query was enough to cost the project its
    entire hosting plan: Render polls ``healthCheckPath`` roughly every five
    seconds, so the probe alone issued ~17,000 queries a day. Neon's
    scale-to-zero needs five consecutive idle minutes and never got them — the
    compute ran continuously from 2026-07-26 to 2026-08-13, burning ~195
    CU-hours a month against a 100 CU-hour allowance.

    The database check now lives in :func:`readyz`, which is polled once per
    deploy instead of twelve times a minute.

    ``apps/core/tests.py`` asserts this request issues **zero** queries, rather
    than merely asserting this function doesn't call ``cursor()`` — middleware
    could reintroduce one without touching this file, which would silently
    re-arm the whole problem.

    No authentication, no data exposure — safe for the host's health checks and
    for CI smoke tests.
    """
    return JsonResponse({"status": "ok"})


def readyz(request):
    """
    Readiness probe: can this build actually reach its database?

    Returns HTTP 200 with a small JSON body when the database answers, 503
    otherwise. Split out of :func:`healthz` in Plan 23 so that the expensive
    half of the old probe runs on a cadence someone chose deliberately.

    **Do not point a high-frequency poller at this path.** Every request keeps
    the Neon compute awake for a further five minutes; that is the cost that
    made this split necessary. Today its only scheduled caller is
    ``scripts/release.sh``, once per release, which is exactly when "did the
    new build come up able to reach Postgres" can newly be false.

    The ``except Exception`` below is load-bearing but was historically not
    enough on its own: during the 2026-07-26 outage a *blocked* connect is not
    an exception, so this handler never fired and the probe hung instead of
    answering 503. What made this path real is the bounded ``connect_timeout``
    in ``config/database.py`` — keep the two in mind together.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - any DB error means "not ready"
        return HttpResponse(
            '{"status": "error"}',
            status=503,
            content_type="application/json",
        )
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    """Serve ``/robots.txt``. See :data:`ROBOTS_TXT` for what it deliberately omits."""
    return HttpResponse(ROBOTS_TXT, content_type="text/plain")
