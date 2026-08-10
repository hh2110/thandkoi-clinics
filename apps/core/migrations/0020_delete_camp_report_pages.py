"""Delete the camp-report page rows before 0021 drops their models (Plan 21).

Retiring a Wagtail page type is two migrations, in this order. This one takes
the *content* out of the tree; ``0021`` then drops the tables. Reversing the
order would leave ``wagtailcore_page`` rows pointing at a content type with no
concrete model behind it — rows Wagtail's admin cannot render and this
migration could no longer identify.

**Imports the real ``wagtail.models.Page``, not ``apps.get_model``**, for the
deletion itself — the same exception ``pipeline/0016`` documents, for the same
reason. A page is a ``treebeard`` node with ``path``/``depth``/``numchild``
bookkeeping plus revisions and log entries; a historical model is a plain
``Model`` with none of that behaviour, so deleting through it corrupts the
tree. Identification still goes through the migration state
(``apps.get_model("core", "CampReportPage")``) — that needs no behaviour, only
a list of ids, and looking pages up by *type* rather than by hardcoded id is
what makes this safe to run against a fresh install, a re-run, or a database
where someone already deleted them by hand.

**The redirect trap.** ``Redirect.redirect_page`` is a ``CASCADE`` foreign
key, so deleting a page silently destroys every redirect pointing *at* it.
The two redirects that preserve the retired camp URLs
(``/en/camp-reports/free-sugar-camp-report`` and
``/en/camp-reports/inauguration-report``) point at the surviving
``NewsletterPage`` replacements, not at anything deleted here, so the risk is
currently zero — but this migration asserts that rather than trusting it. If a
redirect ever does point at a page being deleted, it refuses to run and says
so; repoint the redirect first, then re-run.

Stale ``django_content_type`` rows for the two models are deliberately left
behind. Wagtail's page log entries survive the pages they describe (by design
— ``PageLogEntry.page`` carries no database constraint) and still reference
those content types; deleting the rows would dangle them. They are inert
otherwise, and ``manage.py remove_stale_contenttypes`` can sweep them by hand
if the maintainer ever wants to.

Irreversible: the pages and their revisions are gone once this runs. That is
the accepted trade in the plan's rollback section — both pages were already
unpublished and both URLs already redirect to live newsletter issues, so
nothing a reader can reach depends on them.
"""

from django.db import migrations

CAMP_MODELS = ("CampReportPage", "CampReportIndexPage")


def delete_camp_report_pages(apps, schema_editor):
    from wagtail.models import Page

    Redirect = apps.get_model("wagtailredirects", "Redirect")

    # Children first, then the index — a page's own delete() takes its subtree
    # with it, but being explicit keeps the order legible and independent of
    # treebeard's cascade behaviour.
    page_ids = []
    for model_name in CAMP_MODELS:
        model = apps.get_model("core", model_name)
        page_ids.extend(model.objects.values_list("page_ptr_id", flat=True))

    if not page_ids:
        return

    doomed_redirects = Redirect.objects.filter(redirect_page_id__in=page_ids)
    if doomed_redirects.exists():
        paths = ", ".join(sorted(doomed_redirects.values_list("old_path", flat=True)))
        raise RuntimeError(
            "Refusing to delete camp-report pages: these redirects point at "
            f"them and Redirect.redirect_page is CASCADE, so they would be "
            f"destroyed along with the pages — {paths}. Repoint each redirect "
            "at its surviving replacement page, then re-run this migration."
        )

    # Deleting via a base Page instance, not a specific subclass — Wagtail's
    # own Page.delete() re-fetches the base row for exactly this reason.
    for page in Page.objects.filter(pk__in=page_ids).order_by("-depth"):
        page.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_alter_homepage_body"),
        # The redirect guard reads this table, so its migrations must have run
        # first — on a fresh install nothing orders the two apps otherwise.
        ("wagtailredirects", "__first__"),
    ]

    operations = [
        migrations.RunPython(
            delete_camp_report_pages,
            migrations.RunPython.noop,
        ),
    ]
