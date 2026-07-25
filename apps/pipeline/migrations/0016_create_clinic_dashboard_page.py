"""Put the single ``ClinicDashboardPage`` into the tree (Plan 16 D1).

The page carries no editable fields at all — its title and every string on
it are code-driven — so creating it is a deploy step, not a content
decision. Doing it here means production needs no manual content-ops SSH
step (the route ``docs/content-operations.md`` describes) for a page nobody
will ever edit.

**This migration imports the real model, not ``apps.get_model``**, which is
the usual rule for data migrations. Wagtail pages leave no choice: putting
one in the tree means ``treebeard``'s ``add_child`` plus
``save_revision().publish()``, and a historical model has neither — it is a
plain ``Model`` with the fields as of this migration and none of the
``MP_Node``/``Page`` behaviour. The risk that rule guards against (a later
field change breaking an old migration) is small here and bounded: this
page type has no fields of its own to change, and the helper is a
get-or-create, so if it ever does break on a future replay the fix is to
no-op it rather than to reconstruct data.

Deliberately no-ops on a database that has no Reports index yet — a fresh
install runs migrations before anything has created one. That case is
covered instead by ``report_publishing.publish_daily_report``, which calls
the same get-or-create helper on the first ingest; see the helper's
docstring for the two directions.
"""

from django.db import migrations


def create_clinic_dashboard(apps, schema_editor):
    from apps.pipeline.models import ReportIndexPage
    from apps.pipeline.report_publishing import _get_or_create_clinic_dashboard

    if not ReportIndexPage.objects.exists():
        return
    _get_or_create_clinic_dashboard()


def delete_clinic_dashboard(apps, schema_editor):
    """Reverse: remove the page, so ``migrate pipeline 0015`` leaves no orphan.

    The dashboard row is deleted by 0015's own ``CreateModel`` reversal
    anyway, but its ``wagtailcore.Page`` row is not — that lives in a table
    this migration doesn't own, and would be left behind pointing at a
    content type with no concrete model. ``Page.delete()`` takes both.
    """
    from apps.pipeline.models import ClinicDashboardPage

    for page in ClinicDashboardPage.objects.all():
        page.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0015_clinicdashboardpage"),
    ]

    operations = [
        migrations.RunPython(create_clinic_dashboard, delete_clinic_dashboard),
    ]
