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

import json
import re
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page

from apps.core.models import CampReportIndexPage, paginate_archive
from apps.pipeline.ai_pricing import compute_cost_usd

#: Matches a response wrapped in a markdown code fence, with or without a
#: leading language tag (` ```json ` or bare ` ``` `) — group(1) is the
#: fenced content. Found in production 2026-07-25: every sampled
#: ``empty_columns_flag`` (7/7 checked) was stored as
#: ``'```json\n[...]\n```'`` even though ``_EMPTY_COLUMNS_FLAG_SYSTEM_PROMPT``
#: explicitly says "no prose, no markdown" — real ``claude-haiku-4-5``
#: responses to a "respond with JSON only" instruction routinely add the
#: fence anyway. Duplicated in ``apps.pipeline.freetext``'s
#: ``_strip_markdown_fence`` (same few lines) rather than shared, to avoid a
#: models.py <-> freetext.py import cycle (freetext.py already imports
#: ``DeidentifiedVisit`` from here).
_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_markdown_fence(raw: str) -> str:
    """Unwrap a ```json ... ``` (or bare ``` ... ```) fence, if present."""
    match = _MARKDOWN_FENCE_RE.match(raw.strip())
    return match.group(1) if match else raw


def _parse_empty_columns_flag(raw: str) -> list[str]:
    """Parse ``DailyReportPage.empty_columns_flag`` into a list of column names.

    Plan 11 Track B12: the stored value is a JSON array of column-name
    strings (see ``apps.pipeline.ai.draft_empty_columns_flag``), not prose —
    the template renders each entry as a chip. Falls back to an empty list
    (no chips render) for a blank field or anything that isn't a JSON array
    of strings, rather than raising — this includes pre-B12 pages whose
    field still holds the old free-form sentence, until they're republished.

    Tolerates a markdown code fence around the JSON (see
    :func:`_strip_markdown_fence`'s docstring — found in production
    2026-07-25: every real response came back fenced despite the prompt
    saying not to, which silently zeroed this widget on every page).
    """
    if not raw:
        return []
    try:
        parsed = json.loads(_strip_markdown_fence(raw))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


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

    # Rebanded 2026-07-23 (Plan 11 Track B12, daily-report redesign) from the
    # original six bands (0-4/5-12/13-17/18-40/41-60/61+) to these four fixed
    # display bands, each with a person glyph on the report page. No data
    # migration remaps existing rows onto the new bands (maintainer decision:
    # `DeidentifiedVisit.age_band` only ever stored the band, never the raw
    # age it was derived from, so an old band straddling a new boundary —
    # e.g. 41-60 spanning both new 19-55 and 56+ — cannot be split accurately
    # after the fact; the maintainer will instead delete pre-B12 ingests and
    # re-upload the source exports, which recomputes everything under the new
    # bands from scratch via `age_band_for`, below).
    AGE_BAND_0_5 = "0-5"
    AGE_BAND_6_18 = "6-18"
    AGE_BAND_19_55 = "19-55"
    AGE_BAND_56_PLUS = "56+"
    AGE_BAND_UNKNOWN = "unknown"
    AGE_BAND_CHOICES = [
        (AGE_BAND_0_5, "0–5"),
        (AGE_BAND_6_18, "6–18"),
        (AGE_BAND_19_55, "19–55"),
        (AGE_BAND_56_PLUS, "56+"),
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
    ``clinic_date`` is the natural key — one aggregate row per clinic-date.
    """

    clinic_date = models.DateField(db_index=True)

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
                fields=["clinic_date"],
                name="pipeline_dailyaggregate_unique_date",
            )
        ]

    def __str__(self):
        return f"Aggregate for {self.clinic_date}"

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
    than a dropdown submenu. (Plan 11 D8 later did add a "More" dropdown
    elsewhere in the nav, 2026-07-23's single-row header redesign — but this
    Reports/Camp-Reports merge predates it and was never revisited to use
    it, since the two-section page here already resolved the nav-crowding
    problem on its own.)
    """

    intro = RichTextField(blank=True, help_text="Optional intro copy for the archive.")
    daily_reports_intro = RichTextField(
        blank=True, help_text="Optional intro copy for the 'Daily reports' section."
    )
    camp_reports_intro = RichTextField(
        blank=True, help_text="Optional intro copy for the 'Camp reports' section."
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
        FieldPanel("daily_reports_intro"),
        FieldPanel("camp_reports_intro"),
    ]

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["pipeline.DailyReportPage"]

    def get_reports(self):
        """Published daily reports under this index, newest first.

        ``select_related("aggregate")`` (Plan 15 Track D2): the archive
        template reads each report's live figures off its ``aggregate`` FK, so
        without this the paginated list fires one extra query per report
        (N+1). The join fetches them in the same query as the pages.
        """
        return (
            DailyReportPage.objects.live()
            .child_of(self)
            .select_related("aggregate")
            .order_by("-report_date", "-pk")
        )

    # SVG chart geometry (Plan 13) — fixed marks, not configurable.
    FUNDING_MIX_WINDOW_DAYS = 30
    _CHART_WIDTH = 620
    _CHART_HEIGHT = 220
    _PAD_LEFT = 30
    _PAD_RIGHT = 10
    _PAD_TOP = 14
    _PAD_BOTTOM = 26
    _MAX_BAR_WIDTH = 24
    _STACK_GAP = 2  # surface gap between stacked segments
    _BAR_CORNER_RADIUS = 4
    _SUNDAY_WEEKDAY = 6  # date.weekday() — the clinic is closed Sundays
    # Minimum centre-to-centre spacing (viewBox units) between two date
    # labels. Measured against the widest rendered label ("27 Jun", ~30
    # units) with headroom for a longer translated month name — Plan 13's
    # Mon–Sat gap slots (see _funding_mix_slot_dates) mean consecutive-day
    # runs can now pack bars closer than a label is wide.
    _MIN_LABEL_SPACING = 40

    def get_funding_mix(self) -> dict:
        """Rolling 30-day Zakat-vs-Regular funding mix, as SVG geometry (Plan 13).

        Bar coordinates and path data are computed here rather than in the
        template or client JS, so the chart renders fully without
        JavaScript — mirrors ``circle-of-care.js``'s documented progressive-
        enhancement precedent ("the section renders fully without this
        script; this only adds the reveal"). ``funding-mix-chart.js`` only
        wires up the hover tooltip on top of this.

        Reuses the exact fields ``DailyReportPage.headline_stats`` already
        surfaces under the same labels: ``zakat_beneficiary_patients`` →
        "Zakat", ``paying_patients`` → "Regular" (models.py, above).

        Bars are positioned by each day's slot in the full calendar range
        (see ``_funding_mix_slot_dates``), not by its position in the query
        result — so a Monday–Saturday day with no report reserves a blank
        slot and renders as a visible gap, rather than the timeline
        silently compressing around it. A Sunday with no report gets no
        slot at all, since the clinic's closure that day is expected.
        """
        window_start = timezone.localdate() - timedelta(
            days=self.FUNDING_MIX_WINDOW_DAYS
        )
        today = timezone.localdate()
        rows_by_date = {
            row.clinic_date: row
            for row in DailyAggregate.objects.filter(clinic_date__gte=window_start)
        }
        if not rows_by_date:
            return {"bars": [], "ticks": []}

        end_date = max([today, *rows_by_date.keys()])
        slot_dates = self._funding_mix_slot_dates(rows_by_date, window_start, end_date)

        plot_width = self._CHART_WIDTH - self._PAD_LEFT - self._PAD_RIGHT
        plot_height = self._CHART_HEIGHT - self._PAD_TOP - self._PAD_BOTTOM

        max_total = max(row.total_visits for row in rows_by_date.values()) or 1
        tick_step = 5 if max_total <= 20 else 10
        max_value = ((max_total // tick_step) + 1) * tick_step

        def y_for(value):
            raw = self._PAD_TOP + plot_height - (value / max_value) * plot_height
            return round(raw, 2)

        baseline = y_for(0)
        slot_width = round(plot_width / len(slot_dates), 2)
        bar_width = round(min(self._MAX_BAR_WIDTH, slot_width * 0.6), 2)

        date_label_y = self._CHART_HEIGHT - 8

        bars = []
        last_label_x = None
        for i, slot_date in enumerate(slot_dates):
            row = rows_by_date.get(slot_date)
            if row is None:
                continue  # Mon–Sat, no report — leave the slot empty (a gap)
            bar = self._funding_mix_bar(
                row, i, slot_width, bar_width, baseline, y_for, date_label_y
            )
            # Gap slots let real bars pack closer together than a date
            # label is wide (see _MIN_LABEL_SPACING) — thin colliding
            # labels rather than let them overlap. Every bar still gets
            # its hit-tooltip and its row in the table below, so no date
            # is actually hidden, just its always-visible axis text.
            bar["show_label"] = (
                last_label_x is None
                or bar["label_x"] - last_label_x >= self._MIN_LABEL_SPACING
            )
            if bar["show_label"]:
                last_label_x = bar["label_x"]
            bars.append(bar)
        ticks = [
            {"value": t, "y": y_for(t), "label_y": y_for(t) + 3}
            for t in range(0, max_value + 1, tick_step)
        ]
        return {
            "bars": bars,
            "ticks": ticks,
            "chart_width": self._CHART_WIDTH,
            "chart_height": self._CHART_HEIGHT,
            "grid_x1": self._PAD_LEFT,
            "grid_x2": self._CHART_WIDTH - self._PAD_RIGHT,
            "axis_label_x": self._PAD_LEFT - 6,
        }

    def _funding_mix_slot_dates(self, rows_by_date, start, end):
        """Ordered list of dates that get a chart slot between ``start``
        and ``end`` inclusive.

        A Sunday with no ``DailyAggregate`` row gets no slot at all — the
        clinic is closed Sundays by design, so its absence is expected, not
        a gap. Every other day in range gets a slot regardless of whether
        it has data; the caller renders a bar for slots with data and
        leaves the rest empty, which is what shows up as a gap in the
        chart. A Sunday that does have a row (an exceptional open day) is
        kept, same as any other day with data.
        """
        dates = []
        d = start
        while d <= end:
            if d in rows_by_date or d.weekday() != self._SUNDAY_WEEKDAY:
                dates.append(d)
            d += timedelta(days=1)
        return dates

    def _funding_mix_bar(
        self, row, index, slot_width, bar_width, baseline, y_for, date_label_y
    ):
        cx = round(self._PAD_LEFT + slot_width * index + slot_width / 2, 2)
        x = round(cx - bar_width / 2, 2)
        zakat_top = y_for(row.zakat_beneficiary_patients)
        total_top = y_for(row.zakat_beneficiary_patients + row.paying_patients)

        if row.zakat_beneficiary_patients == 0:
            # Solo regular segment, resting on the baseline — mirrors the
            # solo-zakat case below. Without this, the regular segment's
            # base would be offset by _STACK_GAP above a degenerate
            # zero-height zakat segment, floating it off the baseline.
            segments = [
                {
                    "path": self._rounded_top_path(x, total_top, bar_width, baseline),
                    "css_class": "ri-funding-mix__bar--regular",
                }
            ]
        elif row.paying_patients == 0:
            segments = [
                {
                    "path": self._rounded_top_path(x, zakat_top, bar_width, baseline),
                    "css_class": "ri-funding-mix__bar--zakat",
                }
            ]
        else:
            regular_base = zakat_top - self._STACK_GAP
            segments = [
                {
                    "path": self._square_path(x, zakat_top, bar_width, baseline),
                    "css_class": "ri-funding-mix__bar--zakat",
                },
                {
                    "path": self._rounded_top_path(
                        x, total_top, bar_width, regular_base
                    ),
                    "css_class": "ri-funding-mix__bar--regular",
                },
            ]

        return {
            "date": row.clinic_date,
            "zakat": row.zakat_beneficiary_patients,
            "regular": row.paying_patients,
            "total": row.total_visits,
            "segments": segments,
            "label_x": cx,
            "label_y": date_label_y,
            "hit_x": cx - slot_width / 2,
            "hit_width": slot_width,
        }

    def _rounded_top_path(self, x, y_top, width, y_base):
        r = min(self._BAR_CORNER_RADIUS, width / 2, max(0, y_base - y_top))
        return (
            f"M {x} {y_base} L {x} {y_top + r} Q {x} {y_top} {x + r} {y_top} "
            f"L {x + width - r} {y_top} "
            f"Q {x + width} {y_top} {x + width} {y_top + r} "
            f"L {x + width} {y_base} Z"
        )

    def _square_path(self, x, y_top, width, y_base):
        x_end, y_end = x + width, y_top
        return f"M {x} {y_base} L {x} {y_top} L {x_end} {y_end} L {x_end} {y_base} Z"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["reports"] = paginate_archive(request, self.get_reports())
        context["funding_mix"] = self.get_funding_mix()
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
    # Split into three per-category fields (Plan 14, 2026-07-24, maintainer
    # decision) — replaces the single `freetext_summary` field. Each is an
    # independent, independently-editable restatement of that category's
    # already-collected free-text entries (see
    # `apps.pipeline.freetext.collect_freetext_entries_by_group` and
    # `_group_for_visit` for the male-adult/female-adult/children split and
    # the "under 14" age-band approximation it makes). Blank if the AI call
    # failed/was skipped, or if that category had no matching visits that
    # day.
    freetext_summary_male_adults = models.TextField(
        blank=True,
        help_text="AI-drafted summary of today's free-text clinical columns "
        "for male adult patients (Plan 14). Blank if the AI call failed, "
        "was skipped, or no male adult visits were recorded that day.",
    )
    freetext_summary_female_adults = models.TextField(
        blank=True,
        help_text="AI-drafted summary of today's free-text clinical columns "
        "for female adult patients (Plan 14). Blank if the AI call failed, "
        "was skipped, or no female adult visits were recorded that day.",
    )
    freetext_summary_children = models.TextField(
        blank=True,
        help_text="AI-drafted summary of today's free-text clinical columns "
        "for child patients (Plan 14; age bands 0-5 and 6-18, an "
        'approximation of "under 14" — see freetext.py\'s Plan 14 '
        "grounding note). Blank if the AI call failed, was skipped, or no "
        "child visits were recorded that day.",
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
        FieldPanel("freetext_summary_male_adults"),
        FieldPanel("freetext_summary_female_adults"),
        FieldPanel("freetext_summary_children"),
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

        Redesigned 2026-07-23 (Plan 11 Track B12, maintainer decision): drops
        "New patients" (``aggregate.new_patients`` stays on the model — just
        no longer surfaced here) in favour of the Zakat/Regular split, which
        used to live only in the "Breakdown" cards below.
        """
        return [
            {"value": str(self.aggregate.total_visits), "label": _("Patients seen")},
            {
                "value": str(self.aggregate.zakat_beneficiary_patients),
                "label": _("Zakat"),
            },
            {"value": str(self.aggregate.paying_patients), "label": _("Regular")},
        ]

    def get_context(self, request, *args, **kwargs):
        """Build the redesigned page's context (Plan 11 Track B12, 2026-07-23).

        "By department" and "By diagnosis category" are intentionally not
        surfaced: the real TKC parser never populates `department`
        (parser_tkc_daily_v1's own docstring), and diagnosis category was
        dropped from this page entirely per the redesign (maintainer
        decision). Both remain computed at the model layer
        (`category_counts`) — this page just stops rendering them.
        """
        context = super().get_context(request, *args, **kwargs)
        agg = self.aggregate
        context["aggregate"] = agg

        # Gender bars — percentage is presentation only; counts stay
        # authoritative (rendered alongside every bar).
        gender_counts = {
            _("Female"): agg.female_patients,
            _("Male"): agg.male_patients,
        }
        gender_max = max(gender_counts.values()) or 1
        context["gender_rows"] = [
            {"label": label, "count": count, "pct": round(count / gender_max * 100)}
            for label, count in gender_counts.items()
        ]

        # Four fixed display bands (Plan 11 Track B12 age-band remap).
        by_age = agg.category_counts.get("by_age_band", {})
        context["age_bands"] = [
            {
                "label": "0–5",
                "count": by_age.get(DeidentifiedVisit.AGE_BAND_0_5, 0),
                "icon_template": "pipeline/age_icons/_age_0_5.html",
            },
            {
                "label": "6–18",
                "count": by_age.get(DeidentifiedVisit.AGE_BAND_6_18, 0),
                "icon_template": "pipeline/age_icons/_age_6_18.html",
            },
            {
                "label": "19–55",
                "count": by_age.get(DeidentifiedVisit.AGE_BAND_19_55, 0),
                "icon_template": "pipeline/age_icons/_age_19_55.html",
            },
            {
                "label": "56+",
                "count": by_age.get(DeidentifiedVisit.AGE_BAND_56_PLUS, 0),
                "icon_template": "pipeline/age_icons/_age_56_plus.html",
            },
        ]

        context["report_date"] = self.report_date
        context["empty_columns"] = _parse_empty_columns_flag(self.empty_columns_flag)
        return context

    class Meta:
        verbose_name = "Daily report"


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
    ``DailyAggregate``, unlike those audit models. None of the five call
    sites in ``apps.pipeline.ai`` share a *common* triggering record to hang
    one off: ``draft_daily_summary_sentence`` has a ``DailyAggregate``,
    ``draft_monthly_newsletter_body`` runs before its caller's
    ``NewsletterDraftRun`` row even exists, ``draft_newsletter_prose``
    (presently unused in production — see its call site's comment) takes an
    in-memory ``ClinicAggregate`` that isn't a persisted row at all, and
    ``draft_freetext_summary``/``draft_empty_columns_flag`` (B8/B9) take a
    bare ``clinic_date`` plus a dict, not a model instance. Adding a FK to
    only some of the five would misleadingly suggest the others have one
    too; ``call_site`` already identifies which caller produced a row. Add a
    nullable FK later if a real cross-referencing need shows up.
    """

    CALL_SITE_NEWSLETTER_PROSE = "newsletter_prose"
    CALL_SITE_DAILY_SUMMARY = "daily_summary"
    CALL_SITE_MONTHLY_NEWSLETTER = "monthly_newsletter"
    CALL_SITE_FREETEXT_SUMMARY = "freetext_summary"
    CALL_SITE_EMPTY_COLUMNS_FLAG = "empty_columns_flag"
    CALL_SITE_CHOICES = [
        (
            CALL_SITE_NEWSLETTER_PROSE,
            "Newsletter prose (draft_newsletter_prose — currently unused)",
        ),
        (CALL_SITE_DAILY_SUMMARY, "Daily report summary sentence"),
        (CALL_SITE_MONTHLY_NEWSLETTER, "Monthly newsletter drafting"),
        (CALL_SITE_FREETEXT_SUMMARY, "Free-text summary (B8)"),
        (CALL_SITE_EMPTY_COLUMNS_FLAG, "Empty-columns flag (B9)"),
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
