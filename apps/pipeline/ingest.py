"""Persist a parsed export: content-hash dedup/replace, then recompute + publish.

This is the one DB-writing boundary downstream of the parser (Plan 08's
"one DB transaction" in the plan's diagram). Nothing here ever reads a raw
identifier — everything it touches is already a
:class:`~apps.pipeline.parser_registry.ParsedVisitRow`, which is
de-identified by construction (see ``apps.pipeline.parser_registry``).

Re-upload behaviour (maintainer decision, PR #15): an exact-duplicate
re-upload for a date is a no-op; a genuine correction **replaces** that
date's rows and aggregate atomically. Detected via ``IngestRun.content_hash``
— a fingerprint of the de-identified rows, not the raw file.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import BinaryIO

from django.db import transaction

from apps.pipeline.models import DailyAggregate, DeidentifiedVisit, IngestRun
from apps.pipeline.parser_registry import (
    BUCKET_REGULAR,
    BUCKET_UNKNOWN,
    BUCKET_ZAKAT,
    REVENUE_BUCKETS,
    SERVICE_FEE_FIELDS,
    ParsedExport,
    ParsedVisitRow,
    ParserRegistry,
    content_hash_for_rows,
)

logger = logging.getLogger(__name__)


def _counter(values) -> dict[str, int]:
    """Sorted ``{value: count}`` — deterministic regardless of input order."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _payment_bucket(is_zakat_beneficiary: bool | None) -> str:
    """Which revenue bucket a visit's money belongs in (Plan 22 D3).

    Three buckets, not two. ``None`` — a ``Status`` cell that is neither
    "zakat" nor "regular" — gets its own ``unknown`` bucket rather than being
    folded into Regular (an invention) or dropped (which would make published
    income silently understate what the clinic took). This mirrors the
    existing ``DailyAggregate.unknown_payment_type_patients``, which already
    treats that third case as first-class.
    """
    if is_zakat_beneficiary is True:
        return BUCKET_ZAKAT
    if is_zakat_beneficiary is False:
        return BUCKET_REGULAR
    return BUCKET_UNKNOWN


def _service_revenue(visits) -> dict:
    """Per-service, per-bucket ``{"qty", "amount"}`` for one clinic-date.

    ``amount`` sums that service's fee column; ``qty`` counts the rows where
    it was non-zero — services delivered, not patients (Plan 16 D14: a
    service is the line, not the item, so one lab line covering N tests is
    one lab service).

    Returns ``{}`` — not a dict of zeros — when the date has no revenue at
    all, because ``apps.pipeline.dashboard.has_revenue`` tests the field's
    truthiness to decide whether the date predates the clinic software's fee
    columns. A dict of zeros would read as "revenue exists and is zero" and
    light up an empty revenue table on every historical date.
    """
    revenue = {
        service: {bucket: {"qty": 0, "amount": 0} for bucket in REVENUE_BUCKETS}
        for service in SERVICE_FEE_FIELDS
    }
    any_revenue = False
    for visit in visits:
        bucket = _payment_bucket(visit.is_zakat_beneficiary)
        for service, field_name in SERVICE_FEE_FIELDS.items():
            fee = getattr(visit, field_name, 0) or 0
            if fee <= 0:
                continue
            any_revenue = True
            cell = revenue[service][bucket]
            cell["qty"] += 1
            cell["amount"] += fee
    return revenue if any_revenue else {}


def _warn_on_total_paid_drift(clinic_date: date, rows: list[ParsedVisitRow]) -> None:
    """Reconcile the five fee columns against the export's own ``Total Paid``.

    Plan 22 D5. The per-service columns are the source of truth; this only
    checks that the export agrees with itself. It **warns and never raises**
    — the Plan 17 observability setup forwards ``WARNING`` and above to
    Sentry, so drift is visible without a malformed column being able to
    block a whole day's upload.

    This lives in the ingest path rather than in ``recompute_daily_aggregate``
    because ``total_paid`` is deliberately not persisted (Plan 22 D2): it is
    only available while the parsed rows are still in hand.

    Why this check exists at all: these columns have already emitted
    fabricated values once — the 6 Aug 2026 camp export carried a flat
    ``Registration Fee (PKR)`` of 20 across all 93 attendees of an
    advertised-free camp, confirmed by the maintainer as a clinic-software
    report bug.
    """
    service_total = sum(
        getattr(row, field_name, 0) or 0
        for row in rows
        for field_name in SERVICE_FEE_FIELDS.values()
    )
    reported_total = sum(row.total_paid or 0 for row in rows)
    if service_total == reported_total:
        return
    # No cell values, no patient data — a date and two sums over an already
    # de-identified set of rows.
    logger.warning(
        "Revenue reconciliation mismatch for %s: per-service fees sum to "
        "PKR %s but the export's own 'Total Paid (PKR)' column sums to "
        "PKR %s (difference PKR %s across %s rows). The per-service figures "
        "are what the site publishes; check the clinic software's report.",
        clinic_date.isoformat(),
        service_total,
        reported_total,
        service_total - reported_total,
        len(rows),
    )


