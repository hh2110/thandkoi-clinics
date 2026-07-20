"""Plain Django views that sit outside the Wagtail page tree."""

from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe

# --- Plan 03.5 styleguide icons --------------------------------------------
# Small, author-controlled inline SVGs for the service-card icon slots. Trusted
# markup only (rendered via |safe in _card.html) — never user input. Coral is
# used solely for the cross/heart motif, per brand-guidelines.md §2/§7.
#
# Colours are set via a `style="..."` attribute, not an SVG presentation
# attribute (fill="..."/stroke="..."): CSS custom properties only resolve inside
# a CSS declaration, so `fill="var(--color-coral)"` would render black/none —
# a `style` declaration resolves the token correctly.
_ICON_CROSS = mark_safe(  # noqa: S308 - static, author-authored markup
    '<svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">'
    '<rect x="8" y="3" width="4" height="14" rx="1" '
    'style="fill:var(--color-coral)"></rect>'
    '<rect x="3" y="8" width="14" height="4" rx="1" '
    'style="fill:var(--color-coral)"></rect>'
    "</svg>"
)
_ICON_CIRCLE = mark_safe(  # noqa: S308 - static, author-authored markup
    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">'
    '<circle cx="10" cy="10" r="7" '
    'style="fill:none;stroke:var(--color-brand)" stroke-width="2.5"></circle>'
    "</svg>"
)
_ICON_DIAMOND = mark_safe(  # noqa: S308 - static, author-authored markup
    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">'
    '<rect x="4" y="4" width="12" height="12" rx="2" transform="rotate(45 10 10)" '
    'style="fill:none;stroke:var(--color-brand)" stroke-width="2.5"></rect>'
    "</svg>"
)


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


def styleguide(request):
    """
    Temporary Plan 03.5 preview of the page-body layout kit.

    Renders every section partial (hero, stat band, card grid, feature split,
    CTA band, media grid) with dummy context so the kit is reviewable before
    Plan 04 composes real pages from it. This view and its template are
    throwaway — removed/replaced when Plan 04 lands (see the plan's task 9).
    Its route is registered only when ``settings.DEBUG`` is true (see
    ``config/urls.py``), so it is dev-only and never served in production.

    All numbers and copy below are illustrative demo data only, exactly like
    the docs/design/ mockups — the components themselves bake in nothing.
    """
    context = {
        "impact_stats": [
            {"value": "120/day", "label": "patients seen at the OPD"},
            {"value": "36k+", "label": "consultations a year"},
            {"value": "24", "label": "free medical camps held"},
            {"value": "100%", "label": "donor-funded, no fees"},
        ],
        "service_cards": [
            {
                "icon_svg": _ICON_CROSS,
                "title": "Daily OPD clinic",
                "body": (
                    "General consultations, chronic-disease follow-up, and "
                    "basic diagnostics six days a week."
                ),
            },
            {
                "icon_svg": _ICON_CIRCLE,
                "title": "Medical camps",
                "body": (
                    "Periodic outreach camps bringing screening and treatment "
                    "to surrounding villages."
                ),
            },
            {
                "icon_svg": _ICON_DIAMOND,
                "title": "Zakat-funded care",
                "body": (
                    "Your Zakat and Sadaqa cover medicines and treatment for "
                    "those who cannot pay."
                ),
                "tag": "Planned",
            },
        ],
        "report_stats": [
            {"value": "128", "label": "patients seen"},
            {"value": "61 / 67", "label": "women / men"},
        ],
        "gallery_items": [{}, {}, {}, {}],
    }
    return render(request, "core/styleguide.html", context)
