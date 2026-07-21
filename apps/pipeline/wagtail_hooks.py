"""Register the export-upload view in the Wagtail admin.

Grounded against Wagtail's own idiom for a permission-gated, non-page admin
screen — mirrors ``wagtail/contrib/redirects/wagtail_hooks.py`` (a
``MenuItem`` subclass overriding ``is_shown`` for the permission check, plus
``register_admin_urls``). No in-repo precedent existed before this plan (an
upload view is new), so this is grounded against the Wagtail admin-hooks
docs/source rather than invented (Stage 3/7).
"""

from django.urls import include, path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from apps.pipeline import urls
from apps.pipeline.models import NewsletterDraftRun


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path("pipeline/", include(urls, namespace="pipeline")),
    ]


class UploadExportMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.has_perm("accounts.can_upload_export")


@hooks.register("register_admin_menu_item")
def register_upload_export_menu_item():
    return UploadExportMenuItem(
        _("Upload clinic export"),
        reverse("pipeline:upload_export"),
        name="pipeline-upload-export",
        icon_name="upload",
        order=9000,
    )


class NewsletterDraftRunViewSet(SnippetViewSet):
    """Read-mostly admin listing for Plan 09's audit trail.

    Grounded against Wagtail's own snippets feature (no in-repo precedent —
    ``IngestRun``, the pattern this mirrors, isn't registered anywhere in the
    admin yet). This is Plan 09's "failure visibility" decision (PR #17): no
    email/alert on a failed drafting run, but an Administrator must be able
    to see it here. Visibility is gated by the ``view_newsletterdraftrun``
    Django permission, granted to the Administrator group by this app's own
    migration — see ``apps/pipeline/migrations`` and Plan 07's
    ``0002_create_administrator_group.py`` docstring on why a new
    non-page-permissioned model needs its own such migration.
    """

    model = NewsletterDraftRun
    icon = "clipboard-list"
    menu_label = "Newsletter draft runs"
    menu_order = 9100
    list_display = ("month", "status", "created_at", "triggered_by", "newsletter_page")
    ordering = ["-created_at"]


register_snippet(NewsletterDraftRunViewSet)
