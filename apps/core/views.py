"""Plain Django views that sit outside the Wagtail page tree."""

from django.db import connection
from django.http import HttpResponse, JsonResponse


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
