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

import datetime
import io
import json
import re
import zipfile
from types import SimpleNamespace

import pytest
import xlwt
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import (
    MemoryFileUploadHandler,
    TemporaryFileUploadHandler,
)
from django.core.management import call_command
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.core.factories import HomePageFactory
from apps.pipeline import ai
from apps.pipeline.aggregation import aggregate_export
from apps.pipeline.ai import PATIENT_IDENTIFYING_COLUMNS, draft_newsletter_prose
from apps.pipeline.factories import DailyReportPageFactory, ReportIndexPageFactory
from apps.pipeline.ingest import (
    persist_parsed_export,
    recompute_daily_aggregate,
)
from apps.pipeline.intake import process_upload
from apps.pipeline.middleware import MemoryOnlyUploadHandlerMiddleware
from apps.pipeline.models import (
    DailyAggregate,
    DailyReportPage,
    DeidentifiedVisit,
    IngestRun,
)
from apps.pipeline.parser_clinic_v1 import ClinicDailyExportV1Parser
from apps.pipeline.parser_registry import (
    ParserRegistry,
    age_band_for,
    content_hash_for_rows,
    diagnosis_category_for,
    normalise_sex,
)
from apps.pipeline.parser_tkc_daily_v1 import TkcDailyActivityV1Parser
from apps.pipeline.rendering import render_daily_report
from apps.pipeline.report_publishing import publish_daily_report
from apps.pipeline.xls_compat import convert_xls_to_xlsx, looks_like_xls

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


def test_template_comment_does_not_leak_into_output(mock_anthropic_client):
    """The template's documentation comment must not render as visible text.

    Django's ``{# ... #}`` hash-comment syntax is single-line only (its lexer
    regex is not DOTALL), so a multi-line hash comment leaks into the HTML as
    literal text. The template uses a ``{% comment %}`` block instead; this
    guards against a regression back to the leaking form.
    """
    aggregate = aggregate_export(io.BytesIO(_build_export_xlsx()))
    prose = draft_newsletter_prose(aggregate, mock_anthropic_client)

    html = render_daily_report(aggregate, prose)

    # Distinctive phrases from the template's internal doc comment — none should
    # ever reach the rendered page.
    assert "Daily clinic report" not in html
    assert "privacy invariant #3" not in html
    assert "rendering.py" not in html


def test_real_anthropic_client_is_forbidden_in_tests():
    """The suite can never construct a real client or reach the live API.

    Production code obtains the client via the module (``ai.get_anthropic_client()``);
    the autouse conftest guard patches that entry point to raise.
    """
    with pytest.raises(RuntimeError, match="never be built in tests"):
        ai.get_anthropic_client()


# =============================================================================
# Plan 08 — parser registry, ingest, daily report auto-publish, upload view.
#
# The fixture below deliberately carries real-looking direct identifiers in
# columns the ClinicDailyExportV1Parser is documented to drop (patient_name,
# father_name, mrn, phone, address, dob) alongside the clinical columns it
# actually maps into a DeidentifiedVisit row. Every guardrail test below
# proves those identifier columns — and the raw free-text diagnoses — never
# survive past the parser boundary.
#
# ClinicDailyExportV1Parser is no longer registered/selectable (decision,
# 2026-07-22 — see apps.py and the parser's own module docstring): the real
# ``tkc_daily_activity_v1`` parser is what production uploads use now. This
# fixture and parser class are still used directly below (constructed and
# called without going through ParserRegistry) for two purposes: the
# parser's own privacy-guardrail tests, and — via the ``_ingest_clinic_v1``
# helper — as convenient, already-built test data for the generic
# ingest/aggregate/publish machinery tests that follow, which aren't about
# this specific format. Tests that exercise the real upload *view* (which
# only accepts a registered ``format_key``) use the real
# ``tkc_daily_activity_v1`` fixture instead — see ``_build_tkc_daily_xls``.
# =============================================================================


def test_clinic_v1_format_is_not_registered_by_default():
    """Pins the negative behavior this decision introduces: the provisional
    format is gone from the dropdown and no longer resolvable — a future
    accidental re-registration (e.g. a bad merge) would otherwise ship
    silently, since nothing else in the suite asserts its absence."""
    assert "clinic_daily_export_v1" not in dict(ParserRegistry.choices())
    with pytest.raises(KeyError):
        ParserRegistry.get("clinic_daily_export_v1")


def test_clinic_v1_parser_can_still_be_registered_explicitly():
    """The module's own docstring says register() is kept so "a test (or a
    future need) can still register it explicitly" — exercise that claim
    directly, since nothing else in the suite calls register() at all."""
    from apps.pipeline import parser_clinic_v1

    assert "clinic_daily_export_v1" not in ParserRegistry._parsers
    try:
        parser_clinic_v1.register()
        assert isinstance(
            ParserRegistry.get("clinic_daily_export_v1"),
            parser_clinic_v1.ClinicDailyExportV1Parser,
        )
    finally:
        # ParserRegistry._parsers is a shared class-level dict, not reset
        # per-test — leaving this registered would silently make the format
        # selectable again for every test that runs after this one.
        ParserRegistry._parsers.pop("clinic_daily_export_v1", None)


CLINIC_V1_HEADER = [
    "patient_name",
    "father_name",
    "mrn",
    "phone",
    "address",
    "dob",
    "visit_date",
    "department",
    "gender",
    "location",
    "diagnosis",
    "patient_type",
    "payment_type",
]

