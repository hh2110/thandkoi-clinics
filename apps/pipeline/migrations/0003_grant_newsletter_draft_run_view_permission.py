"""Grant the Administrator group view access to Plan 09's audit trail.

``NewsletterDraftRun`` is a new non-page-permissioned model (a Wagtail
snippet), so — per the explicit note in
``apps/accounts/migrations/0002_create_administrator_group.py`` ("A later
plan that adds a new *non-page* permissioned model ... is not automatically
covered by this list ... That plan's own migration should extend the
Administrator group's permissions the same way this one does") — this
migration extends the Administrator group itself, following that migration's
own ``get_or_create`` pattern (the model's ``view``/``add``/``change``/
``delete`` permissions are only guaranteed to exist once ``post_migrate``
has fired, which is *after* every migration in a fresh-database run has
already applied).

Only ``view`` is granted: this is a passive audit trail (Plan 09's "failure
visibility" decision, PR #17) — an Administrator checks it, nothing here is
meant to be hand-edited or deleted from the admin.
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
        "newsletterdraftrun",
        "view_newsletterdraftrun",
        "Can view newsletter draft run",
    )
    group.permissions.add(permission)


def revoke_view_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).first()
    if group is None:
        return
    permission = Permission.objects.filter(
        content_type__app_label="pipeline", codename="view_newsletterdraftrun"
    ).first()
    if permission is not None:
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0002_newsletter_draft_run"),
        ("accounts", "0002_create_administrator_group"),
    ]

    operations = [
        migrations.RunPython(grant_view_permission, revoke_view_permission),
    ]
