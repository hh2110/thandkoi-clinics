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
from wagtail.fields import RichTextField
from wagtail.models import Page

from apps.core.models import CampReportIndexPage, paginate_archive
from apps.pipeline.ai_pricing import compute_cost_usd


class IngestRun(models.Model):
    """Audit record for one upload's worth of processing for one clinic-date.

    No patient data lives here — only who/when/which parser/how many rows/a
    content-hash fingerprint of the de-identified parsed rows (used only to
    detect an exact-duplicate re-upload; see ``apps.pipeline.ingest``). One
    row per (clinic_date, upload event), not per file — a single uploaded
    export may cover more than one clinic-date and produces one ``IngestRun``
    per date it touches.

    ``report_kind`` (added for the camp-upload flow, 2026-07-22) discriminates
    the clinic's normal daily activity from a medical camp upload. This is
    load-bearing, not cosmetic: a camp and the clinic's own daily activity can
    fall on the *same calendar date*, and ``DeidentifiedVisit``/
    ``DailyAggregate`` are otherwise keyed only by ``visit_date``/
    ``clinic_date``. Without this discriminator, a camp upload sharing a date
    with a daily upload would silently merge into (or wholesale replace, via
    the "supersede" delete in ``apps.pipeline.ingest._ingest_one_date``) the
    clinic's own aggregate — corrupting figures that are meant to be
    independent. See ``DailyAggregate.report_kind`` for the matching half of
    this decision.
    """

    STATUS_CREATED = "created"
    STATUS_REPLACED = "replaced"
    STATUS_DUPLICATE = "duplicate"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created (first upload for this date)"),
        (STATUS_REPLACED, "Replaced (corrected re-upload)"),
        (STATUS_DUPLICATE, "Duplicate (no-op, identical re-upload)"),
    ]

    KIND_DAILY = "daily"
    KIND_CAMP = "camp"
    REPORT_KIND_CHOICES = [
        (KIND_DAILY, "Daily clinic activity"),
        (KIND_CAMP, "Medical camp"),
    ]

    clinic_date = models.DateField(db_index=True)
    report_kind = models.CharField(
        max_length=20, choices=REPORT_KIND_CHOICES, default=KIND_DAILY
    )
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

    # --- Plan 11 Track B8/B9: free-text columns (added 2026-07-23) ---------
    #
    # A later, narrower exception to this model's own "safe by construction"
    # docstring above: these seven fields hold *raw* free text, not a fixed
    # category or a coarsened value. That's only safe because the maintainer
    # separately confirmed (2026-07-23) that the clinic software's data-entry
    # UI structurally cannot accept a patient identifier into these specific
    # columns — see ``apps.pipeline.freetext``'s module docstring for the
    # full grounding note and ``ParsedVisitRow``'s docstring for the same
    # note at the parser boundary. This does NOT reopen de-identification for
    # any other free-text column; `location`/`diagnosis_category` above stay
    # coarsened exactly as before.
    #
    # Used only as the source for two auto-published AI calls (B8's summary,
    # B9's empty-column flag — see ``apps.pipeline.ai`` and
    # ``DailyReportPage.freetext_summary``/``empty_columns_flag``) — never
    # for a numeric aggregate, and never rendered directly on a public page
    # themselves.
    presenting_complaints = models.TextField(blank=True, default="")
    investigation = models.TextField(blank=True, default="")
    provisional_diagnosis_text = models.TextField(
        blank=True,
        default="",
        help_text="Raw free text, distinct from `diagnosis_category` above "
        "(a fixed keyword-mapped category derived from this same source "
        "column) — kept separately because B8/B9 need the actual text, not "
        "the category.",
    )
    prescribed_medicine = models.TextField(blank=True, default="")
    clinical_notes = models.TextField(
        blank=True,
        default="",
        help_text="Doctor's/Nurse's/Dietitian's notes, whichever the source "
        "export carries for this visit, concatenated if more than one is "
        "present — see apps.pipeline.parser_tkc_daily_v1 for how these are "
        "combined.",
    )
    diet_and_drug_compliance = models.TextField(blank=True, default="")
    plan_notes = models.TextField(blank=True, default="")

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

    ``report_kind`` (camp-upload flow, 2026-07-22) mirrors ``IngestRun``'s
    field of the same name — see that model's docstring for why a camp and
    the clinic's own daily activity must never share one aggregate row even
    when they land on the same calendar date. ``clinic_date`` is therefore no
    longer unique on its own; the natural key is now ``(clinic_date,
    report_kind)``.
    """

    clinic_date = models.DateField(db_index=True)
    report_kind = models.CharField(
        max_length=20,
        choices=IngestRun.REPORT_KIND_CHOICES,
        default=IngestRun.KIND_DAILY,
    )

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
        constraints = [
            models.UniqueConstraint(
                fields=["clinic_date", "report_kind"],
                name="pipeline_dailyaggregate_unique_date_kind",
            )
        ]

    def __str__(self):
        return f"{self.get_report_kind_display()} aggregate for {self.clinic_date}"

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

    Nav-merge decision (2026-07-22): the primary nav now carries a single
    "Reports" entry pointing here rather than separate "Reports"/"Camp
    Reports" links. This page's template therefore renders two sections —
    daily reports (this index's own archive) and a camp-reports teaser
    (sourced from ``core.CampReportIndexPage``, which keeps its own URL and
    archive; only the nav *entry* is merged, not the content type) — rather
    than introducing a dropdown-menu widget (not yet built anywhere in this
    repo; that's backlog item D8).
    """

    intro = RichTextField(blank=True, help_text="Optional intro copy for the archive.")

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
    ]

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
        # The merged-nav "Camp reports" teaser section (see this class's
        # docstring) — a handful of the latest camp reports plus a link to
        # their own archive, not a second paginated list on this page.
        camp_index = CampReportIndexPage.objects.first()
        context["camp_reports_index"] = camp_index
        context["camp_reports_preview"] = (
            camp_index.get_camp_reports()[:3] if camp_index is not None else []
        )
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

    # --- Plan 11 Track B8/B9: free-text summary + empty-column flag --------
    #
    # Auto-published alongside the numbers, same as `summary_sentence` above
    # — CLAUDE.md invariant #4's one narrow exception (Plan 08), widened
    # 2026-07-23 (maintainer decision) to also cover these two. Like
    # `summary_sentence`, a failed/skipped AI call leaves the field blank
    # (or, on a re-ingest, preserves whatever was there before — see
    # `report_publishing.publish_daily_report`) rather than blocking publish.
    freetext_summary = models.TextField(
        blank=True,
        help_text="AI-drafted summary of today's free-text clinical columns "
        "(Plan 11 Track B8) — a fixed-template restatement of this date's "
        "already-collected free-text entries. Blank if the AI call failed "
        "or was skipped.",
    )
    empty_columns_flag = models.TextField(
        blank=True,
        help_text="AI-drafted note on which free-text columns were left "
        "blank today (Plan 11 Track B9). Blank if the AI call failed or was "
        "skipped.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("report_date"),
        FieldPanel("summary_sentence"),
        FieldPanel("freetext_summary"),
        FieldPanel("empty_columns_flag"),
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
        # "By department" is intentionally not surfaced here: the real TKC
        # parser never populates `department` (parser_tkc_daily_v1's own
        # docstring), so this would always render as one dead "Unknown: N"
        # line in production. `category_counts["by_department"]` is still
        # computed at the model layer (harmless, and a future parser may
        # populate it) — this page just stops rendering it.
        #
        # "By diagnosis category" was dropped from this page too (maintainer
        # decision, 2026-07-23) — `category_counts["by_diagnosis_category"]`
        # is still computed at the model layer, this page just stops
        # rendering it.
        context["by_age_band"] = sorted(
            self.aggregate.category_counts.get("by_age_band", {}).items()
        )
        return context

    class Meta:
        verbose_name = "Daily report"


class CampUploadReportPage(Page):
    """One camp upload's auto-published report — the camp-upload flow (2026-07-22).

    Maintainer request: the same daily-export format can be uploaded for a
    medical camp instead of the clinic's normal daily activity, with a
    maintainer-supplied camp title. Design decisions, recorded here since
    there is no dedicated plan doc for this small feature:

    * **A new model, not a reuse of ``core.CampReportPage``.** Plan 06's
      ``CampReportPage`` is a manually-authored page whose fields (patients
      split into children/general/Welfare-free-service, a narrative,
      consented photos, partner credits) are an editor's categorisation of a
      source PDF — there is no correspondence between those categories and
      this pipeline's parsed columns (department/diagnosis_category/age_band/
      sex/zakat-beneficiary). Forcing the aggregate into that shape would
      mean inventing a mapping the source data doesn't support. This model
      instead mirrors ``DailyReportPage`` almost exactly (an ``aggregate`` FK
      read live, plus one editable free-text field) — the same numbers-driven
      shape, just for a camp instead of a clinic-day.
    * **Placed under ``core.CampReportIndexPage`` (Plan 06's existing camp
      archive), not a new pipeline-owned index.** A camp report belongs in
      the archive readers already know as "Camp Reports", sitting alongside
      the hand-authored ones — see ``CampReportIndexPage.get_camp_reports``
      for how the two page types are merged for display. This is the
      "reuse the destination page, not the content type" middle ground
      flagged to the maintainer for confirmation.
    * **No AI summary sentence at publish time.** CLAUDE.md's invariant #4
      exception (2026-07-19) for auto-publishing an AI sentence alongside
      deterministic numbers is scoped explicitly to "a deterministic daily
      report page" and says widening it is "a decision to make deliberately
      again, not something a future plan should assume by analogy" — and the
      existing prompt template (``apps.pipeline.ai``) is hard-coded to talk
      about "a clinic's day", not a camp. So this page auto-publishes with
      numbers only; ``summary_sentence`` starts blank and is left as an
      ordinary editable field (invariant #4's default human-in-the-loop) for
      a maintainer to fill in by hand if wanted. The **numbers**-only
      auto-publish itself mirrors PR #15's decision ("no draft step, since
      the parser producing [the] numbers is committed and code-reviewed"),
      which is about the reviewed pipeline's output in general, not narrowly
      about the word "daily" — so that part *is* extended by direct
      precedent, unlike the AI-sentence exception.

    ``camp_date`` is unique, mirroring ``DailyReportPage.report_date`` — one
    upload's aggregate (``report_kind='camp'``) per date. Two camps landing on
    the exact same calendar date is an out-of-scope edge case for now (a
    second upload for that date would be treated as a correcting re-upload of
    the *same* camp, per the existing dedup/replace semantics in
    ``apps.pipeline.ingest``) — flagged rather than silently handled.
    """

    camp_date = models.DateField(unique=True, help_text="The date of the camp.")
    camp_title = models.CharField(
        max_length=200,
        help_text="The camp's title, as entered by the admin at upload time "
        "(e.g. 'Free Medical Camp — Union Council X').",
    )
    aggregate = models.ForeignKey(
        DailyAggregate,
        on_delete=models.PROTECT,
        related_name="camp_report_page",
        help_text="This camp's aggregate (report_kind='camp'). Figures are "
        "read live from here, never copied onto the page.",
    )
    summary_sentence = models.CharField(
        max_length=400,
        blank=True,
        help_text="Optional free-text summary. Not AI-generated at publish "
        "time (see this model's docstring) — a maintainer may fill it in by "
        "hand.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("camp_date"),
        FieldPanel("camp_title"),
        FieldPanel("summary_sentence"),
    ]

    parent_page_types = ["core.CampReportIndexPage"]
    subpage_types: list[str] = []

    @property
    def summary(self) -> str:
        return self.summary_sentence or "See the figures for this camp below."

    @property
    def total_patients_served(self) -> int:
        """Duck-types alongside ``CampReportPage.total_patients_served`` so
        ``CampReportIndexPage``'s shared archive template can render either
        page type without branching on which one it is."""
        return self.aggregate.total_visits

    @property
    def location(self) -> str:
        """``CampReportPage`` has a free-text location; this pipeline-fed
        page has none (not part of the parsed schema) — empty string so the
        shared archive template's ``{% if camp_report.location %}`` stays
        false rather than erroring on a missing attribute."""
        return ""

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["aggregate"] = self.aggregate
        # "By department" is intentionally not surfaced here, same reasoning
        # as DailyReportPage (see the sibling UX-pass fix, 2026-07-22): a
        # camp upload uses the same parser, which never populates
        # `department`, so this would always render as one dead "Unknown: N"
        # line. `category_counts["by_department"]` is still computed at the
        # model layer.
        context["by_diagnosis_category"] = sorted(
            self.aggregate.category_counts.get("by_diagnosis_category", {}).items()
        )
        context["by_age_band"] = sorted(
            self.aggregate.category_counts.get("by_age_band", {}).items()
        )
        return context

    class Meta:
        verbose_name = "Camp upload report"


class NewsletterDraftRun(models.Model):
    """Audit record for one run of the monthly-newsletter drafting command.

    No patient data and no draft narrative text lives here — only
    who/when/target-month/outcome, mirroring ``IngestRun``'s audit-only shape
    (Plan 08). This is Plan 09's "failure visibility" decision (PR #17): no
    email/alert on failure, but a failed run must be visible to an
    Administrator somewhere in the admin console — see
    ``apps.pipeline.wagtail_hooks`` for where this is registered as a
    (view-only) Wagtail snippet.
    """

    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_SUCCEEDED, "Succeeded (draft created)"),
        (STATUS_FAILED, "Failed (no draft created)"),
    ]

    month = models.DateField(help_text="First day of the target calendar month.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(
        blank=True,
        help_text="What went wrong, for an Administrator to read here. Never "
        "patient data — this call only ever sees de-identified aggregates "
        "and admin-supplied notes.",
    )
    newsletter_page = models.ForeignKey(
        "core.NewsletterPage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The draft this run created, if it succeeded.",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The Administrator who ran the management command.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Newsletter draft run for {self.month:%Y-%m} ({self.status})"


class AiCallLog(models.Model):
    """Cost + usage record for one Anthropic API call (Plan 11 C2).

    Anthropic's API never returns a cost figure — only token counts. This
    model is that gap filled in: one row per real ``client.messages.create``
    call in ``apps.pipeline.ai``, recording which call site it was, the
    model, the token counts the response reported, and the computed cost
    (token counts x published per-model rate — see
    ``apps.pipeline.ai_pricing``), so total AI spend is visible in admin
    without cross-referencing Anthropic's own billing console.

    Deliberately no FK back to ``IngestRun``/``NewsletterDraftRun``/
    ``DailyAggregate``, unlike those audit models. The three current call
    sites in ``apps.pipeline.ai`` have no *common* triggering record to hang
    one off: ``draft_daily_summary_sentence`` has a ``DailyAggregate``,
    ``draft_monthly_newsletter_body`` runs before its caller's
    ``NewsletterDraftRun`` row even exists, and ``draft_newsletter_prose``
    (presently unused in production — see its call site's comment) takes an
    in-memory ``ClinicAggregate`` that isn't a persisted row at all. Adding a
    FK to only one of the three would misleadingly suggest the others have
    one too; ``call_site`` already identifies which caller produced a row.
    Add a nullable FK later if a real cross-referencing need shows up.
    """

    CALL_SITE_NEWSLETTER_PROSE = "newsletter_prose"
    CALL_SITE_DAILY_SUMMARY = "daily_summary"
    CALL_SITE_MONTHLY_NEWSLETTER = "monthly_newsletter"
    CALL_SITE_CHOICES = [
        (
            CALL_SITE_NEWSLETTER_PROSE,
            "Newsletter prose (draft_newsletter_prose — currently unused)",
        ),
        (CALL_SITE_DAILY_SUMMARY, "Daily report summary sentence"),
        (CALL_SITE_MONTHLY_NEWSLETTER, "Monthly newsletter drafting"),
    ]

    call_site = models.CharField(max_length=30, choices=CALL_SITE_CHOICES)
    model = models.CharField(
        max_length=60, help_text="Anthropic model id, e.g. claude-sonnet-5."
    )
    input_tokens = models.PositiveIntegerField()
    output_tokens = models.PositiveIntegerField()
    cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        help_text="input_tokens/output_tokens x the published per-model rate "
        "at call time — see apps.pipeline.ai_pricing.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_call_site_display()} ({self.model}): ${self.cost_usd}"

    @classmethod
    def record(
        cls, *, call_site: str, model: str, input_tokens: int, output_tokens: int
    ) -> AiCallLog:
        """Compute cost from the published per-token rates and log one call.

        The single entry point every call site in ``apps.pipeline.ai`` uses —
        keeps the cost computation (``apps.pipeline.ai_pricing``) out of the
        call sites themselves.
        """
        return cls.objects.create(
            call_site=call_site,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=compute_cost_usd(model, input_tokens, output_tokens),
        )
