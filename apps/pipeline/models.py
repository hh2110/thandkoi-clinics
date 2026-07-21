"""Plan 08 — the pipeline's persisted, PHI-free data model.

Three plain Django models (``IngestRun``, ``DeidentifiedVisit``,
``DailyAggregate``) plus two Wagtail pages (``ReportIndexPage``,
``DailyReportPage``). Every field here is safe by construction: nothing in
this module can hold a name, father's/husband's name, CNIC, phone number,
full address, date of birth, or raw diagnosis text — those are stripped or
transformed (DOB → age band, address → coarse location, free-text diagnosis →
fixed category) inside the parser, *before* a row ever reaches this module
(see ``apps.pipeline.parser_registry``). This module only ever receives
already-de-identified values.

``DeidentifiedVisit`` is the canonical row-level store; ``DailyAggregate`` is
a derived cache recomputable from it at any time (maintainer decision, PR #15
— see ``.claude/plans/08-data-pipeline.md`` "The data model"). ``IngestRun``
is an audit trail only — who/when/parser/row-count/content-hash, never data.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page

from apps.core.models import paginate_archive


class IngestRun(models.Model):
    """Audit record for one upload's worth of processing for one clinic-date.

    No patient data lives here — only who/when/which parser/how many rows/a
    content-hash fingerprint of the de-identified parsed rows (used only to
    detect an exact-duplicate re-upload; see ``apps.pipeline.ingest``). One
    row per (clinic_date, upload event), not per file — a single uploaded
    export may cover more than one clinic-date and produces one ``IngestRun``
    per date it touches.
    """

    STATUS_CREATED = "created"
    STATUS_REPLACED = "replaced"
    STATUS_DUPLICATE = "duplicate"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created (first upload for this date)"),
        (STATUS_REPLACED, "Replaced (corrected re-upload)"),
        (STATUS_DUPLICATE, "Duplicate (no-op, identical re-upload)"),
    ]

    clinic_date = models.DateField(db_index=True)
    parser_key = models.CharField(max_length=60)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pipeline_ingest_runs",
        help_text="Who uploaded the export this run came from.",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    row_count = models.PositiveIntegerField(
        help_text="Number of de-identified visit rows this run produced for "
        "this date (0 for a duplicate no-op)."
    )
    content_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 of the de-identified parsed rows for this date — a "
        "fingerprint, not the file. Identifies an exact-duplicate re-upload.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.clinic_date} ingest ({self.status}, {self.row_count} rows)"


class DeidentifiedVisit(models.Model):
    """One patient visit, direct identifiers removed by construction.

    No name, father's/husband's name, DOB, full street address, or raw
    diagnosis text — the parser drops or transforms each of those before a
    row is ever built (see ``.claude/plans/08-data-pipeline.md``
    "De-identification"). ``location`` is deliberately coarse (village / union
    council), never the full address; ``diagnosis_category`` is one of a
    fixed set the parser's keyword mapping can produce, never free text.
    """

    AGE_BAND_0_4 = "0-4"
    AGE_BAND_5_12 = "5-12"
    AGE_BAND_13_17 = "13-17"
    AGE_BAND_18_40 = "18-40"
    AGE_BAND_41_60 = "41-60"
    AGE_BAND_61_PLUS = "61+"
    AGE_BAND_UNKNOWN = "unknown"
    AGE_BAND_CHOICES = [
        (AGE_BAND_0_4, "0–4"),
        (AGE_BAND_5_12, "5–12"),
        (AGE_BAND_13_17, "13–17"),
        (AGE_BAND_18_40, "18–40"),
        (AGE_BAND_41_60, "41–60"),
        (AGE_BAND_61_PLUS, "61+"),
        (AGE_BAND_UNKNOWN, "Unknown"),
    ]

    SEX_MALE = "male"
    SEX_FEMALE = "female"
    SEX_OTHER_UNKNOWN = "other_unknown"
    SEX_CHOICES = [
        (SEX_MALE, "Male"),
        (SEX_FEMALE, "Female"),
        (SEX_OTHER_UNKNOWN, "Other / unknown"),
    ]

    # The fixed diagnosis category set the parser's keyword mapping table maps
    # free-text diagnoses onto (see apps.pipeline.parser_registry). "other" is
    # the explicit fallback for anything the mapping doesn't recognise.
    DIAGNOSIS_HYPERTENSION = "hypertension"
    DIAGNOSIS_DIABETES = "diabetes"
    DIAGNOSIS_RESPIRATORY = "respiratory_infection"
    DIAGNOSIS_GASTROINTESTINAL = "gastrointestinal"
    DIAGNOSIS_MUSCULOSKELETAL = "musculoskeletal"
    DIAGNOSIS_DERMATOLOGICAL = "dermatological"
    DIAGNOSIS_MATERNAL_CHILD = "maternal_and_child_health"
    DIAGNOSIS_CARDIAC = "cardiac"
    DIAGNOSIS_INFECTIOUS = "infectious_disease"
    DIAGNOSIS_OTHER = "other"
    DIAGNOSIS_CATEGORY_CHOICES = [
        (DIAGNOSIS_HYPERTENSION, "Hypertension"),
        (DIAGNOSIS_DIABETES, "Diabetes"),
        (DIAGNOSIS_RESPIRATORY, "Respiratory infection"),
        (DIAGNOSIS_GASTROINTESTINAL, "Gastrointestinal"),
        (DIAGNOSIS_MUSCULOSKELETAL, "Musculoskeletal"),
        (DIAGNOSIS_DERMATOLOGICAL, "Dermatological"),
        (DIAGNOSIS_MATERNAL_CHILD, "Maternal & child health"),
        (DIAGNOSIS_CARDIAC, "Cardiac"),
        (DIAGNOSIS_INFECTIOUS, "Infectious disease"),
        (DIAGNOSIS_OTHER, "Other / unclassified"),
    ]

    ingest_run = models.ForeignKey(
        IngestRun, on_delete=models.CASCADE, related_name="visits"
    )
    visit_date = models.DateField(db_index=True)
    department = models.CharField(max_length=80, blank=True)
    age_band = models.CharField(
        max_length=20, choices=AGE_BAND_CHOICES, default=AGE_BAND_UNKNOWN
    )
    sex = models.CharField(
        max_length=20, choices=SEX_CHOICES, default=SEX_OTHER_UNKNOWN
    )
    location = models.CharField(
        max_length=120,
        blank=True,
        help_text="Coarse location (village / union council) — never a full "
        "street address.",
    )
    diagnosis_category = models.CharField(
        max_length=40, choices=DIAGNOSIS_CATEGORY_CHOICES, default=DIAGNOSIS_OTHER
    )
    is_new_patient = models.BooleanField(
        null=True,
        blank=True,
        help_text="True = new patient, False = follow-up, null = not recorded "
        "in the source export.",
    )
    is_zakat_beneficiary = models.BooleanField(
        null=True,
        blank=True,
        help_text="True = Zakat beneficiary, False = paying patient, null = "
        "not recorded in the source export.",
    )

    class Meta:
        indexes = [models.Index(fields=["visit_date"])]

    def __str__(self):
        return f"Visit on {self.visit_date} ({self.diagnosis_category})"


class DailyAggregate(models.Model):
    """One row per clinic-date — the read interface Plan 09 consumes.

    A derived cache: always recomputable from ``DeidentifiedVisit`` (the
    canonical store) via ``apps.pipeline.ingest.recompute_daily_aggregate`` or
    the ``recompute_daily_aggregates`` management command — never hand-edited.
    Named integer columns cover the common metrics; ``category_counts`` is a
    JSON field so new category breakdowns don't need a migration each time.
    """

    clinic_date = models.DateField(unique=True, db_index=True)

    total_visits = models.PositiveIntegerField(default=0)

    male_patients = models.PositiveIntegerField(default=0)
    female_patients = models.PositiveIntegerField(default=0)
    other_or_unknown_sex_patients = models.PositiveIntegerField(default=0)

    new_patients = models.PositiveIntegerField(default=0)
    follow_up_patients = models.PositiveIntegerField(default=0)
    unknown_patient_type_patients = models.PositiveIntegerField(default=0)

    zakat_beneficiary_patients = models.PositiveIntegerField(default=0)
    paying_patients = models.PositiveIntegerField(default=0)
    unknown_payment_type_patients = models.PositiveIntegerField(default=0)

    category_counts = models.JSONField(
        default=dict,
        blank=True,
        help_text="Flexible category breakdowns: by_department, "
        "by_diagnosis_category, by_age_band.",
    )

    latest_ingest_run = models.ForeignKey(
        IngestRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The most recent ingest run that (re)computed this date.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-clinic_date"]

    def __str__(self):
        return f"Daily aggregate for {self.clinic_date}"

    def as_dict(self) -> dict[str, object]:
        """Plain, JSON-serialisable, aggregates-only representation.

        This is the exact shape handed to the AI daily-summary-sentence call
        (invariant #2) — every value here is a count, never a patient row.
        """
        return {
            "clinic_date": self.clinic_date.isoformat(),
            "total_visits": self.total_visits,
            "male_patients": self.male_patients,
            "female_patients": self.female_patients,
            "other_or_unknown_sex_patients": self.other_or_unknown_sex_patients,
            "new_patients": self.new_patients,
            "follow_up_patients": self.follow_up_patients,
            "unknown_patient_type_patients": self.unknown_patient_type_patients,
            "zakat_beneficiary_patients": self.zakat_beneficiary_patients,
            "paying_patients": self.paying_patients,
            "unknown_payment_type_patients": self.unknown_payment_type_patients,
            "category_counts": dict(self.category_counts),
        }


class ReportIndexPage(Page):
    """Archive of daily report pages — mirrors Plan 06's index/child pattern.

    Same shape as ``NewsletterIndexPage``/``CampReportIndexPage`` (index +
    child ``Page`` per item), reused rather than reinvented (Stage 7:
    precedent over invention).
    """

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["pipeline.DailyReportPage"]

    def get_reports(self):
        """Published daily reports under this index, newest first."""
        return (
            DailyReportPage.objects.live()
            .child_of(self)
            .order_by("-report_date", "-pk")
        )

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["reports"] = paginate_archive(request, self.get_reports())
        return context

    class Meta:
        verbose_name = "Report index page"


class DailyReportPage(Page):
    """One clinic-date's published report — numbers live from ``DailyAggregate``.

    Auto-created and auto-published by ``apps.pipeline.report_publishing`` on
    every successful ingest (maintainer decision, PR #15: one page per date,
    archivable, no draft step for a committed/reviewed parser's output). The
    only editable field is ``summary_sentence`` — the one AI-written sentence
    the CLAUDE.md invariant #4 exception covers; every number on the rendered
    page is read live from ``aggregate``, never copied onto this page, so the
    figures always reflect the current state of the derived-cache aggregate
    even if it is later recomputed.
    """

    report_date = models.DateField(unique=True)
    aggregate = models.ForeignKey(
        DailyAggregate,
        on_delete=models.PROTECT,
        related_name="report_page",
        help_text="The aggregate this page renders. Figures are read live "
        "from here, never copied onto the page.",
    )
    summary_sentence = models.CharField(
        max_length=400,
        blank=True,
        help_text="The one AI-written summary sentence (CLAUDE.md invariant "
        "#4 exception) — a fixed-template restatement of this page's own "
        "aggregate figures. Blank if the AI call failed or was skipped; the "
        "numbers above still stand on their own.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("report_date"),
        FieldPanel("summary_sentence"),
    ]

    parent_page_types = ["pipeline.ReportIndexPage"]
    subpage_types: list[str] = []

    @property
    def summary(self) -> str:
        """The Home-page teaser's body text (``feature_split.html``'s ``body``).

        Falls back to a static line when the AI summary sentence is blank
        (call failed, timed out, or was skipped) — the teaser still reads as
        finished copy rather than an empty paragraph, per the "static
        fallback line" option in the plan's AI-summary-sentence decision.
        """
        return self.summary_sentence or "See the figures for this day below."

    @property
    def headline_stats(self) -> list[dict[str, str]]:
        """Inline stat pairs for the Home teaser (``feature_split.html``'s ``stats``).

        Mirrors ``CampReportPage.get_context``'s ``patient_stats`` shape
        (Plan 06) — read live from ``aggregate``, never copied onto this page.
        """
        return [
            {"value": str(self.aggregate.total_visits), "label": "Patients seen"},
            {
                "value": str(self.aggregate.zakat_beneficiary_patients),
                "label": "Zakat beneficiaries",
            },
            {"value": str(self.aggregate.new_patients), "label": "New patients"},
        ]

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["aggregate"] = self.aggregate
        context["by_department"] = sorted(
            self.aggregate.category_counts.get("by_department", {}).items()
        )
        context["by_diagnosis_category"] = sorted(
            self.aggregate.category_counts.get("by_diagnosis_category", {}).items()
        )
        context["by_age_band"] = sorted(
            self.aggregate.category_counts.get("by_age_band", {}).items()
        )
        return context

    class Meta:
        verbose_name = "Daily report"
