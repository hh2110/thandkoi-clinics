"""Grant the Administrator group view access to Plan 11 C2's cost log.

``AiCallLog`` is a new non-page-permissioned model (a Wagtail snippet), so —
same as ``0003_grant_newsletter_draft_run_view_permission.py`` for
``NewsletterDraftRun`` — this migration extends the Administrator group
itself rather than assuming ``post_migrate`` has already created the
model's permissions (see that migration's docstring for the full
"why", and ``apps/accounts/migrations/0002_create_administrator_group.py``
for the note this follows).

Only ``view`` is granted: like ``NewsletterDraftRun``, this is a passive
audit/cost trail — an Administrator checks it, nothing here is meant to be
hand-edited or deleted from the admin.
"""

from django.db import migrations

ADMINISTRATOR_GROUP_NAME = "Administrator"


def _get_or_create_permission(
    Permission, ContentType, app_label, model, codename, name
):
    content_type, _ = ContentType.objects.get_or_create(
        app_label=app_label, model=model
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type, codename=codename, defaults={"name": name}
    )
    return permission


def grant_view_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")

    group = Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).first()
    if group is None:
        # Plan 07 hasn't run in this environment (e.g. a partial test setup
        # that never applies apps.accounts migrations) — nothing to grant to.
        return

    permission = _get_or_create_permission(
        Permission,
        ContentType,
        "pipeline",
        "aicalllog",
        "view_aicalllog",
        "Can view ai call log",
    )
    group.permissions.add(permission)


def revoke_view_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).first()
    if group is None:
        return
    permission = Permission.objects.filter(
        content_type__app_label="pipeline", codename="view_aicalllog"
    ).first()
    if permission is not None:
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0006_ai_call_log"),
        ("accounts", "0002_create_administrator_group"),
    ]

    operations = [
        migrations.RunPython(grant_view_permission, revoke_view_permission),
    ]
