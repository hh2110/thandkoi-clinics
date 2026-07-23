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
    export runs (a common spreadsheet reality) doesn't break parsing — mirrors
    ``apps.pipeline.aggregation._header_index``'s same idiom (Plan 02), made
    public here so real parsers reuse one implementation.
    """
    wanted = column_name.strip().lower()
    for index, cell in enumerate(header_row):
        if cell is not None and str(cell).strip().lower() == wanted:
            return index
    return None


# --- De-identification helpers shared by every concrete parser --------------


def age_band_for(*, dob: date | None, age_years: int | None, on: date) -> str:
    """Band an age (from a DOB or a raw age value) — never the exact value.

    Accepts either a date of birth (preferred — banded relative to ``on``,
    the visit date) or an already-computed age in years (some exports give
    age directly, not DOB). Returns
    :data:`DeidentifiedVisit.AGE_BAND_UNKNOWN` if neither is usable, rather
    than guessing.
    """
    if age_years is None and dob is not None:
        age_years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    if age_years is None or age_years < 0:
        return DeidentifiedVisit.AGE_BAND_UNKNOWN
    if age_years <= 4:
        return DeidentifiedVisit.AGE_BAND_0_4
    if age_years <= 12:
        return DeidentifiedVisit.AGE_BAND_5_12
    if age_years <= 17:
        return DeidentifiedVisit.AGE_BAND_13_17
    if age_years <= 40:
        return DeidentifiedVisit.AGE_BAND_18_40
    if age_years <= 60:
        return DeidentifiedVisit.AGE_BAND_41_60
    return DeidentifiedVisit.AGE_BAND_61_PLUS


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
# software). Matched by substring against the lower-cased, stripped raw
# value. Not user-editable at runtime and not agentic inference — reviewed
# in code like the rest of the parser. Extend this table, don't invent a new
# mechanism, when a new common diagnosis needs its own category.
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
    "abdominal pain": DeidentifiedVisit.DIAGNOSIS_GASTROINTESTINAL,
    "joint pain": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "back pain": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "arthritis": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "musculoskeletal": DeidentifiedVisit.DIAGNOSIS_MUSCULOSKELETAL,
    "skin": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "rash": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "allergy": DeidentifiedVisit.DIAGNOSIS_DERMATOLOGICAL,
    "antenatal": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
    "pregnan": DeidentifiedVisit.DIAGNOSIS_MATERNAL_CHILD,
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


def diagnosis_category_for(raw_diagnosis: str | None) -> str:
    """Map a raw free-text diagnosis to a fixed category — never store the text.

    The raw value is read only as this function's local ``value`` and is
    never returned, logged, or attached to a row — only the resulting fixed
    category crosses back to the caller.
    """
    value = (raw_diagnosis or "").strip().lower()
    for keyword, category in _DIAGNOSIS_KEYWORDS.items():
        if keyword in value:
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

    def _canonical_tuple(self) -> tuple:
        # Deliberately excludes the seven Plan 11 Track B8/B9 free-text
        # fields below (maintainer decision 2026-07-23, found by
        # code-review-tc): this tuple feeds content_hash_for_rows(), and
        # every IngestRun.content_hash already persisted in production was
        # computed before these fields existed. Including them would change
        # the hash for a byte-identical re-upload of an already-ingested
        # date, misclassifying it as STATUS_REPLACED instead of
        # STATUS_DUPLICATE and needlessly re-triggering all three AI calls.
        # If free text ever needs to participate in dedup detection, that's
        # a deliberate follow-up, not an incidental side effect of adding
        # the fields.
        return (
            self.visit_date.isoformat(),
            self.department,
            self.age_band,
            self.sex,
            self.location,
            self.diagnosis_category,
            self.is_new_patient,
            self.is_zakat_beneficiary,
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


def content_hash_for_rows(rows: list[ParsedVisitRow]) -> str:
    """A deterministic fingerprint of a set of de-identified rows.

    Order-independent (rows are sorted before hashing) so the same data in a
    different row order still hashes identically — re-uploading the same
    corrected export should be recognised as unchanged, not as a spurious
    diff. This hashes the *de-identified* rows, never raw bytes: it is a
    semantic fingerprint of the parsed content, not a checksum of the file.
    """
    canonical = sorted(row._canonical_tuple() for row in rows)
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
