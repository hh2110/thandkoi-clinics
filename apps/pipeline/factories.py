"""factory_boy factories for pipeline models — mirrors apps.core.factories.

``ReportIndexPage``/``DailyReportPage`` use the same ``_TreePageFactory``
pattern as Plan 06's archive pages (a Wagtail page must be attached under a
parent via ``add_child``, not plain ``.objects.create()``).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import factory
from wagtail.models import Page

from apps.pipeline.models import (
    AiCallLog,
    CampUploadReportPage,
    DailyAggregate,
    DailyReportPage,
    DeidentifiedVisit,
    IngestRun,
    NewsletterDraftRun,
    ReportIndexPage,
)


class _TreePageFactory(factory.django.DjangoModelFactory):
    """Same pattern as apps.core.factories._TreePageFactory (not reused across
    apps to avoid a cross-app private import; kept identical on purpose)."""

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        parent = kwargs.pop("parent", None) or Page.get_first_root_node()
        instance = model_class(*args, **kwargs)
        parent.add_child(instance=instance)
        return instance


class IngestRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IngestRun

    clinic_date = factory.LazyFunction(datetime.date.today)
    parser_key = "clinic_daily_export_v1"
    row_count = 1
    content_hash = factory.Sequence(lambda n: f"testhash{n}")
    status = IngestRun.STATUS_CREATED


class DeidentifiedVisitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeidentifiedVisit

    ingest_run = factory.SubFactory(IngestRunFactory)
    visit_date = factory.LazyAttribute(lambda o: o.ingest_run.clinic_date)
    department = "General Medicine"
    age_band = DeidentifiedVisit.AGE_BAND_18_40
    sex = DeidentifiedVisit.SEX_FEMALE
    location = "Thandkoi"
    diagnosis_category = DeidentifiedVisit.DIAGNOSIS_HYPERTENSION
    is_new_patient = True
    is_zakat_beneficiary = True


class DailyAggregateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyAggregate

    clinic_date = factory.LazyFunction(datetime.date.today)
    total_visits = 3
    male_patients = 1
    female_patients = 2
    other_or_unknown_sex_patients = 0
    new_patients = 2
    follow_up_patients = 1
    unknown_patient_type_patients = 0
    zakat_beneficiary_patients = 2
    paying_patients = 1
    unknown_payment_type_patients = 0
    category_counts = factory.LazyFunction(
        lambda: {
            "by_department": {"General Medicine": 3},
            "by_diagnosis_category": {"hypertension": 2, "diabetes": 1},
            "by_age_band": {"18-40": 3},
        }
    )


class ReportIndexPageFactory(_TreePageFactory):
    class Meta:
        model = ReportIndexPage

    title = "Reports"
    slug = "reports"


class DailyReportPageFactory(_TreePageFactory):
    class Meta:
        model = DailyReportPage

    title = factory.LazyAttribute(lambda o: f"Daily report — {o.report_date}")
    slug = factory.LazyAttribute(lambda o: o.report_date.isoformat())
    report_date = factory.LazyFunction(datetime.date.today)
    aggregate = factory.SubFactory(
        DailyAggregateFactory,
        clinic_date=factory.SelfAttribute("..report_date"),
    )


class CampUploadReportPageFactory(_TreePageFactory):
    class Meta:
        model = CampUploadReportPage

    title = factory.LazyAttribute(lambda o: o.camp_title)
    slug = factory.LazyAttribute(lambda o: o.camp_date.isoformat())
    camp_date = factory.LazyFunction(datetime.date.today)
    camp_title = "Free Medical Camp"
    aggregate = factory.SubFactory(
        DailyAggregateFactory,
        clinic_date=factory.SelfAttribute("..camp_date"),
        report_kind=IngestRun.KIND_CAMP,
    )


class NewsletterDraftRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NewsletterDraftRun

    month = factory.LazyFunction(lambda: datetime.date.today().replace(day=1))
    status = NewsletterDraftRun.STATUS_SUCCEEDED


class AiCallLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AiCallLog

    call_site = AiCallLog.CALL_SITE_DAILY_SUMMARY
    model = "claude-haiku-4-5"
    input_tokens = 100
    output_tokens = 50
    cost_usd = Decimal("0.00035")
