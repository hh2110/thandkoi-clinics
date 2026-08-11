"""The parser contract and registry (Plan 08).

CLAUDE.md invariant #1, made structural for *this* module: a parser's
``parse()`` reads a raw export and returns only a :class:`ParsedExport` —
de-identified rows plus a content hash of those rows. There is no code path
here that returns, logs, or persists a raw cell value from an identifying
column; direct identifiers (name, father's/husband's name, full address, DOB,
raw diagnosis text) are read only as short-lived locals inside ``parse()``
and are never attached to a :class:`ParsedVisitRow`.

Adding a new export format is a new :class:`BaseExportParser` subclass
registered with :class:`ParserRegistry` — no change to this module or to the
ingest pipeline (``apps.pipeline.ingest``). Agentic/model-assisted onboarding
of new formats is explicitly deferred (README "Out of scope", 2026-07-19);
every parser here is hand-written and code-reviewed like the rest of the app.
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import BinaryIO

from apps.pipeline.models import DeidentifiedVisit


class ExportParseError(Exception):
    """A parser recognised the file but cannot safely parse it.

    Raised from ``parse()`` *before* anything is persisted, with a message
    that is safe to show the uploading admin verbatim (so it must never
    contain a cell value — only structural facts about the file). The upload
    view catches it around ``ingest_export`` and renders the message; parse
    always completes before persistence begins, so "nothing was saved" holds.
    """


# --- Column-lookup helper shared by every concrete parser -------------------


def header_index(header_row: tuple, column_name: str) -> int | None:
    """Find a column by (case-insensitive) header name, or return ``None``.

    Shared by every concrete parser so a column that shifts position between
    export runs (a common spreadsheet reality) doesn't break parsing. Started
    as a private helper in the Plan 02 prototype aggregator (deleted
    2026-07-25), made public here so real parsers reuse one implementation.
    """
    wanted = column_name.strip().lower()
    for index, cell in enumerate(header_row):
        if cell is not None and str(cell).strip().lower() == wanted:
            return index
    return None


# --- Service revenue vocabulary (Plan 22 D1) --------------------------------
#
# The five services the clinic export's fee columns carry, in the display
# order Plan 16's design handoff fixed. Defined here rather than in the one
# parser that reads them because three layers have to agree on the same keys:
# the parser producing them, ``apps.pipeline.ingest`` aggregating them into
# ``DailyAggregate.service_revenue``, and ``apps.pipeline.dashboard`` reading
# them back out. A key that exists in only two of the three is a silently
# dropped service.
#
# ``laboratory`` is deliberately not ``lab``: the export's header is "Lab Fee
# (PKR)" but the handoff's display label is "Laboratory", and the stored key
# follows the domain vocabulary rather than the spreadsheet's abbreviation.
SERVICE_REGISTRATION = "registration"
SERVICE_CONSULTATION = "consultation"
SERVICE_PHARMACY = "pharmacy"
SERVICE_LABORATORY = "laboratory"
SERVICE_ULTRASOUND = "ultrasound"

#: Canonical display order (Plan 16 handoff), and the only keys that may
#: appear in ``DailyAggregate.service_revenue``.
SERVICE_KEYS = (
    SERVICE_REGISTRATION,
    SERVICE_CONSULTATION,
    SERVICE_PHARMACY,
    SERVICE_LABORATORY,
    SERVICE_ULTRASOUND,
)

#: ``ParsedVisitRow`` / ``DeidentifiedVisit`` field name per service key.
SERVICE_FEE_FIELDS = {key: f"{key}_fee" for key in SERVICE_KEYS}

#: The three payment buckets a service's revenue splits across (Plan 22 D3).
#: ``unknown`` is first-class, mirroring the existing
#: ``DailyAggregate.unknown_payment_type_patients`` — money on a row whose
#: ``Status`` is neither "zakat" nor "regular" is recorded as unattributed
#: rather than guessed into one of the other two or dropped.
BUCKET_REGULAR = "regular"
BUCKET_ZAKAT = "zakat"
BUCKET_UNKNOWN = "unknown"
REVENUE_BUCKETS = (BUCKET_REGULAR, BUCKET_ZAKAT, BUCKET_UNKNOWN)


def coerce_fee(value) -> int:
    """A fee cell as whole PKR — 0 for blank, non-numeric or negative input.

    Excel hands numeric cells back as floats (``20.0``, not ``20``) and
    occasionally as strings when the column has mixed formatting, so this
    normalises both. Rounds rather than truncates: ``19.999`` from a
    float-rounding artifact is 20 rupees, not 19.

    Never raises. A malformed fee cell degrades to "no fee recorded" for that
    one service on that one row, which is the same thing an export predating
    the fee columns produces — the alternative, failing the parse, would
    block a whole day's upload over one bad cell. Values that don't
    reconcile are surfaced by the ingest-time ``Total Paid`` check instead
    (Plan 22 D5), which warns without blocking.
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        # bool is an int subclass; a checkbox cell is not a fee.
        return 0
    if isinstance(value, (int, float)):
        number = value
    else:
        text = str(value).strip().replace(",", "")
        if not text:
            return 0
        # Tolerate a currency prefix/suffix typed into an otherwise numeric
        # column ("PKR 250", "250/-").
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return 0
        number = float(match.group())
    if number != number or number in (float("inf"), float("-inf")):  # NaN/inf
        return 0
    return max(0, round(number))


