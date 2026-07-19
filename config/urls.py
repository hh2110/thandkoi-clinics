"""
Project URL configuration.

The Wagtail page tree is served last, as a catch-all, so any URL not matched by
Django admin, Wagtail admin, documents, or our own views falls through to a
Wagtail page. Keep app URLs above ``wagtail_urls``.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from apps.core import views as core_views

urlpatterns = [
    # Liveness/readiness probe for the host and for CI smoke tests.
    path("healthz", core_views.healthz, name="healthz"),
    # Django admin (kept distinct from Wagtail's admin).
    path("django-admin/", admin.site.urls),
    # Wagtail admin and document serving.
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
]

# Serve user-uploaded media in development only.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page serving — must come last (catch-all).
urlpatterns += [
    path("", include(wagtail_urls)),
]
