"""The upload form — an explicit format choice, per Plan 08's decision table.

The admin picks the export format from a dropdown rather than the system
silently guessing (``ParserRegistry.sniff_all`` only *suggests*, see
``apps.pipeline.admin_views``) — this avoids silently mis-parsing a
look-alike format.

``report_kind``/``camp_title`` (camp-upload flow, 2026-07-22): a maintainer
asked to be able to upload the same daily-export format for a medical camp
instead of the clinic's normal daily activity. This is a second, independent
axis from ``format_key`` — ``format_key`` picks the *parser* (the column
schema the file is read with); ``report_kind`` picks the *destination/meaning*
of the parsed data (the clinic's own day, vs. a named camp) — see
``apps.pipeline.models.IngestRun.report_kind`` for why the two must never be
conflated at the data layer. A camp upload additionally requires a camp
title, enforced in ``clean()`` rather than by making the field itself
required, since it's only required conditionally.
"""

from __future__ import annotations

from django import forms

from apps.pipeline.models import IngestRun
from apps.pipeline.parser_registry import ParserRegistry


class ExportUploadForm(forms.Form):
    export_file = forms.FileField(label="Daily export (.xls or .xlsx)")
    format_key = forms.ChoiceField(label="Export format")
    report_kind = forms.ChoiceField(
        label="This export is for",
        choices=IngestRun.REPORT_KIND_CHOICES,
        initial=IngestRun.KIND_DAILY,
        help_text="Same file format either way — choose 'Medical camp' when "
        "this export covers a camp rather than the clinic's normal daily "
        "activity.",
    )
    camp_title = forms.CharField(
        label="Camp title",
        required=False,
        help_text="Required when 'This export is for' is set to Medical "
        "camp — e.g. 'Free Medical Camp — Union Council X'.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built at request time (not import time) so a freshly-registered
        # parser is always reflected, and so tests can register a fake parser
        # and see it appear here.
        self.fields["format_key"].choices = ParserRegistry.choices()

    def clean(self):
        cleaned = super().clean()
        report_kind = cleaned.get("report_kind")
        camp_title = (cleaned.get("camp_title") or "").strip()
        if report_kind == IngestRun.KIND_CAMP and not camp_title:
            self.add_error("camp_title", "Enter the camp's title.")
        cleaned["camp_title"] = camp_title
        return cleaned