def recompute_daily_aggregate(
    clinic_date: date,
    *,
    latest_ingest_run: IngestRun | None = None,
) -> DailyAggregate:
    """Rebuild ``DailyAggregate`` for one date from ``DeidentifiedVisit`` rows.

    ``DeidentifiedVisit`` is the canonical store; this is the **only** place
    ``DailyAggregate`` values are computed, whether called right after an
    ingest (with the new ``latest_ingest_run``) or standalone by the
    ``recompute_daily_aggregates`` management command (with none — the
    aggregate's existing ``latest_ingest_run`` is left untouched, since no new
    ingest happened). Every figure here comes from a plain Python count over
    already-de-identified rows — deterministic, byte-for-byte reproducible
    (CLAUDE.md invariant #3).
    """
    visits = list(DeidentifiedVisit.objects.filter(visit_date=clinic_date))
    total = len(visits)

    male = sum(1 for v in visits if v.sex == DeidentifiedVisit.SEX_MALE)
    female = sum(1 for v in visits if v.sex == DeidentifiedVisit.SEX_FEMALE)
    other_or_unknown_sex = total - male - female

    new_patients = sum(1 for v in visits if v.is_new_patient is True)
    follow_up_patients = sum(1 for v in visits if v.is_new_patient is False)
    unknown_patient_type = total - new_patients - follow_up_patients

    zakat_beneficiary = sum(1 for v in visits if v.is_zakat_beneficiary is True)
    paying = sum(1 for v in visits if v.is_zakat_beneficiary is False)
    unknown_payment_type = total - zakat_beneficiary - paying

    defaults = {
        "total_visits": total,
        "male_patients": male,
        "female_patients": female,
        "other_or_unknown_sex_patients": other_or_unknown_sex,
        "new_patients": new_patients,
        "follow_up_patients": follow_up_patients,
        "unknown_patient_type_patients": unknown_patient_type,
        "zakat_beneficiary_patients": zakat_beneficiary,
        "paying_patients": paying,
        "unknown_payment_type_patients": unknown_payment_type,
        "category_counts": {
            "by_department": _counter(v.department or "unspecified" for v in visits),
            "by_diagnosis_category": _counter(v.diagnosis_category for v in visits),
            "by_age_band": _counter(v.age_band for v in visits),
        },
        # Plan 22: recomputed from the canonical per-visit fees like every
        # other figure here, so this stays deterministic and byte-for-byte
        # reproducible (invariant #3) and the command below can rebuild a
        # historical date's revenue rather than zeroing it.
        "service_revenue": _service_revenue(visits),
    }
    if latest_ingest_run is not None:
        defaults["latest_ingest_run"] = latest_ingest_run

    aggregate, _created = DailyAggregate.objects.update_or_create(
        clinic_date=clinic_date, defaults=defaults
    )
    return aggregate


@dataclass(frozen=True)
class DateIngestResult:
    """Outcome for one clinic-date within a (possibly multi-date) upload.

    Deliberately carries **counts only** — the upload view's success message
    is built from this, never from the parsed rows themselves.
    """

    clinic_date: date
    status: str
    row_count: int


@dataclass(frozen=True)
class IngestSummary:
    """The only thing the upload view renders — per-date counts, never rows."""

    parser_key: str
    results: list[DateIngestResult] = field(default_factory=list)