CLINIC_V1_VISIT_DATE = datetime.date(2026, 7, 20)

# (identifiers..., dob, department, gender, location, diagnosis, patient_type,
# payment_type)
CLINIC_V1_ROWS = [
    [
        "Fatima Bibi",
        "Abdul Rahman",
        "MRN-100",
        "0300-9998887",
        "House 12, Street 5, Thandkoi Bazaar",
        datetime.date(2020, 1, 1),
        CLINIC_V1_VISIT_DATE,
        "General Medicine",
        "Female",
        "Thandkoi",
        "high bp",
        "New",
        "Zakat",
    ],
    [
        "Ahmed Raza",
        "Sher Ali",
        "MRN-101",
        "0301-1112223",
        "House 3, Main Road, Yaqubi",
        datetime.date(1990, 5, 5),
        CLINIC_V1_VISIT_DATE,
        "General Medicine",
        "Male",
        "Yaqubi",
        "sugar",
        "Follow-up",
        "Paid",
    ],
    [
        "Zainab Gul",
        "Wali Muhammad",
        "MRN-102",
        "0302-4445556",
        "House 9, Bazaar Road, Thandkoi",
        datetime.date(1960, 3, 3),
        CLINIC_V1_VISIT_DATE,
        "Cardiology",
        "Female",
        "Thandkoi",
        "chest pain",
        "New",
        "Zakat",
    ],
    [
        "Bilal Khan",
        "Noor Zaman",
        "MRN-103",
        "0303-7778889",
        "House 21, Canal Road, Thandkoi",
        None,
        CLINIC_V1_VISIT_DATE,
        "",
        "",
        "",
        "xyz-unusual-complaint",
        "",
        "",
    ],
]

# Every identifier value above — none may survive past the parser boundary.
CLINIC_V1_RAW_IDENTIFIERS = [
    "fatima bibi",
    "ahmed raza",
    "zainab gul",
    "bilal khan",
    "abdul rahman",
    "sher ali",
    "wali muhammad",
    "noor zaman",
    "mrn-100",
    "mrn-101",
    "mrn-102",
    "mrn-103",
    "0300-9998887",
    "0301-1112223",
    "0302-4445556",
    "0303-7778889",
    "house 12, street 5, thandkoi bazaar",
    "house 3, main road, yaqubi",
    "house 9, bazaar road, thandkoi",
    "house 21, canal road, thandkoi",
    "2020-01-01",
    "1990-05-05",
    "1960-03-03",
]
# The raw diagnosis free text — must never survive; only the mapped fixed
# category may appear (checked separately, since e.g. "cardiac" the category
# is a substring-safe, deliberately different string from "chest pain").
CLINIC_V1_RAW_DIAGNOSES = ["high bp", "sugar", "chest pain", "xyz-unusual-complaint"]

EXPECTED_TOTAL_VISITS = 4
EXPECTED_BY_DEPARTMENT = {
    "General Medicine": 2,
    "Cardiology": 1,
    "unspecified": 1,
}
EXPECTED_BY_DIAGNOSIS_CATEGORY = {
    "hypertension": 1,
    "diabetes": 1,
    "cardiac": 1,
    "other": 1,
}
EXPECTED_BY_AGE_BAND = {"5-12": 1, "18-40": 1, "61+": 1, "unknown": 1}


