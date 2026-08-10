"""Drop ``CampReportPage``/``CampReportIndexPage`` (Plan 21).

Runs strictly after ``0020``, which takes the page rows out of the tree —
see that migration's docstring for why the order matters and why it is
irreversible.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_delete_camp_report_pages"),
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