def _ingest_one_date(
    clinic_date: date,
    rows: list[ParsedVisitRow],
    *,
    parser_key: str,
    uploaded_by,
) -> DateIngestResult:
    """Content-hash dedup/replace for a single clinic-date, in one transaction."""
    content_hash = content_hash_for_rows(rows)

    existing_aggregate = (
        DailyAggregate.objects.filter(clinic_date=clinic_date)
        .select_related("latest_ingest_run")
        .first()
    )
    is_duplicate = (
        existing_aggregate is not None
        and existing_aggregate.latest_ingest_run is not None
        and existing_aggregate.latest_ingest_run.content_hash == content_hash
    )
    if is_duplicate:
        # Still recorded in the audit trail (an upload attempt happened), but
        # no row/aggregate data is touched — a true no-op.
        IngestRun.objects.create(
            clinic_date=clinic_date,
            parser_key=parser_key,
            uploaded_by=uploaded_by,
            row_count=0,
            content_hash=content_hash,
            status=IngestRun.STATUS_DUPLICATE,
        )
        return DateIngestResult(
            clinic_date=clinic_date, status=IngestRun.STATUS_DUPLICATE, row_count=0
        )

    status = (
        IngestRun.STATUS_REPLACED if existing_aggregate else IngestRun.STATUS_CREATED
    )
    with transaction.atomic():
        run = IngestRun.objects.create(
            clinic_date=clinic_date,
            parser_key=parser_key,
            uploaded_by=uploaded_by,
            row_count=len(rows),
            content_hash=content_hash,
            status=status,
        )
        # Supersede: an existing date's rows are replaced wholesale, never
        # appended to — this is what makes a corrected re-upload a true
        # replace rather than a silent double-count.
        DeidentifiedVisit.objects.filter(visit_date=clinic_date).delete()
        DeidentifiedVisit.objects.bulk_create(
            [
                DeidentifiedVisit(
                    ingest_run=run,
                    visit_date=row.visit_date,
                    department=row.department,
                    age_band=row.age_band,
                    sex=row.sex,
                    location=row.location,
                    diagnosis_category=row.diagnosis_category,
                    is_new_patient=row.is_new_patient,
                    is_zakat_beneficiary=row.is_zakat_beneficiary,
                    # Plan 11 Track B8/B9 free-text columns (2026-07-23) —
                    # see ParsedVisitRow's docstring for the grounding note.
                    presenting_complaints=row.presenting_complaints,
                    investigation=row.investigation,
                    provisional_diagnosis_text=row.provisional_diagnosis_text,
                    prescribed_medicine=row.prescribed_medicine,
                    clinical_notes=row.clinical_notes,
                    diet_and_drug_compliance=row.diet_and_drug_compliance,
                    plan_notes=row.plan_notes,
                    # Plan 22 D2 — persisted per visit so the aggregate stays
                    # recomputable from this table alone.
                    registration_fee=row.registration_fee,
                    consultation_fee=row.consultation_fee,
                    pharmacy_fee=row.pharmacy_fee,
                    laboratory_fee=row.laboratory_fee,
                    ultrasound_fee=row.ultrasound_fee,
                )
                for row in rows
            ]
        )
        recompute_daily_aggregate(clinic_date, latest_ingest_run=run)

    # After the transaction commits, and never inside it: this is a
    # diagnostic, so it must not be able to affect the write it reports on.
    _warn_on_total_paid_drift(clinic_date, rows)

    return DateIngestResult(clinic_date=clinic_date, status=status, row_count=len(rows))


def persist_parsed_export(
    parsed: ParsedExport,
    *,
    parser_key: str,
    uploaded_by,
) -> IngestSummary:
    """Group rows by clinic-date, ingest each date, then auto-publish its report.

    The report auto-publish (and its AI summary-sentence call) deliberately
    happens *after* each date's DB transaction commits — never inside it — so
    a slow or failing AI call can never hold the row/aggregate write open.
    """
    # Local import: report_publishing depends on this module's models but not
    # on ingest itself, so there's no cycle — kept local purely to keep this
    # module's own import list focused on persistence, not publishing.
    from apps.pipeline.report_publishing import publish_daily_report

    rows_by_date: dict[date, list[ParsedVisitRow]] = defaultdict(list)
    for row in parsed.rows:
        rows_by_date[row.visit_date].append(row)

    results = []
    for clinic_date in sorted(rows_by_date):
        result = _ingest_one_date(
            clinic_date,
            rows_by_date[clinic_date],
            parser_key=parser_key,
            uploaded_by=uploaded_by,
        )
        results.append(result)
        if result.status != IngestRun.STATUS_DUPLICATE:
            publish_daily_report(clinic_date)

    return IngestSummary(parser_key=parser_key, results=results)


def ingest_export(
    uploaded_file: BinaryIO,
    *,
    parser_key: str,
    uploaded_by,
) -> IngestSummary:
    """Parse an in-memory upload and persist it. The upload view's one call.

    ``uploaded_file`` is read entirely inside ``parser.parse()`` (which
    returns only de-identified rows); nothing here retains a reference to it
    afterwards, so it is free to be garbage-collected once this returns —
    the raw bytes are never written anywhere.
    """
    parser = ParserRegistry.get(parser_key)
    parsed = parser.parse(uploaded_file)
    return persist_parsed_export(
        parsed,
        parser_key=parser_key,
        uploaded_by=uploaded_by,
    )
