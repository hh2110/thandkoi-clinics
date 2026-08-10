"""Take the camp-report pages out of the tree (Plan 21).

Runs straight after ``0020``, which dropped their tables — see that
migration's docstring for why the schema half goes first. What is left at
this point is three plain ``wagtailcore_page`` rows whose content type has
no model behind it, which is precisely the state Wagtail's own ``Page`` API
can delete correctly: ``treebeard``'s ``path``/``depth``/``numchild``
bookkeeping all lives on ``wagtailcore_page``, and there is no longer a
concrete child row for Django's cascade to miss.

**Imports the real ``wagtail.models.Page``, not ``apps.get_model``** — the
same exception ``pipeline/0016`` documents, for the same reason: a page is a
``treebeard`` node plus revisions, log entries and search-index hooks, and a
historical model is a plain ``Model`` with none of that behaviour.

Pages are found **by content type, never by hardcoded id**, so this is safe
on a fresh install (no such content type, no pages, no-op), on a re-run, and
on any database where someone already removed them by hand.

**The redirect trap.** ``Redirect.redirect_page`` is a ``CASCADE`` foreign
key, so deleting a page silently destroys every redirect pointing *at* it.
The two redirects preserving the retired camp URLs
(``/en/camp-reports/free-sugar-camp-report`` and
``/en/camp-reports/inauguration-report``) point at the surviving
``NewsletterPage`` replacements, not at anything deleted here, so the risk is
currently zero — this migration asserts that rather than trusting it, and
refuses to run if a redirect would be collateral. Repoint it and re-run.

Stale ``django_content_type`` rows for the two models are deliberately left
behind: Wagtail's page log entries outlive the pages they describe
(``PageLogEntry.page`` carries no database constraint — production has nine
such rows for this subtree) and still reference those content types.
``manage.py remove_stale_contenttypes`` can sweep them by hand later.

Irreversible, and marked so: the pages, their revisions and their draft
content are gone once this runs, and a no-op reverse that silently
"succeeded" would be a lie. Django raises ``IrreversibleError`` instead.
That is the plan's accepted rollback trade — both pages were already
unpublished and both URLs already redirect to live newsletter issues, so
nothing a reader can reach depends on them.
"""

from django.db import migrations

CAMP_PAGE_MODELS = ("campreportpage", "campreportindexpage")


def delete_camp_report_pages(apps, schema_editor):
    from wagtail.models import Page

    ContentType = apps.get_model("contenttypes", "ContentType")
    Redirect = apps.get_model("wagtailredirects", "Redirect")

    content_type_ids = list(
        ContentType.objects.filter(
            app_label="core", model__in=CAMP_PAGE_MODELS
        ).values_list("id", flat=True)
    )
    if not content_type_ids:
        return

    page_ids = list(
        Page.objects.filter(content_type_id__in=content_type_ids).values_list(
            "id", flat=True
        )
    )
    if not page_ids:
        return

    doomed_redirects = Redirect.objects.filter(redirect_page_id__in=page_ids)
    if doomed_redirects.exists():
        paths = ", ".join(sorted(doomed_redirects.values_list("old_path", flat=True)))
        raise RuntimeError(
            "Refusing to delete camp-report pages: these redirects point at "
            "them, and Redirect.redirect_page is CASCADE, so they would be "
            f"destroyed along with the pages — {paths}. Repoint each redirect "
            "at its surviving replacement page, then re-run this migration."
        )

    # Deepest first, so a child is never orphaned by its parent going away,
    # and each delete() decrements exactly one parent's numchild. Base Page
    # instances, not specific subclasses — Wagtail's own delete path re-fetches
    # the base row for exactly this reason.
    for page in Page.objects.filter(pk__in=page_ids).order_by("-depth"):
        page.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_delete_camp_report_models"),
        # Both tables this migration reads must exist before it runs; on a
        # fresh install nothing else orders these apps against core.
        ("contenttypes", "__first__"),
        ("wagtailredirects", "__first__"),
    ]

    operations = [
        # No reverse_code: deleted pages cannot be brought back, so Django
        # refuses to unapply rather than pretending. See the docstring.
        migrations.RunPython(delete_camp_report_pages),
    ]
