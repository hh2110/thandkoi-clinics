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


def get_anthropic_client() -> _AnthropicLike:  # pragma: no cover - prod only
    """Construct the real Anthropic client for production use.

    Never called from the test suite — a conftest fixture patches this to raise,
    guaranteeing no real API call happens in CI. The import is lazy so the SDK
    is only touched when a real call is actually made.
    """
    import os

    import anthropic

    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
