"""The upload view — the structural enforcement of CLAUDE.md invariant #1.

Gated on ``accounts.can_upload_export`` (Plan 07's one custom permission,
held only by the Administrator group).

The load-bearing guarantee — that the upload runs through **only**
``MemoryFileUploadHandler``, with no ``TemporaryFileUploadHandler`` to spool
an oversized export to disk — is installed by
``apps.pipeline.middleware.MemoryOnlyUploadHandlerMiddleware``, **not** here.
It has to be: Django only honours an ``upload_handlers`` override made before
the multipart body is parsed, and ``CsrfViewMiddleware`` parses that body (to
read the CSRF token from ``request.POST``) *before* this view ever runs — so
setting the handler here raised ``AttributeError: You cannot set the upload
handlers after the upload has been processed``. See that middleware's
docstring for the full ordering argument and why the ``csrf_exempt`` view
split can't be used for a Wagtail admin view.

With no fallback handler in the chain, a file over
``settings.FILE_UPLOAD_MAX_MEMORY_SIZE`` (Django's default, 2.5 MB) never
reaches ``request.FILES`` at all — ``MemoryFileUploadHandler`` declines it and
nothing spools it to disk. An oversized upload therefore surfaces as the
form's ordinary "this field is required" validation error rather than a 500 —
the view can't distinguish "too large" from "nothing selected" once the memory
handler has declined the file, but neither is a crash and neither touches disk.

The response is built entirely from ``apps.pipeline.ingest.IngestSummary`` —
per-date counts only. No parsed row ever reaches this view, so there is
nothing here that *could* leak into the rendered response.
"""

from __future__ import annotations

import logging
from zipfile import BadZipFile

from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from apps.pipeline.forms import ExportUploadForm
from apps.pipeline.ingest import ingest_export
from apps.pipeline.parser_registry import ParserRegistry

logger = logging.getLogger(__name__)


def _template_for(request) -> str:
    """HTMX submits swap just the result fragment; a plain GET gets the full page."""
    if request.headers.get("HX-Request") == "true":
        return "pipeline/admin/upload_result.html"
    return "pipeline/admin/upload.html"


@require_http_methods(["GET", "POST"])
@permission_required("accounts.can_upload_export", raise_exception=True)
def upload_export(request):
    # The memory-only upload handler is installed by
    # apps.pipeline.middleware.MemoryOnlyUploadHandlerMiddleware, which runs
    # before CsrfViewMiddleware parses the body — it cannot be set here (the
    # body is already parsed by the time this view runs).
    summary = None
    warning = None
    error = None

    if request.method == "POST":
        form = ExportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["export_file"]
            format_key = form.cleaned_data["format_key"]
            # The not-really-an-.xlsx catch is scoped to opening/sniffing the
            # workbook only. ``ingest_export`` commits one transaction per
            # clinic-date and publishes a page per date, so an OSError-family
            # exception escaping *it* (TimeoutError, ConnectionError, ...)
            # must surface as a logged 500 — after a partial ingest, "Nothing
            # was saved" would be a lie.
            try:
                workbook = load_workbook(uploaded, read_only=True, data_only=True)
                try:
                    suggested = ParserRegistry.sniff_all(workbook)
                finally:
                    workbook.close()
            except (InvalidFileException, BadZipFile, OSError) as exc:
                # BadZipFile: a non-.xlsx file (e.g. a PDF renamed) isn't a
                # zip archive at all, so openpyxl never gets far enough to
                # raise its own InvalidFileException.
                # OSError: the clinic system's real .xls export is an OLE2
                # file that happens to embed a zip end-of-central-directory
                # record, so ``zipfile`` opens it and openpyxl only fails
                # later with ``OSError("File contains no valid workbook
                # part")`` — production 500 of 2026-07-22.
                logger.warning(
                    "Rejected export upload as not a readable .xlsx: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                error = (
                    "That file doesn't look like a valid .xlsx export. "
                    "If this is the clinic's .xls export, re-save it as "
                    ".xlsx first. Nothing was saved."
                )
            else:
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
