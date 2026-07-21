"""The upload view — the structural enforcement of CLAUDE.md invariant #1.

Gated on ``accounts.can_upload_export`` (Plan 07's one custom permission,
held only by the Administrator group). The load-bearing line is
``request.upload_handlers = [MemoryFileUploadHandler(request)]``, set before
``request.POST``/``request.FILES`` is ever touched (Django only honours an
``upload_handlers`` override made before the multipart body is parsed — see
Django's file-upload docs). With **no** ``TemporaryFileUploadHandler`` in the
chain, a file over ``settings.FILE_UPLOAD_MAX_MEMORY_SIZE`` (Django's
default, 2.5 MB) simply never reaches ``request.FILES`` at all — Django's
``MemoryFileUploadHandler`` declines it and there is no fallback handler to
spool it to disk (see ``django.core.files.uploadhandler`` — the memory
handler's ``receive_data_chunk`` returns the raw chunk unconsumed and
``file_complete`` returns ``None`` when it never activated). That is a
*stronger* guarantee than the usual "delete the temp file afterwards"
pattern: an oversized export cannot touch disk even transiently. An
oversized upload surfaces to the admin as the form's ordinary "this field
is required" validation error (Django never populated ``request.FILES`` for
it) rather than a 500 — still a friendly failure, just not a distinct
message, since the view has no way to distinguish "too large" from "nothing
selected" once the memory handler has already declined the file.

The response is built entirely from ``apps.pipeline.ingest.IngestSummary`` —
per-date counts only. No parsed row ever reaches this view, so there is
nothing here that *could* leak into the rendered response.
"""

from __future__ import annotations

from zipfile import BadZipFile

from django.contrib.auth.decorators import permission_required
from django.core.files.uploadhandler import MemoryFileUploadHandler
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from apps.pipeline.forms import ExportUploadForm
from apps.pipeline.ingest import ingest_export
from apps.pipeline.parser_registry import ParserRegistry


def _template_for(request) -> str:
    """HTMX submits swap just the result fragment; a plain GET gets the full page."""
    if request.headers.get("HX-Request") == "true":
        return "pipeline/admin/upload_result.html"
    return "pipeline/admin/upload.html"


@require_http_methods(["GET", "POST"])
@permission_required("accounts.can_upload_export", raise_exception=True)
def upload_export(request):
    # Must be set before request.POST / request.FILES is accessed anywhere —
    # including inside ExportUploadForm(request.POST, request.FILES) below.
    request.upload_handlers = [MemoryFileUploadHandler(request)]

    summary = None
    warning = None
    error = None

    if request.method == "POST":
        form = ExportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["export_file"]
            format_key = form.cleaned_data["format_key"]
            try:
                workbook = load_workbook(uploaded, read_only=True, data_only=True)
                try:
                    suggested = ParserRegistry.sniff_all(workbook)
                finally:
                    workbook.close()
                if suggested and format_key not in suggested:
                    suggested_labels = ", ".join(
                        label
                        for key, label in ParserRegistry.choices()
                        if key in suggested
                    )
                    warning = (
                        f"This file looks more like: {suggested_labels}. "
                        "Proceeding with your selected format anyway."
                    )
                uploaded.seek(0)
                summary = ingest_export(
                    uploaded, parser_key=format_key, uploaded_by=request.user
                )
            except (InvalidFileException, BadZipFile):
                # BadZipFile: a non-.xlsx file (e.g. a PDF renamed or a plain
                # .xls) isn't a zip archive at all, so openpyxl never gets far
                # enough to raise its own InvalidFileException.
                error = (
                    "That file doesn't look like a valid .xlsx export. "
                    "Nothing was saved."
                )
            except KeyError:
                error = "Unknown export format selected. Nothing was saved."
        else:
            error = "; ".join(
                f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()
            )
    else:
        form = ExportUploadForm()

    context = {
        "form": form,
        "summary": summary,
        "warning": warning,
        "error": error,
    }
    return render(request, _template_for(request), context)