# --- De-identification helpers shared by every concrete parser --------------


def age_band_for(*, dob: date | None, age_years: int | None, on: date) -> str:
    """Band an age (from a DOB or a raw age value) — never the exact value.

    Accepts either a date of birth (preferred — banded relative to ``on``,
    the visit date) or an already-computed age in years (some exports give
    age directly, not DOB). Returns
    :data:`DeidentifiedVisit.AGE_BAND_UNKNOWN` if neither is usable, rather
    than guessing.

    Rebanded 2026-07-23 (Plan 11 Track B12, daily-report redesign) from the
    original six bands to four fixed display bands — see
    ``DeidentifiedVisit.AGE_BAND_*``'s decision comment for why this isn't
    also a data migration remapping already-persisted rows.
    """
    if age_years is None and dob is not None:
        age_years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    if age_years is None or age_years < 0:
        return DeidentifiedVisit.AGE_BAND_UNKNOWN
    if age_years <= 5:
        return DeidentifiedVisit.AGE_BAND_0_5
    if age_years <= 18:
        return DeidentifiedVisit.AGE_BAND_6_18
    if age_years <= 55:
        return DeidentifiedVisit.AGE_BAND_19_55
    return DeidentifiedVisit.AGE_BAND_56_PLUS


def normalise_sex(raw: str | None) -> str:
    """Map a free-text sex/gender value onto the fixed 3-value set."""
    value = (raw or "").strip().lower()
    if value in {"m", "male"}:
        return DeidentifiedVisit.SEX_MALE
    if value in {"f", "female"}:
        return DeidentifiedVisit.SEX_FEMALE
    return DeidentifiedVisit.SEX_OTHER_UNKNOWN


