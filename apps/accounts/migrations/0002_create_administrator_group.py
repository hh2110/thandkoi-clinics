"""Create the single Administrator group and attach its permission set.

Plan 07 (maintainer decision, PR #15): **one** Wagtail group, held by every
real account, granted every capability the clinic's ~3 trusted logins need —
see ``.claude/plans/07-accounts-roles.md`` "The role" and "What gets built".

This migration deliberately does **not** rely on ``Permission.objects.filter(...)``
finding rows created elsewhere. Django only auto-creates a model's
add/change/delete/view/custom permissions via the ``post_migrate`` signal,
which fires once, **after every migration in the run has already applied**
(see ``django.core.management.commands.migrate`` — ``emit_post_migrate_signal``
runs after ``executor.migrate()`` returns). On a fresh database — a new CI
run, a fresh clone — every app's migrations, including this one, apply in a
single ``migrate`` invocation, so none of those permissions exist yet when this
RunPython executes. Wagtail hits the same problem for its own ``access_admin``
permission and solves it the same way (see
``wagtail/admin/migrations/0001_create_admin_access_permissions.py``):
explicitly ``get_or_create`` the ``ContentType`` and ``Permission`` rows this
migration needs, rather than assuming they already exist. On an
already-migrated database (prod, a long-lived local dev DB) these calls just
find the rows ``post_migrate`` created in an earlier deploy — ``get_or_create``
makes both cases safe.

No user rows are created here (Plan 07 acceptance criteria) — see the account
setup checklist in the plan for how the three real accounts get provisioned
and added to this group, by hand, after this migration has run.
"""

from django.db import migrations

ADMINISTRATOR_GROUP_NAME = "Administrator"

# Non-page Django model permissions the Administrator group needs, keyed by
# (app_label, model) so each ContentType is looked up unambiguously, with a
# (codename, name) pair per permission on that model.
#
# Page create/edit/publish/lock/unlock is granted separately below via
# GroupPagePermission on the page-tree root, which is why "publish on all
# content types" doesn't need a content-type-by-content-type entry here — a
# root-page grant cascades to every current *and future* Page subclass
# (Wagtail's own tree-based permission model). These are the other
# permissions — this app's own custom one, plus the surfaces Wagtail's admin
# checks with plain Django model permissions (users/groups, images,
# documents, redirects) and this project's own site setting.
#
# A later plan that adds a new *non-page* permissioned model (a snippet, a
# new settings singleton) is not automatically covered by this list — Django
# model permissions don't cascade the way page permissions do. That plan's
# own migration should extend the Administrator group's permissions the same
# way this one does.
MODEL_PERMISSIONS = {
    ("accounts", "exportpermissions"): [
        ("can_upload_export", "Can upload a raw clinic data export"),
    ],
    ("wagtailadmin", "admin"): [
        ("access_admin", "Can access Wagtail admin"),
    ],
    ("auth", "group"): [
        ("add_group", "Can add group"),
        ("change_group", "Can change group"),
        ("delete_group", "Can delete group"),
        ("view_group", "Can view group"),
    ],
    ("auth", "user"): [
        ("add_user", "Can add user"),
        ("change_user", "Can change user"),
        ("delete_user", "Can delete user"),
        ("view_user", "Can view user"),
    ],
    ("wagtailimages", "image"): [
        ("add_image", "Can add image"),
        ("change_image", "Can change image"),
        ("delete_image", "Can delete image"),
        ("view_image", "Can view image"),
        ("choose_image", "Can choose image"),
    ],
    ("wagtaildocs", "document"): [
        ("add_document", "Can add document"),
        ("change_document", "Can change document"),
        ("delete_document", "Can delete document"),
        ("view_document", "Can view document"),
        ("choose_document", "Can choose document"),
    ],
    ("wagtailredirects", "redirect"): [
        ("add_redirect", "Can add redirect"),
        ("change_redirect", "Can change redirect"),
        ("delete_redirect", "Can delete redirect"),
    ],
    ("core", "contactbanksettings"): [
        ("add_contactbanksettings", "Can add contact & bank details"),
        ("change_contactbanksettings", "Can change contact & bank details"),
        ("view_contactbanksettings", "Can view contact & bank details"),
    ],
}

# GroupPagePermission entries, granted on the page-tree root so they cover
# every page in the tree — matches Wagtail's own Editors/Moderators groups
# (wagtail/migrations/0002_initial_data.py), just with the full permission
# set rather than a partial one, since there's only one role here.
PAGE_PERMISSIONS = [
    ("add_page", "Add/edit pages you own"),
    ("bulk_delete_page", "Delete pages with children"),
    ("change_page", "Edit any page"),
    ("lock_page", "Lock/unlock pages you've locked"),
    ("publish_page", "Publish any page"),
    ("unlock_page", "Unlock any page"),
]


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


def create_administrator_group(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    Group = apps.get_model("auth", "Group")
    Page = apps.get_model("wagtailcore", "Page")
    GroupPagePermission = apps.get_model("wagtailcore", "GroupPagePermission")

    group, _ = Group.objects.get_or_create(name=ADMINISTRATOR_GROUP_NAME)

    for (app_label, model), codename_names in MODEL_PERMISSIONS.items():
        for codename, name in codename_names:
            permission = _get_or_create_permission(
                Permission, ContentType, app_label, model, codename, name
            )
            group.permissions.add(permission)

    # The page-tree root (depth=1) — created by wagtailcore's own initial-data
    # migration, long since applied in every environment this migration can
    # possibly run in. A GroupPagePermission here covers every page below it.
    root = Page.objects.get(depth=1)
    for codename, name in PAGE_PERMISSIONS:
        permission = _get_or_create_permission(
            Permission, ContentType, "wagtailcore", "page", codename, name
        )
        GroupPagePermission.objects.get_or_create(
            group=group, page=root, permission=permission
        )


def remove_administrator_group(apps, schema_editor):
    """Reverse: drop the group (cascades its permission and page-permission rows).

    The permission/content-type rows created above are left in place — other
    groups or future migrations may reference them, and Wagtail's own
    equivalent migrations follow the same caution. No user rows are ever
    created by this migration (Plan 07 acceptance criteria), so there is
    nothing else to unwind.
    """
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("core", "0005_campreportindexpage_campreportpage_gallerypage_and_more"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
        ("wagtailadmin", "0006_formstate"),
        ("wagtailimages", "0027_image_description"),
        ("wagtaildocs", "0014_alter_document_file_size"),
        ("wagtailredirects", "0008_add_verbose_name_plural"),
    ]

    operations = [
        migrations.RunPython(create_administrator_group, remove_administrator_group),
    ]
