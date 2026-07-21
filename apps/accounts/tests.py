"""Tests for Plan 07 — the Administrator group and the invariant-#4 gate.

The important test here is
``test_administrator_can_publish_but_automation_user_cannot``: it is the
acceptance criterion CLAUDE.md invariant #4 depends on — an AI/automation
identity that only ever calls ``save_revision()`` must be structurally
unable to publish, while an Administrator can. See
``.claude/plans/07-accounts-roles.md`` "How invariant #4 is enforced".
"""

from django.contrib.auth.models import Group, Permission

from apps.core.factories import HomePageFactory


def test_administrator_group_exists_after_migration(db):
    """The migration creates exactly one Administrator group — no manual clicking."""
    assert Group.objects.filter(name="Administrator").count() == 1


def test_administrator_group_has_the_documented_permission_set(db):
    """The group carries access_admin, can_upload_export, and content management
    permissions — the set Plan 07 documents, not whatever happened to get
    clicked together by hand."""
    group = Group.objects.get(name="Administrator")
    codenames = set(
        group.permissions.values_list("content_type__app_label", "codename")
    )
    assert ("accounts", "can_upload_export") in codenames
    assert ("wagtailadmin", "access_admin") in codenames
    assert ("auth", "add_user") in codenames
    assert ("auth", "add_group") in codenames
    assert ("core", "change_contactbanksettings") in codenames
    assert ("wagtailimages", "add_image") in codenames
    assert ("wagtaildocs", "add_document") in codenames


def test_administrator_group_has_full_page_permissions_on_the_tree_root(db):
    """Granted on the tree root, not per page type — covers every current and
    future Page subclass, matching Wagtail's own Editors/Moderators idiom."""
    group = Group.objects.get(name="Administrator")
    page_perm_codenames = set(
        group.page_permissions.values_list("permission__codename", flat=True)
    )
    assert page_perm_codenames == {
        "add_page",
        "bulk_delete_page",
        "change_page",
        "lock_page",
        "publish_page",
        "unlock_page",
    }
    # Granted at the root, not some page further down the tree.
    root_depth = {pp.page.depth for pp in group.page_permissions.all()}
    assert root_depth == {1}


def test_administrator_can_publish_but_automation_user_cannot(db, django_user_model):
    """The invariant-#4 gate: an Administrator can publish; a plain automation
    identity — one call.save_revision() would use, with no publish permission —
    cannot. This is what makes "every AI-generated page is a draft a human
    approves" an enforced permission boundary rather than a stated intention.
    """
    page = HomePageFactory()

    administrator = django_user_model.objects.create_user(
        username="administrator",
        password="x",  # noqa: S106
    )
    administrator.groups.add(Group.objects.get(name="Administrator"))

    automation = django_user_model.objects.create_user(
        username="automation",
        password="x",  # noqa: S106
    )

    assert page.permissions_for_user(administrator).can_publish() is True
    assert page.permissions_for_user(automation).can_publish() is False


def test_can_upload_export_permission_gates_administrators_only(db, django_user_model):
    """Placeholder for Plan 08's upload view: the permission exists and is held
    only by Administrators — tightened once the view lands and can be
    exercised through a real request."""
    assert Permission.objects.filter(
        content_type__app_label="accounts", codename="can_upload_export"
    ).exists()

    administrator = django_user_model.objects.create_user(
        username="uploader",
        password="x",  # noqa: S106
    )
    administrator.groups.add(Group.objects.get(name="Administrator"))

    other = django_user_model.objects.create_user(
        username="no-upload",
        password="x",  # noqa: S106
    )

    assert administrator.has_perm("accounts.can_upload_export") is True
    assert other.has_perm("accounts.can_upload_export") is False