# Hand-written keyword → fixed-category mapping (maintainer decision, PR #15
# post-review: diagnosis is confirmed free text in the source clinic
# software). Matched as whole words/phrases against the lower-cased, stripped
# raw value (see ``diagnosis_category_for``), not user-editable at runtime and
# not agentic inference — reviewed in code like the rest of the parser. Extend
# this table, don't invent a new mechanism, when a new common diagnosis needs
# its own category.
#
# Word-boundary matching (Plan 15 Track D1): a bare substring match mis-filed
# any diagnosis that merely *contained* a keyword inside a longer, unrelated
# word — "heartburn" tripped "heart" (Cardiac) when it is Gastrointestinal,
# "cold sore" tripped "cold" (Respiratory) when it is Dermatological. Matching
# each keyword as a whole word (and longest-phrase-first, so "cold sore" wins
# over "cold") fixes those. Two former substring-*prefix* keywords had to be
# spelled out as whole words to keep matching once boundaries are enforced:
# "pregnan" (never a word on its own) became "pregnant"/"pregnancy", and
# "gastro" gained explicit "gastroenteritis"/"gastritis" siblings.
_DIAGNOSIS_KEYWORDS: dict[str, str] = {
    "hypertension": DeidentifiedVisit.DIAGNOSIS_HYPERTENSION,
    "high bp": DeidentifiedVisit.DIAGNOSIS_HYPERTENSION,
    "htn": DeidentifiedVisit.DIAGNOSIS_HYPERTENSION,
    "diabetes": DeidentifiedVisit.DIAGNOSIS_DIABETES,
    "sugar": DeidentifiedVisit.DIAGNOSIS_DIABETES,
    "cough": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "cold": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "flu": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "asthma": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "pneumonia": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "chest infection": DeidentifiedVisit.DIAGNOSIS_RESPIRATORY,
    "diarrhea": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "diarrhoea": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "vomiting": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "gastro": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "gastroenteritis": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "gastritis": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "heartburn": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "abdominal pain": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "joint pain": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "back pain": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "arthritis": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "musculoskeletal": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "skin": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "rash": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "allergy": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "cold sore": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "antenatal": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "pregnant": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "pregnancy": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "postnatal": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "child health": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "cardiac": DeidentifiedVisit.DIAGNOSIS_CARDIAC,
    "heart": DeidentifiedVisit.DIAGNOSIS_CARDIAC,
    "chest pain": DeidentifiedVisit.DIAGNOSIS_CARDIAC,
    "infection": DeidentifiedVisit.DIAGNOSIS_INFECTIOUS,
    "fever": DeidentifiedVisit.DIAGNOSIS_INFECTIOUS,
    "malaria": DeidentifiedVisit.DIAGNOSIS_INFECTIOUS,
    "typhoid": DeidentifiedVisit.DIAGNOSIS_INFECTIOUS,
}

#: ``_DIAGNOSIS_KEYWORDS`` compiled to whole-word/phrase patterns, ordered
#: longest-keyword-first so a specific multi-word term is tried before a
#: shorter one nested inside it (e.g. "cold sore" before "cold", "chest
#: infection"/"chest pain" before any bare "chest"). Built once at import.
_DIAGNOSIS_KEYWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(keyword)}\b"), category)
    for keyword, category in sorted(
        _DIAGNOSIS_KEYWORDS.items(), key=lambda item: -len(item[0])
    )
]


def diagnosis_category_for(raw_diagnosis: str | None) -> str:
    """Map a raw free-text diagnosis to a fixed category — never store the text.

    Each keyword is matched as a whole word/phrase (Plan 15 Track D1), so a
    keyword nested inside an unrelated longer word no longer mis-files the
    visit. The raw value is read only as this function's local ``value`` and
    is never returned, logged, or attached to a row — only the resulting
    fixed category crosses back to the caller.
    """
    value = (raw_diagnosis or "").strip().lower()
    for pattern, category in _DIAGNOSIS_KEYWORD_PATTERNS:
        if pattern.search(value):
            return category
    return DeidentifiedVisit.DIAGNOSIS_OTHER


# --- The parser contract -----------------------------------------------------


