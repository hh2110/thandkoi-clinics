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

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import BinaryIO

from django.db import transaction

from apps.pipeline.models import DailyAggregate, DeidentifiedVisit, IngestRun
from apps.pipeline.parser_registry import (
    ParsedExport,
    ParsedVisitRow,
    ParserRegistry,
    content_hash_for_rows,
)


def _counter(values) -> dict[str, int]:
    """Sorted ``{value: count}`` — deterministic regardless of input order."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def recompute_daily_aggregate(
    clinic_date: date,
    *,
    report_kind: str = IngestRun.KIND_DAILY,
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

    ``report_kind`` (camp-upload flow, 2026-07-22) scopes the recompute to
    just the visits from that kind of upload — a camp and the clinic's own
    daily activity can share a calendar date but must never be aggregated
    together (see ``IngestRun.report_kind``'s docstring). Filtered via
    ``ingest_run__report_kind`` since ``DeidentifiedVisit`` itself carries no
    ``report_kind`` column — only its owning ``IngestRun`` does.
    """
    visits = list(
        DeidentifiedVisit.objects.filter(
            visit_date=clinic_date, ingest_run__report_kind=report_kind
        )
    )
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
    }
    if latest_ingest_run is not None:
        defaults["latest_ingest_run"] = latest_ingest_run

    aggregate, _created = DailyAggregate.objects.update_or_create(
        clinic_date=clinic_date, report_kind=report_kind, defaults=defaults
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

    @property
    def total_rows(self) -> int:
        return sum(result.row_count for result in self.results)


def _ingest_one_date(
    clinic_date: date,
    rows: list[ParsedVisitRow],
    *,
    parser_key: str,
    uploaded_by,
    report_kind: str = IngestRun.KIND_DAILY,
) -> DateIngestResult:
    """Content-hash dedup/replace for a single clinic-date, in one transaction.

    ``report_kind`` scopes every step (existing-aggregate lookup, the
    supersede delete, and the recompute) to just this kind of upload, so a
    camp upload landing on a date that also has the clinic's own daily
    activity affects only its own rows/aggregate, never the other kind's
    (see ``IngestRun.report_kind``'s docstring).
    """
    content_hash = content_hash_for_rows(rows)

    existing_aggregate = (
        DailyAggregate.objects.filter(clinic_date=clinic_date, report_kind=report_kind)
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
            report_kind=report_kind,
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
            report_kind=report_kind,
            parser_key=parser_key,
            uploaded_by=uploaded_by,
            row_count=len(rows),
            content_hash=content_hash,
            status=status,
        )
        # Supersede: an existing date's rows *of this report_kind* are
        # replaced wholesale, never appended to — this is what makes a
        # corrected re-upload a true replace rather than a silent
        # double-count, while leaving the other report_kind's rows for the
        # same date untouched.
        DeidentifiedVisit.objects.filter(
            visit_date=clinic_date, ingest_run__report_kind=report_kind
        ).delete()
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
                )
                for row in rows
            ]
        )
        recompute_daily_aggregate(
            clinic_date, report_kind=report_kind, latest_ingest_run=run
        )

    return DateIngestResult(clinic_date=clinic_date, status=status, row_count=len(rows))


def persist_parsed_export(
    parsed: ParsedExport,
    *,
    parser_key: str,
    uploaded_by,
    report_kind: str = IngestRun.KIND_DAILY,
    camp_title: str | None = None,
) -> IngestSummary:
    """Group rows by clinic-date, ingest each date, then auto-publish its report.

    The report auto-publish (and, for a daily report, its AI summary-sentence
    call) deliberately happens *after* each date's DB transaction commits —
    never inside it — so a slow or failing AI call can never hold the
    row/aggregate write open.

    ``report_kind``/``camp_title`` (camp-upload flow, 2026-07-22): a
    ``report_kind`` of ``"camp"`` publishes a ``CampUploadReportPage`` instead
    of a ``DailyReportPage`` for each date the export covers, titled from
    ``camp_title`` (required by ``ExportUploadForm`` whenever ``report_kind``
    is ``"camp"`` — see that form's ``clean()``). A camp export spanning more
    than one date (unusual, but the format allows it) publishes one camp
    report page per date, all sharing that one title.
    """
    # Local import: report_publishing depends on this module's models but not
    # on ingest itself, so there's no cycle — kept local purely to keep this
    # module's own import list focused on persistence, not publishing.
    from apps.pipeline.report_publishing import (
        publish_camp_report,
        publish_daily_report,
    )

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
            report_kind=report_kind,
        )
        results.append(result)
        if result.status != IngestRun.STATUS_DUPLICATE:
            if report_kind == IngestRun.KIND_CAMP:
                publish_camp_report(clinic_date, camp_title=camp_title or "")
            else:
                publish_daily_report(clinic_date)

    return IngestSummary(parser_key=parser_key, results=results)


def ingest_export(
    uploaded_file: BinaryIO,
    *,
    parser_key: str,
    uploaded_by,
    report_kind: str = IngestRun.KIND_DAILY,
    camp_title: str | None = None,
) -> IngestSummary:
    """Parse an in-memory upload and persist it. The upload view's one call.

    ``uploaded_file`` is read entirely inside ``parser.parse()`` (which
    returns only de-identified rows); nothing here retains a reference to it
    afterwards, so it is free to be garbage-collected once this returns —
    the raw bytes are never written anywhere.

    ``report_kind``/``camp_title``: see :func:`persist_parsed_export`.
    """
    parser = ParserRegistry.get(parser_key)
    parsed = parser.parse(uploaded_file)
    return persist_parsed_export(
        parsed,
        parser_key=parser_key,
        uploaded_by=uploaded_by,
        report_kind=report_kind,
        camp_title=camp_title,
    )
