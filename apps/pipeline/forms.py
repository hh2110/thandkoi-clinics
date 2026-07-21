"""The upload form — an explicit format choice, per Plan 08's decision table.

The admin picks the export format from a dropdown rather than the system
silently guessing (``ParserRegistry.sniff_all`` only *suggests*, see
``apps.pipeline.admin_views``) — this avoids silently mis-parsing a
look-alike format.
"""

from __future__ import annotations

from django import forms

from apps.pipeline.parser_registry import ParserRegistry


class ExportUploadForm(forms.Form):
    export_file = forms.FileField(label="Daily export (.xlsx)")
    format_key = forms.ChoiceField(label="Export format")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built at request time (not import time) so a freshly-registered
        # parser is always reflected, and so tests can register a fake parser
        # and see it appear here.
        self.fields["format_key"].choices = ParserRegistry.choices()