def _build_clinic_v1_xlsx(rows=None) -> bytes:
    """Build an in-memory ``clinic_daily_export_v1``-shaped .xlsx; return its bytes."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(CLINIC_V1_HEADER)
    for row in CLINIC_V1_ROWS if rows is None else rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _ingest_clinic_v1(rows=None, *, uploaded_by=None):
    """Parse + persist the clinic_v1 fixture, bypassing ``ParserRegistry``.

    ``ClinicDailyExportV1Parser`` is no longer registered (see apps.py), so
    ``ingest_export(..., parser_key="clinic_daily_export_v1", ...)`` would
    raise ``KeyError``. The tests using this helper aren't testing that
    format specifically — they use its rich, already-built fixture as
    convenient data for generic ingest/aggregate/publish machinery — so this
    calls the parser directly and hands the parsed rows to
    ``persist_parsed_export`` (the same thing ``ingest_export`` does
    internally, minus the registry lookup).
    """
    buffer = io.BytesIO(_build_clinic_v1_xlsx(rows=rows))
    parsed = ClinicDailyExportV1Parser().parse(buffer)
    return persist_parsed_export(
        parsed, parser_key="clinic_daily_export_v1", uploaded_by=uploaded_by
    )


def _administrator_user(django_user_model, username="administrator"):
    user = django_user_model.objects.create_user(username=username, password="x")  # noqa: S106
    user.groups.add(Group.objects.get(name="Administrator"))
    return user


@pytest.fixture
def home_page(db):
    """A HomePage so ``publish_daily_report``'s ``ReportIndexPage`` auto-create
    (``apps.pipeline.report_publishing._get_or_create_report_index``) has
    somewhere to attach to — every test that calls ``ingest_export``/
    ``publish_daily_report`` needs one to exist first, same as a real site
    (mirrors ``apps.core.tests.home_page``'s role, scoped to this module)."""
    return HomePageFactory()


# --- Parser registry unit tests ---------------------------------------------


def test_age_band_for_bands_by_dob_relative_to_visit_date():
    on = datetime.date(2026, 7, 20)
    assert age_band_for(dob=datetime.date(2020, 1, 1), age_years=None, on=on) == "5-12"
    assert age_band_for(dob=datetime.date(1990, 5, 5), age_years=None, on=on) == "18-40"
    assert age_band_for(dob=datetime.date(1960, 3, 3), age_years=None, on=on) == "61+"
    assert age_band_for(dob=None, age_years=None, on=on) == "unknown"


def test_normalise_sex_maps_free_text_to_fixed_set():
    assert normalise_sex("Female") == DeidentifiedVisit.SEX_FEMALE
    assert normalise_sex("m") == DeidentifiedVisit.SEX_MALE
    assert normalise_sex("nonbinary") == DeidentifiedVisit.SEX_OTHER_UNKNOWN
    assert normalise_sex(None) == DeidentifiedVisit.SEX_OTHER_UNKNOWN


def test_diagnosis_category_for_maps_keywords_and_falls_back_to_other():
    assert diagnosis_category_for("high bp") == DeidentifiedVisit.DIAGNOSIS_HYPERTENSION
    assert diagnosis_category_for("sugar") == DeidentifiedVisit.DIAGNOSIS_DIABETES
    assert diagnosis_category_for("chest pain") == DeidentifiedVisit.DIAGNOSIS_CARDIAC
    assert (
        diagnosis_category_for("xyz-unusual-complaint")
        == DeidentifiedVisit.DIAGNOSIS_OTHER
    )
    assert diagnosis_category_for(None) == DeidentifiedVisit.DIAGNOSIS_OTHER


def test_content_hash_for_rows_is_order_independent_and_change_sensitive():
    parsed_a = ClinicDailyExportV1Parser().parse(io.BytesIO(_build_clinic_v1_xlsx()))
    parsed_b = ClinicDailyExportV1Parser().parse(
        io.BytesIO(_build_clinic_v1_xlsx(rows=list(reversed(CLINIC_V1_ROWS))))
    )
    assert content_hash_for_rows(parsed_a.rows) == content_hash_for_rows(parsed_b.rows)

    changed_rows = [list(row) for row in CLINIC_V1_ROWS]
    changed_rows[0][8] = "Male"  # flip row 1's gender
    parsed_changed = ClinicDailyExportV1Parser().parse(
        io.BytesIO(_build_clinic_v1_xlsx(rows=changed_rows))
    )
    assert content_hash_for_rows(parsed_a.rows) != content_hash_for_rows(
        parsed_changed.rows
    )


def test_clinic_v1_parser_sniffs_its_own_required_columns():
    workbook = Workbook()
    workbook.active.append(CLINIC_V1_HEADER)
    assert ClinicDailyExportV1Parser().sniff(workbook) is True

    unrelated = Workbook()
    unrelated.active.append(["some_other_column"])
    assert ClinicDailyExportV1Parser().sniff(unrelated) is False


# --- Privacy guardrail: parser never carries identifiers past its boundary --


def test_parser_never_produces_a_row_with_a_raw_identifier_or_diagnosis(db):
    """Invariant #1, at the parser boundary: ParsedVisitRow structurally has no
    identifier field, and its serialised values never contain a raw one."""
    parsed = ClinicDailyExportV1Parser().parse(io.BytesIO(_build_clinic_v1_xlsx()))
    assert len(parsed.rows) == EXPECTED_TOTAL_VISITS

    serialised = json.dumps(
        [
            {
                "visit_date": row.visit_date.isoformat(),
                "department": row.department,
                "age_band": row.age_band,
                "sex": row.sex,
                "location": row.location,
                "diagnosis_category": row.diagnosis_category,
                "is_new_patient": row.is_new_patient,
                "is_zakat_beneficiary": row.is_zakat_beneficiary,
            }
            for row in parsed.rows
        ]
    ).lower()
    for identifier in CLINIC_V1_RAW_IDENTIFIERS:
        assert identifier not in serialised
    for raw_diagnosis in CLINIC_V1_RAW_DIAGNOSES:
        assert raw_diagnosis not in serialised
    # Coarse location IS expected to survive (maintainer decision, PR #15).
    assert "thandkoi" in serialised


# --- Privacy guardrail: end-to-end ingest never persists PHI ---------------


def test_ingest_never_persists_raw_phi_and_computes_correct_aggregate(home_page):
    """Invariant #1 end-to-end: parse → persist → the DB holds only
    de-identified rows and aggregates; invariant #3: the aggregate is exactly
    the deterministic recomputation from the fixture."""
    summary = _ingest_clinic_v1()
    assert summary.total_rows == EXPECTED_TOTAL_VISITS
    assert summary.results[0].status == IngestRun.STATUS_CREATED

    # No raw identifier or raw diagnosis text anywhere in what got persisted.
    visits = DeidentifiedVisit.objects.filter(visit_date=CLINIC_V1_VISIT_DATE)
    aggregate = DailyAggregate.objects.get(clinic_date=CLINIC_V1_VISIT_DATE)
    serialised = json.dumps(
        [
            {
                "department": v.department,
                "age_band": v.age_band,
                "sex": v.sex,
                "location": v.location,
                "diagnosis_category": v.diagnosis_category,
            }
            for v in visits
        ]
        + [aggregate.as_dict()]
    ).lower()
    for identifier in CLINIC_V1_RAW_IDENTIFIERS:
        assert identifier not in serialised
    for raw_diagnosis in CLINIC_V1_RAW_DIAGNOSES:
        assert raw_diagnosis not in serialised
    for column in PATIENT_IDENTIFYING_COLUMNS:
        assert column not in serialised

    # Only fixed diagnosis categories, never free text.
    fixed_categories = {
        choice[0] for choice in DeidentifiedVisit.DIAGNOSIS_CATEGORY_CHOICES
    }
    assert set(visits.values_list("diagnosis_category", flat=True)) <= fixed_categories

    # Invariant #3: the aggregate matches an independent, deterministic recompute.
    assert aggregate.total_visits == EXPECTED_TOTAL_VISITS
    assert aggregate.category_counts["by_department"] == EXPECTED_BY_DEPARTMENT
    assert (
        aggregate.category_counts["by_diagnosis_category"]
        == EXPECTED_BY_DIAGNOSIS_CATEGORY
    )
    assert aggregate.category_counts["by_age_band"] == EXPECTED_BY_AGE_BAND
    assert aggregate.new_patients == 2
    assert aggregate.follow_up_patients == 1
    assert aggregate.unknown_patient_type_patients == 1
    assert aggregate.zakat_beneficiary_patients == 2
    assert aggregate.paying_patients == 1
    assert aggregate.unknown_payment_type_patients == 1

    # Recomputing from the row table byte-for-byte reproduces the same aggregate
    # (the derived-cache contract) — invariant #3, and the "recompute" contract.
    recomputed = recompute_daily_aggregate(CLINIC_V1_VISIT_DATE)
    assert recomputed.as_dict() == aggregate.as_dict()


def test_upload_view_never_writes_a_file_to_disk(
    client, home_page, settings, tmp_path, django_user_model
):
    """Invariant #1 through the real admin view: MemoryFileUploadHandler means
    the upload never touches MEDIA_ROOT, mirroring the Plan 02 placeholder
    test but exercised through the real permission-gated view.

    Uses the real, selectable ``tkc_daily_activity_v1`` format —
    ``clinic_daily_export_v1`` (used above as fixture data only) is no
    longer a valid ``format_key`` choice, see apps.py.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    client.force_login(_administrator_user(django_user_model))

    response = client.post(
        reverse("pipeline:upload_export"),
        data={
            "export_file": SimpleUploadedFile(
                "TKC JULY 8TH STAT.xls",
                _build_tkc_daily_xls(),
                content_type="application/vnd.ms-excel",
            ),
            "format_key": "tkc_daily_activity_v1",
        },
    )
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
    assert DailyAggregate.objects.filter(clinic_date=TKC_VISIT_DATE).exists()


def _build_ole2_with_embedded_zip() -> bytes:
    """Mimic the clinic system's real .xls export, without any PHI.

    The production file (regression of 2026-07-22) is an OLE2 compound
    document that happens to contain an embedded zip end-of-central-directory
    record, so ``zipfile`` opens it as an archive and openpyxl fails past the
    ``BadZipFile`` guard with ``OSError("File contains no valid workbook
    part")``. Reproduce that shape: OLE2 magic bytes followed by a zip whose
    only entry is a content-types manifest — no workbook part.
    """
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
    ole2_magic = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    return ole2_magic + b"\x00" * 64 + inner.getvalue()


def test_upload_view_rejects_ole2_xls_with_embedded_zip_gracefully(
    client, home_page, django_user_model, caplog
):
    """Regression for the production 500 of 2026-07-22: the clinic's real
    ``.xls`` export slipped past the ``BadZipFile`` catch (its OLE2 body
    embeds a zip signature) and openpyxl's ``OSError`` went unhandled. The
    view must answer with its ordinary "not a valid .xlsx" error — a 200,
    nothing ingested — while logging the underlying exception so a recurring
    failure stays visible to the operator."""
    client.force_login(_administrator_user(django_user_model))

    with caplog.at_level("WARNING", logger="apps.pipeline.admin_views"):
        response = client.post(
            reverse("pipeline:upload_export"),
            data={
                "export_file": SimpleUploadedFile(
                    "TKC JULY 8TH STAT.xls",
                    _build_ole2_with_embedded_zip(),
                    content_type="application/vnd.ms-excel",
                ),
                "format_key": "tkc_daily_activity_v1",
            },
        )

    assert response.status_code == 200
    # The swallowed exception is still diagnosable from the logs. (With .xls
    # conversion in place, the OLE2 magic routes this payload to xlrd, which
    # rejects it as not a real BIFF workbook — the graceful path either way.)
    assert any(
        "Rejected export upload" in record.getMessage() for record in caplog.records
    )
    # The apostrophe in "doesn't" is HTML-escaped in the rendered page, so
    # assert on the fragment after it.
    assert "look like a valid Excel export" in response.content.decode()
    assert not IngestRun.objects.exists()
    assert not DailyAggregate.objects.exists()


def _build_tkc_daily_xls(
    *, period: str = "Period: 08 Jul 2026 to 08 Jul 2026"
) -> bytes:
    """A synthetic legacy ``.xls`` mirroring the clinic system's real layout.

    Same shape as the 2026-07-22 sample: banner row, ``Period:`` row, blank
    row, header row, then data rows — with the same fake identifiers as
    ``EXPORT_ROWS`` so the ``RAW_IDENTIFIERS`` guard applies. Built with
    xlwt (dev dependency) because openpyxl cannot write BIFF.
    """
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Patient Report")
    sheet.write(0, 0, "THE THANDKOI CLINICS — Daily Activity Report")
    sheet.write(1, 0, period)
    header = [
        "S#",
        "MR #",
        "Patient Name",
        "Father's / Husband's Name",
        "Date of Birth",
        "Sex",
        "Address",
        "Status",
        "Presenting Complaints",
        "Provisional Diagnosis",
    ]
    for column, name in enumerate(header):
        sheet.write(3, column, name)
    data = [
        # (mrn, name, dob, sex, status, diagnosis)
        ("MRN-001", "Fatima Bibi", "05-Mar-1988", "Female", "Zakat", "Hypertension"),
        ("MRN-002", "Ahmed Khan", "", "Male", "Regular", "Diabetes"),
        ("MRN-003", "Zainab Ali", "20-Dec-2015", "Female", "", "Hypertension"),
    ]
    for offset, (mrn, name, dob, sex, status, diagnosis) in enumerate(data):
        row = 4 + offset
        sheet.write(row, 0, offset + 1)
        sheet.write(row, 1, mrn)
        sheet.write(row, 2, name)
        sheet.write(row, 3, "Someone Else")
        sheet.write(row, 4, dob)
        sheet.write(row, 5, sex)
        sheet.write(row, 6, "House 12, Street 3, Thandkoi")
        sheet.write(row, 7, status)
        sheet.write(row, 8, "Headache")
        sheet.write(row, 9, diagnosis)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


TKC_VISIT_DATE = datetime.date(2026, 7, 8)


def test_upload_view_ingests_real_format_xls(
    client, home_page, settings, tmp_path, django_user_model
):
    """The clinic system's native ``.xls`` uploads end to end: detected by
    magic bytes, converted to ``.xlsx`` in memory, sniffed as
    ``tkc_daily_activity_v1``, parsed with the visit date taken from the
    ``Period:`` banner — and, per invariant #1, without the raw upload or
    its conversion ever touching disk."""
    settings.MEDIA_ROOT = str(tmp_path)
    client.force_login(_administrator_user(django_user_model))

    response = client.post(
        reverse("pipeline:upload_export"),
        data={
            "export_file": SimpleUploadedFile(
                "TKC JULY 8TH STAT.xls",
                _build_tkc_daily_xls(),
                content_type="application/vnd.ms-excel",
            ),
            "format_key": "tkc_daily_activity_v1",
        },
    )

    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []

    aggregate = DailyAggregate.objects.get(clinic_date=TKC_VISIT_DATE)
    assert aggregate.total_visits == 3
    assert aggregate.female_patients == 2
    assert aggregate.male_patients == 1

    visits = DeidentifiedVisit.objects.filter(visit_date=TKC_VISIT_DATE)
    assert visits.count() == 3
    # Status column mapped: Zakat → True, Regular → False, blank → unknown.
    assert visits.filter(is_zakat_beneficiary=True).count() == 1
    assert visits.filter(is_zakat_beneficiary=False).count() == 1
    assert visits.filter(is_zakat_beneficiary=None).count() == 1

    # No direct identifier from the .xls survived into the response. Short
    # tokens ("ali", "khan") are excluded — they false-positive as substrings
    # of ordinary HTML ("align"); the distinctive names and MRNs suffice.
    rendered = response.content.decode().lower()
    for identifier in (i for i in RAW_IDENTIFIERS if len(i) > 4):
        assert identifier not in rendered


def test_upload_view_rejects_multi_day_xls_with_clear_error(
    client, home_page, django_user_model
):
    """A multi-day ``Period:`` range can't attribute rows to a clinic date;
    the parser raises ``ExportParseError`` (before anything is persisted)
    and the view shows its message instead of a 500."""
    client.force_login(_administrator_user(django_user_model))

    response = client.post(
        reverse("pipeline:upload_export"),
        data={
            "export_file": SimpleUploadedFile(
                "TKC WEEKLY STAT.xls",
                _build_tkc_daily_xls(period="Period: 06 Jul 2026 to 12 Jul 2026"),
                content_type="application/vnd.ms-excel",
            ),
            "format_key": "tkc_daily_activity_v1",
        },
    )

    assert response.status_code == 200
    assert "Multi-day exports" in response.content.decode()
    assert not IngestRun.objects.exists()
    assert not DailyAggregate.objects.exists()


def _build_tkc_daily_workbook_with_wrapped_text_continuation_rows() -> bytes:
    """Reproduces the exact phantom-row shape found in the clinic system's
    real 2026-07-20 export (a production bug: 7 real patients were parsed and
    published as 17).

    The clinic system's report writer spills a free-text column's wrapped
    content (observed on ``Presenting Complaints``) onto an extra physical
    row when it has multiple lines. That continuation row has every cell
    ``None`` except the one free-text column — no ``MR #`` — so the old
    "is this row entirely blank" check didn't catch it and it was counted as
    its own visit. A wholly blank leftover row (stray ``.xls`` "used range"
    padding) is included too, since the old check *did* correctly skip that
    one — this fixture proves the fix keeps that case working as well as
    fixing the continuation-row case. No real patient data: names/MRNs here
    are fabricated placeholders, not the real file's values.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Patient Report"
    sheet.append(["THE THANDKOI CLINICS — Daily Activity Report"])
    sheet.append(["Period: 20 Jul 2026 to 20 Jul 2026"])
    sheet.append([])
    header = [
        "S#",
        "MR #",
        "Patient Name",
        "Father's / Husband's Name",
        "Date of Birth",
        "Sex",
        "Address",
        "Status",
        "Presenting Complaints",
        "Provisional Diagnosis",
    ]
    sheet.append(header)
    # A genuine visit, whose "Presenting Complaints" text wraps onto a second
    # physical row that carries no MR # (or anything else).
    sheet.append(
        [
            1,
            "MRN-201",
            "Placeholder One",
            "Someone",
            "05-Mar-1988",
            "Female",
            "Addr",
            "Zakat",
            "first line of complaint",
            "",
        ]
    )
    sheet.append(
        [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "second line of complaint (wrapped, no MR #)",
            None,
        ]
    )
    # Another genuine visit, followed by a wholly blank leftover row.
    sheet.append(
        [
            2,
            "MRN-202",
            "Placeholder Two",
            "Someone Else",
            "",
            "Male",
            "Addr",
            "Regular",
            "another complaint",
            "",
        ]
    )
    sheet.append([None] * 10)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_tkc_daily_parser_skips_wrapped_text_continuation_rows_without_mr_number():
    """Regression for the 2026-07-20 production bug: a real 7-patient export
    was parsed and published as 17. Root cause: a free-text column's wrapped
    content spills onto an extra physical row carrying no ``MR #``; the old
    "all cells are None" blank check didn't catch it (one cell held text) so
    each continuation row was counted as its own phantom visit. The fix
    requires a non-blank ``MR #`` for a row to count as a visit."""
    parsed = TkcDailyActivityV1Parser().parse(
        io.BytesIO(_build_tkc_daily_workbook_with_wrapped_text_continuation_rows())
    )
    assert len(parsed.rows) == 2


def test_xls_conversion_preserves_date_cells():
    """A real Excel date cell in a ``.xls`` comes out of the in-memory
    conversion as a ``datetime`` — what openpyxl would give a parser for a
    native ``.xlsx`` — not as a raw float serial."""
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    date_style = xlwt.easyxf(num_format_str="DD-MM-YYYY")
    sheet.write(0, 0, "when")
    sheet.write(1, 0, datetime.datetime(2026, 7, 8), date_style)
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)

    assert looks_like_xls(buffer)
    converted = convert_xls_to_xlsx(buffer)
    workbook = load_workbook(converted, read_only=True, data_only=True)
    try:
        rows = list(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()
    assert rows[0][0] == "when"
    assert rows[1][0] == datetime.datetime(2026, 7, 8)


def _extract_csrf_token(html: str) -> str:
    """Pull the hidden ``csrfmiddlewaretoken`` value out of a rendered form."""
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
    assert match is not None, "no CSRF token found in the rendered upload form"
    return match.group(1)


def test_upload_view_survives_csrf_enforced_multipart_post(
    home_page, settings, tmp_path, django_user_model
):
    """Regression for the production 500: the real browser path is a
    CSRF-enforced multipart POST.

    ``CsrfViewMiddleware`` reads ``request.POST`` to validate the token, which
    parses the multipart body and locks ``request.upload_handlers`` *before*
    the view runs. When the memory-only handler was set inside the view, that
    swap raised ``AttributeError: You cannot set the upload handlers after the
    upload has been processed`` → HTTP 500. Moving the swap into
    ``MemoryOnlyUploadHandlerMiddleware`` (which runs before CSRF) fixes it.

    The default Django test client sets ``enforce_csrf_checks=False``, so
    ``CsrfViewMiddleware`` short-circuits without reading ``request.POST`` and
    the whole failure mode is invisible — which is exactly why CI stayed green.
    This test opts into CSRF enforcement to exercise the true production path.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(_administrator_user(django_user_model))

    # GET the form first — this sets the csrftoken cookie and renders a token
    # matching it, mirroring a real browser session.
    form_page = csrf_client.get(reverse("pipeline:upload_export"))
    assert form_page.status_code == 200
    token = _extract_csrf_token(form_page.content.decode())

    response = csrf_client.post(
        reverse("pipeline:upload_export"),
        data={
            "csrfmiddlewaretoken": token,
            "export_file": SimpleUploadedFile(
                "TKC JULY 8TH STAT.xls",
                _build_tkc_daily_xls(),
                content_type="application/vnd.ms-excel",
            ),
            "format_key": "tkc_daily_activity_v1",
        },
    )

    # Not a 403 (CSRF genuinely passed) and not a 500 (the handler swap
    # happened in time) — the upload was ingested.
    assert response.status_code == 200
    # And the memory-only handler still held under the real CSRF path: the raw
    # export never spooled to disk (invariant #1).
    assert list(tmp_path.iterdir()) == []
    assert DailyAggregate.objects.filter(clinic_date=TKC_VISIT_DATE).exists()


def test_middleware_installs_memory_only_handler_for_the_upload_post():
    """The upload POST is forced onto a single ``MemoryFileUploadHandler`` —
    no ``TemporaryFileUploadHandler`` that could spool to disk."""
    captured: dict[str, list] = {}

    def get_response(request):
        captured["handlers"] = list(request.upload_handlers)
        return HttpResponse()

    request = RequestFactory().post(reverse("pipeline:upload_export"))
    MemoryOnlyUploadHandlerMiddleware(get_response)(request)

    assert len(captured["handlers"]) == 1
    assert isinstance(captured["handlers"][0], MemoryFileUploadHandler)


def test_middleware_leaves_other_paths_on_the_default_handler_chain():
    """A POST elsewhere (e.g. a Wagtail image upload) keeps the default
    handlers, including the temp handler that spools large files to disk —
    the memory-only swap is scoped to the export upload alone."""
    captured: dict[str, list] = {}

    def get_response(request):
        captured["handlers"] = list(request.upload_handlers)
        return HttpResponse()

    request = RequestFactory().post("/admin/images/multiple/add/")
    MemoryOnlyUploadHandlerMiddleware(get_response)(request)

    assert any(
        isinstance(handler, TemporaryFileUploadHandler)
        for handler in captured["handlers"]
    )


def test_upload_view_denies_user_without_can_upload_export(
    client, db, django_user_model
):
    """Invariant #4's permission gate, exercised as a real request/response.

    Two things prove "denied" here, grounded in Wagtail's real behaviour
    (``wagtail.admin.auth.require_admin_access``/``permission_denied``, which
    wraps every ``register_admin_urls`` view including ours):

    * A user lacking even ``wagtailadmin.access_admin`` never reaches our
      view at all — Wagtail's own gate redirects them to the admin login
      page first. That's Wagtail's boundary, not ours.
    * A user *with* basic admin access but without ``can_upload_export``
      does reach our ``permission_required`` check, which raises
      ``PermissionDenied`` — Wagtail's wrapper turns that into a redirect to
      the admin home with a "you do not have permission" flash message for a
      normal browser request (a 403 only for an AJAX request, checked via
      ``X-Requested-With``). Both assertions below prove *our* check fired,
      not Wagtail's outer one.
    """
    other = django_user_model.objects.create_user(username="no-perm", password="x")  # noqa: S106
    other.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="wagtailadmin", codename="access_admin"
        )
    )
    client.force_login(other)

    response = client.get(reverse("pipeline:upload_export"))
    assert response.status_code == 302
    assert response.url == reverse("wagtailadmin_home")

    ajax_response = client.get(
        reverse("pipeline:upload_export"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
    )
    assert ajax_response.status_code == 403


# --- Re-upload: duplicate is a no-op, corrected re-upload replaces ---------


def test_reuploading_the_same_fixture_is_a_noop_duplicate(home_page):
    first = _ingest_clinic_v1()
    assert first.results[0].status == IngestRun.STATUS_CREATED

    second = _ingest_clinic_v1()
    assert second.results[0].status == IngestRun.STATUS_DUPLICATE
    assert DeidentifiedVisit.objects.filter(
        visit_date=CLINIC_V1_VISIT_DATE
    ).count() == (EXPECTED_TOTAL_VISITS)


def test_corrected_reupload_replaces_rather_than_double_counts(home_page):
    _ingest_clinic_v1()

    corrected_rows = [list(row) for row in CLINIC_V1_ROWS]
    corrected_rows[0][8] = "Male"  # a correction: row 1's gender was mis-entered
    result = _ingest_clinic_v1(rows=corrected_rows)
    assert result.results[0].status == IngestRun.STATUS_REPLACED

    # Still exactly 4 rows for the date — replaced, not appended.
    assert DeidentifiedVisit.objects.filter(
        visit_date=CLINIC_V1_VISIT_DATE
    ).count() == (EXPECTED_TOTAL_VISITS)
    aggregate = DailyAggregate.objects.get(clinic_date=CLINIC_V1_VISIT_DATE)
    assert aggregate.male_patients == 2  # row 1's corrected gender is reflected
    assert aggregate.female_patients == 1


def _post_tkc_daily_upload(client, **xls_kwargs):
    return client.post(
        reverse("pipeline:upload_export"),
        data={
            "export_file": SimpleUploadedFile(
                "TKC daily.xls",
                _build_tkc_daily_xls(**xls_kwargs),
                content_type="application/vnd.ms-excel",
            ),
            "format_key": "tkc_daily_activity_v1",
        },
    )


def test_tkc_daily_reupload_via_upload_view_is_a_noop_duplicate(
    client, home_page, django_user_model
):
    """Regression: dedup/replace coverage for the *currently registered*
    format must go through the real ParserRegistry.get(parser_key) lookup
    the upload view actually uses — not just the unregistered clinic_v1
    fixture (see the format-removal decision above). A second identical
    upload of the clinic's real tkc_daily_activity_v1 export is a no-op."""
    client.force_login(_administrator_user(django_user_model))

    first = _post_tkc_daily_upload(client)
    assert first.status_code == 200
    assert IngestRun.objects.filter(clinic_date=TKC_VISIT_DATE).first().status == (
        IngestRun.STATUS_CREATED
    )

    second = _post_tkc_daily_upload(client)
    assert second.status_code == 200
    # One IngestRun per upload event, newest first (Meta.ordering) — the
    # duplicate upload adds its own row rather than updating the first.
    assert IngestRun.objects.filter(clinic_date=TKC_VISIT_DATE).first().status == (
        IngestRun.STATUS_DUPLICATE
    )
    assert DeidentifiedVisit.objects.filter(visit_date=TKC_VISIT_DATE).count() == 3


# --- Daily report auto-publish + the AI summary sentence -------------------


def test_daily_summary_payload_contains_only_this_dates_aggregate(
    home_page, mock_anthropic_client
):
    """Invariant #2, for the daily-summary call specifically: the payload is
    built only from this date's DailyAggregate — never a row, never another
    date's figures."""
    _ingest_clinic_v1()
    aggregate = DailyAggregate.objects.get(clinic_date=CLINIC_V1_VISIT_DATE)

    sentence = ai.draft_daily_summary_sentence(aggregate, mock_anthropic_client)
    assert sentence  # the stub returned its canned (truncated-safe) text

    assert len(mock_anthropic_client.calls) == 1
    sent = json.dumps(mock_anthropic_client.calls[0]).lower()
    for identifier in CLINIC_V1_RAW_IDENTIFIERS:
        assert identifier not in sent
    for column in PATIENT_IDENTIFYING_COLUMNS:
        assert column not in sent
    assert str(EXPECTED_TOTAL_VISITS) in sent
    assert "total_visits" in sent


def test_daily_report_page_publishes_numbers_even_when_ai_client_fails(home_page):
    """The AI summary sentence never blocks the deterministic numbers: a
    client whose call raises still results in a published page with the
    correct figures and an empty summary_sentence."""
    _ingest_clinic_v1()

    def _raise(**kwargs):
        raise TimeoutError("simulated AI timeout")

    raising_client = SimpleNamespace(messages=SimpleNamespace(create=_raise))

    # publish_daily_report already ran once during _ingest_clinic_v1 (client=
    # None, which hits the forbidden-real-client guard and falls back) —
    # republish explicitly with a client that raises, to prove the *same*
    # fallback path.
    page = publish_daily_report(CLINIC_V1_VISIT_DATE, client=raising_client)

    assert page.live is True
    assert page.summary_sentence == ""
    assert page.aggregate.total_visits == EXPECTED_TOTAL_VISITS


def test_ingest_export_auto_publishes_the_daily_report_page(home_page):
    """The full flow: an ingest creates + live-publishes the DailyReportPage,
    with no draft step (maintainer decision, PR #15)."""
    _ingest_clinic_v1()
    page = DailyReportPage.objects.get(report_date=CLINIC_V1_VISIT_DATE)
    assert page.live is True
    assert page.aggregate.total_visits == EXPECTED_TOTAL_VISITS


# --- Recompute command: DailyAggregate is a derived cache -------------------


def test_recompute_daily_aggregates_command_rebuilds_from_deidentified_visit(home_page):
    _ingest_clinic_v1()
    original = DailyAggregate.objects.get(clinic_date=CLINIC_V1_VISIT_DATE)
    original_dict = original.as_dict()

    # Simulate a stale/corrupted aggregate — the command should rebuild it
    # from DeidentifiedVisit (the canonical store), not trust the stored row.
    DailyAggregate.objects.filter(clinic_date=CLINIC_V1_VISIT_DATE).update(
        total_visits=999
    )

    call_command("recompute_daily_aggregates")

    rebuilt = DailyAggregate.objects.get(clinic_date=CLINIC_V1_VISIT_DATE)
    assert rebuilt.as_dict() == original_dict


# --- Home page teaser wiring -------------------------------------------------


def test_home_page_get_latest_report_returns_latest_published_daily_report(db):
    home = HomePageFactory()
    index = ReportIndexPageFactory(parent=home)
    DailyReportPageFactory(parent=index, report_date=datetime.date(2026, 7, 1))
    latest = DailyReportPageFactory(
        parent=index, report_date=datetime.date(2026, 7, 15)
    )

    assert home.get_latest_report().pk == latest.pk


def test_persist_parsed_export_groups_rows_by_visit_date(home_page):
    """A single export spanning more than one clinic-date produces one
    IngestRun/DailyAggregate per date, not one lumped together."""
    from apps.pipeline.parser_registry import ParsedExport, ParsedVisitRow

    rows = [
        ParsedVisitRow(
            visit_date=datetime.date(2026, 7, 1),
            department="General Medicine",
            age_band=DeidentifiedVisit.AGE_BAND_18_40,
            sex=DeidentifiedVisit.SEX_MALE,
            location="Thandkoi",
            diagnosis_category=DeidentifiedVisit.DIAGNOSIS_OTHER,
            is_new_patient=True,
            is_zakat_beneficiary=True,
        ),
        ParsedVisitRow(
            visit_date=datetime.date(2026, 7, 2),
            department="General Medicine",
            age_band=DeidentifiedVisit.AGE_BAND_18_40,
            sex=DeidentifiedVisit.SEX_FEMALE,
            location="Thandkoi",
            diagnosis_category=DeidentifiedVisit.DIAGNOSIS_OTHER,
            is_new_patient=True,
            is_zakat_beneficiary=True,
        ),
    ]
    summary = persist_parsed_export(
        ParsedExport(rows=rows), parser_key="clinic_daily_export_v1", uploaded_by=None
    )
    assert {r.clinic_date for r in summary.results} == {
        datetime.date(2026, 7, 1),
        datetime.date(2026, 7, 2),
    }
    assert DailyAggregate.objects.filter(clinic_date=datetime.date(2026, 7, 1)).exists()
    assert DailyAggregate.objects.filter(clinic_date=datetime.date(2026, 7, 2)).exists()
