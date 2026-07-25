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
ROBOTS_TXT = """User-agent: *
Disallow: /admin/
Disallow: /django-admin/
"""


def healthz(request):
    """
    Liveness/readiness probe.

    Returns HTTP 200 with a small JSON body when the app can reach the
    database, 503 otherwise. No authentication, no data exposure — safe for the
    host's health checks and for CI smoke tests.
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
