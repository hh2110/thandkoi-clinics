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

from apps.pipeline import urls


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
