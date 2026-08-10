"""Drop the ``CampReportPage``/``CampReportIndexPage`` tables (Plan 21).

**Schema first, data second** — the reverse of the order Plan 21's D5
proposed, and of the usual convention. The plan assumed a data migration
would delete the page rows and a schema migration would then drop the
models. Building it that way and running it against a local replica of
production (2026-08-10) showed why it cannot work:

* By the time this branch's migrations run, the model classes are already
  gone from ``apps/core/models.py``. Django's cascade collector walks the
  *live app registry*, so deleting a ``wagtailcore_page`` row no longer
  reaches the concrete ``core_campreportpage`` row hanging off it — the
  deferred foreign key then fails at COMMIT ("still referenced from table
  core_campreportpage").
* Deleting the concrete rows first through the migration-state model does
  not help either. A historical model of a multi-table-inheritance child
  cascades *upward*: ``CampReportPage.objects.all().delete()`` takes the
  parent ``wagtailcore_page`` row with it, as a plain Django delete with no
  ``treebeard`` bookkeeping. The pages vanish, and the home page is left
  claiming a child it no longer has (``numchild=2``, one actual child) —
  silent tree corruption, caught by ``Page.find_problems()`` on the replica.
  This is exactly the risk the plan's "deleting a Wagtail page type is not a
  normal migration" note warns about.

Dropping the tables first sidesteps both. It leaves the ``wagtailcore_page``
rows standing on their own for the length of one migration, with a content
type that has no model behind it — a state Wagtail tolerates deliberately
(``Page.get_specific()`` degrades to the base page when ``specific_class`` is
``None``) — and ``0021`` then deletes them through Wagtail's own ``Page``
API, which keeps ``path``/``depth``/``numchild`` correct. Verified on the
replica: ``Page.find_problems()`` comes back clean.

Both migrations belong to the same deploy. Neither is reversible in any
useful sense: reversing this one recreates empty tables, and ``0021`` cannot
bring back deleted content.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_alter_homepage_body"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="campreportpage",
            name="page_ptr",
        ),
        migrations.RemoveField(
            model_name="campreportpage",
            name="report_document",
        ),
        migrations.DeleteModel(
            name="CampReportIndexPage",
        ),
        migrations.DeleteModel(
            name="CampReportPage",
        ),
    ]
