"""Upload intake: aggregate-and-discard.

``process_upload`` is the request-time boundary that privacy invariant #1 hangs
on. It takes an uploaded file, aggregates it entirely in memory, and returns the
de-identified result. It never calls ``.save()`` on the upload, never writes to
``MEDIA_ROOT``, and never creates a database row for a raw patient record — so
when the request ends there is nothing raw left behind.

Plan 08 wires this into a real Wagtail upload view with a parser registry; for
Plan 02 it exists so the privacy guardrail tests have a concrete boundary to
assert against.
"""

from __future__ import annotations

import io
from typing import BinaryIO

from apps.pipeline.aggregation import ClinicAggregate, aggregate_export


def process_upload(uploaded_file: BinaryIO) -> ClinicAggregate:
    """Aggregate an uploaded export in memory and discard the raw bytes.

    We copy the upload into an in-memory buffer rather than touching disk, run
    the aggregation, and let the buffer fall out of scope. The caller receives
    only the de-identified ``ClinicAggregate``.
    """
    buffer = io.BytesIO(uploaded_file.read())
    try:
        return aggregate_export(buffer)
    finally:
        buffer.close()
