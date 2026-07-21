"""AI drafting — de-identified aggregates in, prose out.

This module enforces privacy invariants #2 and #3 (CLAUDE.md):

* **#2 — never send patient data to a model.** ``build_prompt_payload`` is built
  from a :class:`~apps.pipeline.aggregation.ClinicAggregate`, which by
  construction holds only counts. There is no code path here that can reach a
  raw patient row.
* **#3 — numbers are deterministic.** The model is asked to write prose *around*
  numbers that were already computed in Python; it is explicitly told not to
  invent or restate figures. The authoritative numbers are rendered from the
  aggregate (see :mod:`apps.pipeline.rendering`), not parsed back out of the
  model's prose.

The Anthropic client is dependency-injected into :func:`draft_newsletter_prose`
so tests pass a canned stub and the real API is never called from the test
suite. :func:`get_anthropic_client` builds the real client for production use
and is deliberately never exercised by tests (a conftest guard makes calling it
raise).
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from apps.pipeline.aggregation import ClinicAggregate
from apps.pipeline.models import DailyAggregate

# Direct identifiers that may appear as columns in a raw export. They are read
# for tallying (see aggregation.py) but must NEVER appear in an AI payload. The
# guardrail test asserts none of these names — or their values — reach the
# client. Extend this list as new export formats are onboarded (Plan 08).
PATIENT_IDENTIFYING_COLUMNS = frozenset(
    {
        "patient_name",
        "name",
        "first_name",
        "last_name",
        "father_name",
        "mrn",
        "medical_record_number",
        "cnic",
        "national_id",
        "phone",
        "mobile",
        "address",
        "email",
        "date_of_birth",
        "dob",
    }
)

# Model used for newsletter drafting (see CLAUDE.md → Stack).
DRAFTING_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = (
    "You are drafting prose for a not-for-profit clinic's public report. "
    "You are given de-identified aggregate counts only. Write warm, factual "
    "narrative around these numbers. Do NOT invent, estimate, or restate any "
    "statistic from memory — every number the reader sees is inserted by our "
    "code, not by you. Never ask for or refer to individual patients."
)


class _AnthropicLike(Protocol):
    """Minimal shape of the Anthropic client used here (real or stub)."""

    messages: Any


def build_prompt_payload(aggregate: ClinicAggregate) -> dict[str, Any]:
    """Build the exact payload handed to the model — aggregates only.

    Everything in the returned dict comes from ``aggregate.as_dict()``; there is
    no field here that could carry a patient identifier.
    """
    return {
        "model": DRAFTING_MODEL,
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Write the narrative for today's clinic report using only "
                    "these de-identified aggregate figures:\n"
                    + json.dumps(aggregate.as_dict(), sort_keys=True, indent=2)
                ),
            }
        ],
    }


def draft_newsletter_prose(aggregate: ClinicAggregate, client: _AnthropicLike) -> str:
    """Ask the (injected) client for prose around the de-identified aggregate.

    Returns the model's text only. The numbers a reader ultimately sees are
    rendered from ``aggregate`` in :mod:`apps.pipeline.rendering`; this prose is
    treated as narrative, never as a source of figures.
    """
    payload = build_prompt_payload(aggregate)
    response = client.messages.create(**payload)
    return response.content[0].text


# --- Plan 08: the daily report's one AI-written summary sentence -----------
#
# CLAUDE.md invariant #4 was amended (2026-07-19, maintainer decision) with
# one narrow exception scoped to exactly this call — see
# ".claude/plans/08-data-pipeline.md" → "The AI summary sentence — and why
# it's allowed to auto-publish". Three properties make the exception safe:
#
# 1. Fixed template, not free-form drafting — the model only phrases numbers
#    it's handed, never invents, contextualises, or compares.
# 2. The payload is `DailyAggregate.as_dict()` only — structurally incapable
#    of holding a row-level value (see that method's own docstring).
# 3. Never blocks the deterministic content — any failure, timeout, or
#    sanity-check miss (empty / too long) falls back to `None`, and the
#    caller (apps.pipeline.report_publishing.publish_daily_report) still
#    auto-publishes the page's numbers with no sentence.

# Model used for the daily summary sentence (see CLAUDE.md → Stack): a short,
# fixed-template phrasing task, not open-ended drafting — Haiku, not Opus.
DAILY_SUMMARY_MODEL = "claude-haiku-4-5"

# A sane upper bound for "one sentence" — anything longer fails the sanity
# check and falls back to no sentence at all, rather than a runaway output.
MAX_DAILY_SUMMARY_LENGTH = 320

_DAILY_SUMMARY_SYSTEM_PROMPT = (
    "You write exactly one short sentence summarising a clinic's day for a "
    "public report page. You are given de-identified aggregate counts only. "
    "State only these figures — do not add context, comparisons, estimates, "
    "or any claim not present in the data. Do not invent or restate a "
    "statistic from memory; use only the numbers given to you."
)


def build_daily_summary_payload(aggregate: DailyAggregate) -> dict[str, Any]:
    """Build the exact payload for the daily-summary call — aggregates only.

    Built entirely from ``aggregate.as_dict()``, which by construction holds
    only counts for this one clinic-date — there is no field here that could
    carry a patient identifier or another date's data.
    """
    return {
        "model": DAILY_SUMMARY_MODEL,
        "max_tokens": 200,
        "system": _DAILY_SUMMARY_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    "In one sentence, summarise this clinic's day using only "
                    "these de-identified figures:\n"
                    + json.dumps(aggregate.as_dict(), sort_keys=True, indent=2)
                ),
            }
        ],
    }


def draft_daily_summary_sentence(
    aggregate: DailyAggregate, client: _AnthropicLike | None = None
) -> str | None:
    """Ask the model to phrase the day's aggregate as one sentence, or give up.

    Returns ``None`` — never raises — on any failure: client construction,
    the API call itself, or a response that fails the basic sanity check
    (empty, or over :data:`MAX_DAILY_SUMMARY_LENGTH`). The caller always has
    a safe value to fall back to, which is exactly what lets the daily report
    page auto-publish unconditionally (see this module's Plan 08 section
    above). The broad ``except Exception`` here is deliberate: *any* failure
    mode of an external API call — network error, timeout, malformed
    response — must degrade to "no sentence", never bubble up and block the
    deterministic numbers.
    """
    try:
        active_client = client or get_anthropic_client()
        payload = build_daily_summary_payload(aggregate)
        response = active_client.messages.create(**payload)
        text = response.content[0].text.strip()
    except Exception:  # noqa: BLE001 - any failure falls back to no sentence
        return None

    if not text or len(text) > MAX_DAILY_SUMMARY_LENGTH:
        return None
    return text


def get_anthropic_client() -> _AnthropicLike:  # pragma: no cover - prod only
    """Construct the real Anthropic client for production use.

    Never called from the test suite — a conftest fixture patches this to raise,
    guaranteeing no real API call happens in CI. The import is lazy so the SDK
    is only touched when a real call is actually made.
    """
    import os

    import anthropic

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