@dataclass(frozen=True)
class ParsedVisitRow:
    """One de-identified visit — the only row shape a parser may produce.

    Every field is already de-identified/coarsened by the parser that built
    it; there is no field here that could carry a direct identifier.

    The seven free-text fields below (default ``""``, so an existing parser
    that doesn't populate them — ``parser_clinic_v1`` — needs no change) are a
    later, narrower addition (Plan 11 Track B8/B9, maintainer decision
    2026-07-23): unlike everything above, which is a fixed category or a
    coarsened value, these carry the *raw* free text from the source export.
    That's only safe because the maintainer confirmed the clinic software's
    data-entry UI structurally cannot accept a patient identifier in these
    specific columns — see ``apps.pipeline.freetext``'s module docstring for
    the full grounding note. A new free-text column added later needs that
    same question asked explicitly, not assumed by analogy.
    """

    visit_date: date
    department: str
    age_band: str
    sex: str
    location: str
    diagnosis_category: str
    is_new_patient: bool | None
    is_zakat_beneficiary: bool | None
    presenting_complaints: str = ""
    investigation: str = ""
    provisional_diagnosis_text: str = ""
    prescribed_medicine: str = ""
    clinical_notes: str = ""
    diet_and_drug_compliance: str = ""
    plan_notes: str = ""

    # --- Plan 22: per-service fees, whole PKR (added 2026-08-11) -----------
    #
    # Defaulted to 0 like the free-text fields above are defaulted to "", so
    # a parser that doesn't populate them needs no change — both
    # ``parser_clinic_v1`` and any clinic export predating the software
    # update that added these columns produce rows of zeros rather than
    # failing. Unlike the free-text fields, these carry no text at all: a fee
    # is a de-identified number, so this addition raises no new question
    # under privacy invariant #1.
    #
    # ``total_paid`` is the export's own per-row total, kept **only** for the
    # ingest-time reconciliation check (Plan 22 D5). It is never summed into
    # a published figure — the per-service fees are the source of truth.
    registration_fee: int = 0
    consultation_fee: int = 0
    pharmacy_fee: int = 0
    laboratory_fee: int = 0
    ultrasound_fee: int = 0
    total_paid: int = 0

    @property
    def service_fees(self) -> dict[str, int]:
        """``{service_key: fee}`` for the five services, in display order."""
        return {key: getattr(self, field) for key, field in SERVICE_FEE_FIELDS.items()}

    def _canonical_tuple(self) -> tuple:
        # Includes the seven Plan 11 Track B8/B9 free-text fields below —
        # this went back and forth during code-review-tc, so the reasoning
        # is recorded here rather than left to be re-litigated:
        #
        # An earlier revision excluded these fields, reasoning that every
        # IngestRun.content_hash already persisted in production was computed
        # before they existed, so including them would make a byte-identical
        # re-upload of an already-ingested date hash differently and get
        # reclassified STATUS_REPLACED instead of STATUS_DUPLICATE. That's
        # true, but a second review pass found the exclusion's real cost is
        # worse and permanent: a staff member correcting only a free-text
        # column (Doctor's Notes, Prescribed Medicine, etc.) on a genuine
        # re-upload — the actual workflow B8/B9 exists to support — would
        # forever hash identically to the uncorrected version and be
        # silently skipped as a no-op duplicate, with the stale AI drafts
        # never regenerated.
        #
        # Decision: include them. The one-time production transition this
        # causes is not a misclassification — before this deploy, free text
        # was never parsed or persisted at all, so an unchanged file's old
        # hash correctly reflected "nothing new to extract"; after this
        # deploy, that same file yields genuinely new persistable
        # information (the free text), so the first re-upload of any
        # already-ingested date correctly reclassifying as a replace (and
        # backfilling that date's free-text data + drafts) is the desired
        # behavior, not a bug. Every subsequent re-upload of that same file
        # then hashes identically going forward, same as before.
        return (
            self.visit_date.isoformat(),
            self.department,
            self.age_band,
            self.sex,
            self.location,
            self.diagnosis_category,
            self.is_new_patient,
            self.is_zakat_beneficiary,
            self.presenting_complaints,
            self.investigation,
            self.provisional_diagnosis_text,
            self.prescribed_medicine,
            self.clinical_notes,
            self.diet_and_drug_compliance,
            self.plan_notes,
            # Plan 22 D7 — the five fee fields join the hash, and the
            # reasoning is exactly the B8/B9 one above, so it is followed
            # rather than re-argued: excluding them would mean a genuine
            # re-upload correcting only a fee cell hashes identically to the
            # uncorrected file and is silently skipped as a duplicate, with
            # that date's revenue never corrected. Including them means the
            # first re-upload of an already-ingested date reclassifies
            # STATUS_REPLACED once and backfills its revenue — correct, since
            # before this change the file yielded no revenue to persist at
            # all. Subsequent re-uploads hash identically again.
            #
            # `total_paid` is deliberately NOT here: it is a reconciliation
            # input (D5), never persisted and never published, so letting it
            # move the hash would reclassify a re-upload over a value that
            # changes nothing downstream.
            self.registration_fee,
            self.consultation_fee,
            self.pharmacy_fee,
            self.laboratory_fee,
            self.ultrasound_fee,
        )


