"""Template context processors for apps.core."""

from django.conf import settings


def analytics(request):
    """Expose the Umami website ID (Plan 12 Track B) to every template."""
    return {"UMAMI_WEBSITE_ID": settings.UMAMI_WEBSITE_ID}
