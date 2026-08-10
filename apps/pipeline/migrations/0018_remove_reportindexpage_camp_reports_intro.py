"""Drop the ``/reports/`` camp-teaser intro field (Plan 21).

The teaser section it captioned went with ``CampReportPage`` — see
``core/0020``. Admin-entered copy, so the field's current value is lost;
that is intended, since it introduced a section that no longer exists. The
neighbouring ``daily_reports_intro`` (including the "figures exclude camps"
line the maintainer added in Plan 20) is untouched — it describes the daily
figures, not the retired teaser.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0017_alter_aicalllog_call_site"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="reportindexpage",
            name="camp_reports_intro",
        ),
    ]