@dataclass(frozen=True)
class ParsedExport:
    """The only thing a parser hands back to the ingest pipeline.

    ``rows`` holds every de-identified visit from the export, across however
    many clinic-dates it covers; ``apps.pipeline.ingest`` groups them by date
    and computes a per-date content hash (see
    :func:`content_hash_for_rows`) before persisting.
    """

    rows: list[ParsedVisitRow]


def _sort_key(tup: tuple) -> tuple:
    """Order-safe key for a ``_canonical_tuple()``.

    ``is_new_patient``/``is_zakat_beneficiary`` are ``bool | None`` — plain
    Python can't compare ``None`` against ``True``/``False`` (``TypeError``),
    so a real day mixing Zakat/Regular/blank ``Status`` values (an entirely
    normal day, not an edge case) crashed here on upload. Each element is
    wrapped as ``(0, "")`` for ``None`` or ``(1, value)`` otherwise, so same-
    position values are only ever compared within one type.
    """
    return tuple((0, "") if value is None else (1, value) for value in tup)


def content_hash_for_rows(rows: list[ParsedVisitRow]) -> str:
    """A deterministic fingerprint of a set of de-identified rows.

    Order-independent (rows are sorted before hashing) so the same data in a
    different row order still hashes identically — re-uploading the same
    corrected export should be recognised as unchanged, not as a spurious
    diff. This hashes the *de-identified* rows, never raw bytes: it is a
    semantic fingerprint of the parsed content, not a checksum of the file.
    """
    canonical = sorted((row._canonical_tuple() for row in rows), key=_sort_key)
    payload = json.dumps(canonical, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BaseExportParser(ABC):
    """Contract every concrete export-format parser implements.

    ``format_key`` is the stable identifier stored on ``IngestRun`` and used
    as the admin's dropdown value; ``label`` is the human-readable name shown
    in the upload form.
    """

    format_key: str
    label: str

    @abstractmethod
    def sniff(self, workbook) -> bool:
        """Best-effort check: does ``workbook`` look like this format?

        ``workbook`` is an already-opened ``openpyxl`` workbook (read-only).
        Used only to suggest/confirm the admin's explicit dropdown choice
        (decision table, Plan 08) — never to silently auto-select a parser.
        """

    @abstractmethod
    def parse(self, buffer: BinaryIO) -> ParsedExport:
        """Read ``buffer`` (an in-memory byte stream) and return de-identified rows.

        Must never write ``buffer`` (or anything derived from it) to disk, a
        model, or a log — see this module's docstring.
        """


class ParserRegistry:
    """Maps ``format_key -> parser``. Parsers self-register on import.

    Concrete parser modules call :meth:`register` at import time (see
    ``apps.pipeline.apps.PipelineConfig.ready``, which imports them); the
    upload view lists :meth:`choices` in its format dropdown.
    """

    _parsers: dict[str, BaseExportParser] = {}

    @classmethod
    def register(cls, parser: BaseExportParser) -> BaseExportParser:
        cls._parsers[parser.format_key] = parser
        return parser

    @classmethod
    def get(cls, format_key: str) -> BaseExportParser:
        try:
            return cls._parsers[format_key]
        except KeyError:
            raise KeyError(
                f"No parser registered for format_key={format_key!r}"
            ) from None

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """``(format_key, label)`` pairs, for the upload form's dropdown."""
        return [(key, parser.label) for key, parser in cls._parsers.items()]

    @classmethod
    def sniff_all(cls, workbook) -> list[str]:
        """``format_key``s whose parser's ``sniff()`` matches — a hint, not a choice."""
        return [key for key, parser in cls._parsers.items() if parser.sniff(workbook)]
