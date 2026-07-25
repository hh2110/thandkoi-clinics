"""
Project URL configuration.

The Wagtail page tree is served last, as a catch-all, so any URL not matched by
Django admin, Wagtail admin, documents, or our own views falls through to a
Wagtail page. Keep app URLs above ``wagtail_urls``.

The public page tree is wrapped in ``i18n_patterns`` so every front-end URL is
language-prefixed (``/en/...``, ``/ur/...``) — Plan 03's bilingual routing.
Infrastructure paths (health check, both admins, document serving) stay
unprefixed: they aren't bilingual content and editors/hosts shouldn't need a
locale in the URL to reach them.
"""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
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
    # Crawler directives (Plan 18). Unprefixed like the health check: robots.txt
    # is only ever read from the site root, so it must not sit behind
    # i18n_patterns' language prefix.
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    # Django admin (kept distinct from Wagtail's admin).
    path("django-admin/", admin.site.urls),
    # Wagtail admin and document serving.
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
]

# Development-only routes.
if settings.DEBUG:
    # Serve user-uploaded media in development only.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Wagtail's page serving — must come last (catch-all). Language-prefixed:
# visiting "/" 404s here and LocaleMiddleware redirects to "/en/" (or the
# visitor's detected language) — see apps/core/tests.py.
urlpatterns += i18n_patterns(
    path("", include(wagtail_urls)),
    prefix_default_language=True,
)
