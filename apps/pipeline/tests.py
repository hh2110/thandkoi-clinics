"""Privacy-invariant guardrail tests (Plan 02).

These are plain, deterministic Python assertions about what our code *does* —
never a call to a real model, never a judgement of model output quality. Each
maps to a non-negotiable invariant in CLAUDE.md:

* ``test_upload_never_persists_raw_phi``     → invariant #1 (never persist PHI)
* ``test_ai_payload_contains_only_aggregates`` → invariant #2 (AI never sees PHI)
* ``test_published_report_numbers_are_deterministic`` → invariant #3 (numbers
  computed in Python, not the model)

The real Anthropic client is impossible to construct here — see the autouse
``_forbid_real_anthropic`` guard in the project ``conftest.py``.
"""

from __future__ import annotations

import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.pipeline import ai
from apps.pipeline.aggregation import aggregate_export
from apps.pipeline.ai import PATIENT_IDENTIFYING_COLUMNS, draft_newsletter_prose
from apps.pipeline.intake import process_upload
from apps.pipeline.rendering import render_daily_report

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# A fixture export that includes real-looking direct identifiers alongside the
# two columns we actually aggregate on. Nothing in the "identifying" columns may
# ever survive aggregation or reach a model.
EXPORT_HEADER = ["patient_name", "mrn", "phone", "gender", "diagnosis"]
EXPORT_ROWS = [
    ["Fatima Bibi", "MRN-001", "0300-1112222", "Female", "Hypertension"],
    ["Ahmed Khan", "MRN-002", "0301-3334444", "Male", "Diabetes"],
    ["Zainab Ali", "MRN-003", "0302-5556666", "Female", "Hypertension"],
]
# Identifier substrings that must never appear downstream of aggregation.
RAW_IDENTIFIERS = [
    "fatima",
    "bibi",
    "ahmed",
    "khan",
    "zainab",
    "ali",
    "mrn-001",
    "mrn-002",
    "mrn-003",
    "0300-1112222",
    "0301-3334444",
    "0302-5556666",
]


def _build_export_xlsx() -> bytes:
    """Build an in-memory .xlsx export with PHI columns; return its bytes."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(EXPORT_HEADER)
    for row in EXPORT_ROWS:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# Deterministic expected aggregate, computed here in the test independently of
# the production aggregation code.
EXPECTED_TOTAL = len(EXPORT_ROWS)
EXPECTED_BY_GENDER = {"female": 2, "male": 1}
EXPECTED_BY_DIAGNOSIS = {"diabetes": 1, "hypertension": 2}


def test_upload_never_persists_raw_phi(
    db, django_assert_num_queries, settings, tmp_path
):
    """Invariant #1: an uploaded export leaves no file on disk and no DB row."""
    settings.MEDIA_ROOT = str(tmp_path)
    upload = SimpleUploadedFile(
        "daily-export.xlsx", _build_export_xlsx(), content_type=XLSX_CONTENT_TYPE
    )

    # Aggregating must not touch the database at all — no raw patient row.
    with django_assert_num_queries(0):
        aggregate = process_upload(upload)

    # Nothing was written to media storage — the raw upload is discarded.
    assert list(tmp_path.iterdir()) == []

    # The aggregate is correct...
    assert aggregate.total_patients == EXPECTED_TOTAL
    assert aggregate.by_gender == EXPECTED_BY_GENDER
    assert aggregate.by_diagnosis == EXPECTED_BY_DIAGNOSIS

    # ...and carries no direct identifier from the raw rows.
    serialised = json.dumps(aggregate.as_dict()).lower()
    for identifier in RAW_IDENTIFIERS:
        assert identifier not in serialised
    for column in PATIENT_IDENTIFYING_COLUMNS:
        assert column not in serialised


def test_ai_payload_contains_only_aggregates(mock_anthropic_client):
    """Invariant #2: the payload sent to the model holds only aggregate counts."""
    aggregate = aggregate_export(io.BytesIO(_build_export_xlsx()))

    prose = draft_newsletter_prose(aggregate, mock_anthropic_client)
    assert prose  # the stub returned its canned text

    # Inspect exactly what our code sent to the (mocked) client.
    assert len(mock_anthropic_client.calls) == 1
    sent = json.dumps(mock_anthropic_client.calls[0]).lower()

    # No raw identifier value and no identifying column name crossed the wire.
    for identifier in RAW_IDENTIFIERS:
        assert identifier not in sent
    for column in PATIENT_IDENTIFYING_COLUMNS:
        assert column not in sent

    # The de-identified aggregates DID cross — that's what the model works from.
    assert str(EXPECTED_TOTAL) in sent
    assert "hypertension" in sent
    assert "by_gender" in sent


def test_published_report_numbers_are_deterministic(mock_anthropic_client):
    """Invariant #3: published figures come from Python, not the model's prose."""
    aggregate = aggregate_export(io.BytesIO(_build_export_xlsx()))

    # The stub prose deliberately contains a bogus number ("9999").
    prose = draft_newsletter_prose(aggregate, mock_anthropic_client)
    assert "9999" in prose

    html = render_daily_report(aggregate, prose)

    # The figures the reader sees are the deterministic, code-computed numbers.
    assert f"Patients seen: <strong>{EXPECTED_TOTAL}</strong>" in html
    assert "hypertension: <strong>2</strong>" in html
    assert "female: <strong>2</strong>" in html

    # The bogus number from the model appears only inside the narrative block,
    # never in the figures block — numbers came from code, not the mock.
    figures_block, _, narrative_block = html.partition('data-role="narrative"')
    assert "9999" not in figures_block
    assert "9999" in narrative_block

    # Byte-for-byte: re-aggregating the same export yields the same figures, and
    # those figures equal the values computed independently in this test.
    reaggregate = aggregate_export(io.BytesIO(_build_export_xlsx()))
    assert reaggregate == aggregate
    assert aggregate.total_patients == EXPECTED_TOTAL
    assert aggregate.by_diagnosis == EXPECTED_BY_DIAGNOSIS


def test_real_anthropic_client_is_forbidden_in_tests():
    """The suite can never construct a real client or reach the live API.

    Production code obtains the client via the module (``ai.get_anthropic_client()``);
    the autouse conftest guard patches that entry point to raise.
    """
    with pytest.raises(RuntimeError, match="never be built in tests"):
        ai.get_anthropic_client()
