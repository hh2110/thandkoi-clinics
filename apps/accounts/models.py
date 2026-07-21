"""The one custom permission this plan exists to add.

Plan 07's whole scope is narrow: one Wagtail **Administrator** group (built in
a data migration, see ``migrations/0002_create_administrator_group.py``) and
one custom Django permission, ``can_upload_export``, that Plan 08's raw-export
upload view will guard with ``@permission_required`` — no Wagtail page
permission fits an upload, since no page is involved.

``ExportPermissions`` is a dummy model that exists only to attach that
permission to, mirroring Wagtail's own idiom for the same problem (see
``wagtail.admin.models.Admin``, which does the same for ``access_admin``):
``default_permissions = []`` skips Django's own add/change/delete/view perms
(there is nothing to add/change/delete — this model has no fields and no
rows), leaving only the one permission this app is here to define.
"""

from django.db import models


class ExportPermissions(models.Model):
    class Meta:
        default_permissions: list[str] = []
        permissions = [
            ("can_upload_export", "Can upload a raw clinic data export"),
        ]

    def __str__(self):
        return "Export permissions"
