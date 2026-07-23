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

import datetime
import json
from collections.abc import Callable
from typing import Any, Protocol

from apps.pipeline.aggregation import ClinicAggregate
from apps.pipeline.freetext import FREETEXT_COLUMN_LABELS
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
DRAFTING_MODEL = "claude-sonnet-5"

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
        # Sonnet 5 runs adaptive thinking by default when `thinking` is
        # omitted (Opus did not) -- thinking output counts against this same
        # fixed max_tokens, so an unconfigured default risks truncating this
        # already-tight budget (stop_reason="max_tokens") purely from the
        # model swap. Disabled explicitly to keep the budget for prose, same
        # as the pre-existing Opus behavior.
        "thinking": {"type": "disabled"},
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


def _draft_short_text(
    build_payload: Callable[[], dict[str, Any]],
    client: _AnthropicLike | None,
    max_length: int,
) -> str | None:
    """Shared shape behind every short, fixed-template drafting call below.

    Returns ``None`` — never raises — on any failure: client construction,
    payload building, the API call itself, or a response that fails the
    basic sanity check (empty, or over ``max_length``). ``build_payload`` is
    called *inside* the try so a payload-building error degrades the same
    way an API error does — none of these calls may ever bubble up and block
    their caller. Extracted (found by code-review-tc) so a future change to
    this shape only has one place to land, instead of three near-identical
    copies drifting apart.
    """
    try:
        active_client = client or get_anthropic_client()
        payload = build_payload()
        response = active_client.messages.create(**payload)
        text = response.content[0].text.strip()
    except Exception:  # noqa: BLE001 - any failure means "no text this run"
        return None

    if not text or len(text) > max_length:
        return None
    return text


def draft_daily_summary_sentence(
    aggregate: DailyAggregate, client: _AnthropicLike | None = None
) -> str | None:
    """Ask the model to phrase the day's aggregate as one sentence, or give up.

    See :func:`_draft_short_text` for the failure contract. The caller always
    has a safe value to fall back to, which is exactly what lets the daily
    report page auto-publish unconditionally (see this module's Plan 08
    section above).
    """
    return _draft_short_text(
        lambda: build_daily_summary_payload(aggregate), client, MAX_DAILY_SUMMARY_LENGTH
    )


# --- Plan 11 Track B8/B9: free-text summary + empty-column flag ------------
#
# Unlike the daily-summary sentence above, these two calls do NOT get
# CLAUDE.md invariant #4's Plan 08 exception — they are new AI-authored
# content, so the *default* human-in-the-loop rule applies: a person must
# review and explicitly approve before either is shown on a public page. See
# ``apps.pipeline.report_publishing.publish_daily_report`` for where the
# output of these two calls lands (a `_draft` field, never auto-approved) and
# ``DailyReportPage.freetext_summary_approved``/``empty_columns_flag_approved``
# for the review gate itself.
#
# Both still follow invariant #3's shape ("numbers computed in Python, AI
# writes prose only"): B8 is handed only the non-blank free-text entries
# already collected by ``apps.pipeline.freetext.collect_freetext_entries``;
# B9 is handed only the already-computed booleans from
# ``apps.pipeline.freetext.compute_empty_columns`` and may only *phrase* that
# fact, never decide it.
#
# Grounding note: sending the seven named free-text columns to a model is
# authorised by the maintainer's 2026-07-23 decision (see
# ``apps.pipeline.freetext``'s module docstring) — they are confirmed free of
# patient identifiers by construction, not by any scrubbing this module does.

# Short, fixed-template tasks restating/flagging already-computed input — the
# same classification as DAILY_SUMMARY_MODEL above (CLAUDE.md → Stack).
FREETEXT_SUMMARY_MODEL = "claude-haiku-4-5"
EMPTY_COLUMNS_FLAG_MODEL = "claude-haiku-4-5"

# Sanity-check upper bounds, same role as MAX_DAILY_SUMMARY_LENGTH above: a
# response over this length (or empty) is treated as a failed draft, not
# published as-is. These calls are draft-only (never auto-published), so
# there is no fallback-to-blank requirement driving the bound the way Plan
# 08's exception does — it's purely a runaway-output guard, not a length
# target: it must sit comfortably above what the call's own max_tokens can
# actually produce (~4 chars/token for English, plus margin), or a genuinely
# good, full-length response on a busy day gets rejected as if it had failed
# (found by code-review-tc: the previous bounds were tighter than their
# calls' max_tokens could produce — a valid 600-token freetext summary could
# run well past the old 800-char cap).
MAX_FREETEXT_SUMMARY_LENGTH = 3000  # max_tokens=600 below
MAX_EMPTY_COLUMNS_FLAG_LENGTH = 1000  # max_tokens=200 below

_FREETEXT_SUMMARY_SYSTEM_PROMPT = (
    "You are drafting an internal review summary (not yet published) of a "
    "clinic's free-text clinical notes for one day. You are given, for each "
    "listed column, every non-blank entry recorded that day. Write a short, "
    "factual summary of common themes across entries. Do not invent, "
    "estimate, or attribute anything to a specific patient — you are not "
    "given any patient identifier and must not imply one. If a column has no "
    "entries, say so plainly rather than guessing what it might have said."
)


def build_freetext_summary_payload(
    clinic_date: datetime.date, columns: dict[str, list[str]]
) -> dict[str, Any]:
    """Build the exact payload for the B8 free-text-summary call.

    ``columns`` is built by
    :func:`apps.pipeline.freetext.collect_freetext_entries` from that date's
    ``DeidentifiedVisit`` rows — every value is one of the seven named
    free-text columns the maintainer confirmed (2026-07-23) are structurally
    free of patient identifiers by construction. Nothing else about a visit —
    no age band, sex, location, or any identifying field — is included.
    """
    body = {FREETEXT_COLUMN_LABELS[name]: values for name, values in columns.items()}
    return {
        "model": FREETEXT_SUMMARY_MODEL,
        "max_tokens": 600,
        "system": _FREETEXT_SUMMARY_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Summarise {clinic_date.isoformat()}'s free-text clinical "
                    "columns, given as {column label: [every non-blank entry "
                    "recorded that day]}:\n"
                    # ensure_ascii=False: this is bilingual clinic (CLAUDE.md
                    # "Bilingual") free text, so Urdu entries must reach the
                    # model as real characters, not \uXXXX escapes (found by
                    # code-review-tc).
                    + json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False)
                ),
            }
        ],
    }


def draft_freetext_summary(
    clinic_date: datetime.date,
    columns: dict[str, list[str]],
    client: _AnthropicLike | None = None,
) -> str | None:
    """Ask the model to summarise the day's free-text columns, or give up.

    See :func:`_draft_short_text` for the failure contract. Unlike
    :func:`draft_daily_summary_sentence`, a ``None`` (or a drafted string)
    here is never auto-shown on the public page:
    :func:`apps.pipeline.report_publishing.publish_daily_report` stores
    whatever this returns (or ``""``) in ``freetext_summary_draft`` and a
    person must separately approve it (CLAUDE.md invariant #4's default
    rule, not Plan 08's narrow exception).
    """
    return _draft_short_text(
        lambda: build_freetext_summary_payload(clinic_date, columns),
        client,
        MAX_FREETEXT_SUMMARY_LENGTH,
    )


_EMPTY_COLUMNS_FLAG_SYSTEM_PROMPT = (
    "You write a short, plain-language internal note (not yet published) "
    "listing which of a clinic's free-text record columns were left blank "
    "for the day, so staff know what to fill in. You are given, for each "
    "listed column, whether it was entirely empty across every visit that "
    "day — a true/false fact already determined for you; you must not "
    "recompute or second-guess it. State only which columns are marked "
    "empty. Do not add commentary on why, and if none are empty, say so in "
    "one short sentence instead of listing every column as filled in."
)


def build_empty_columns_flag_payload(
    clinic_date: datetime.date, empty_columns: dict[str, bool]
) -> dict[str, Any]:
    """Build the exact payload for the B9 empty-column-flag call.

    ``empty_columns`` is built by
    :func:`apps.pipeline.freetext.compute_empty_columns` — a dict of
    already-computed booleans, one per free-text column, over the same
    de-identified visits as :func:`build_freetext_summary_payload`. No visit
    data itself crosses into this payload, only the derived booleans.
    """
    body = {
        FREETEXT_COLUMN_LABELS[name]: is_empty
        for name, is_empty in empty_columns.items()
    }
    return {
        "model": EMPTY_COLUMNS_FLAG_MODEL,
        "max_tokens": 200,
        "system": _EMPTY_COLUMNS_FLAG_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"For {clinic_date.isoformat()}, here is whether each "
                    "free-text column was entirely empty across today's "
                    "visits:\n" + json.dumps(body, sort_keys=True, indent=2)
                ),
            }
        ],
    }


def draft_empty_columns_flag(
    clinic_date: datetime.date,
    empty_columns: dict[str, bool],
    client: _AnthropicLike | None = None,
) -> str | None:
    """Ask the model to phrase which columns are empty, or give up.

    Same failure/review-gate contract as :func:`draft_freetext_summary` above
    — see :func:`_draft_short_text`.
    """
    return _draft_short_text(
        lambda: build_empty_columns_flag_payload(clinic_date, empty_columns),
        client,
        MAX_EMPTY_COLUMNS_FLAG_LENGTH,
    )


# --- Plan 09: the monthly newsletter — one-shot prompt with tooling --------
#
# The "one-shot prompt with tooling" shape from architecture-and-ai-brief.md
# §6.2: rather than one pre-flattened context blob, the model is given a
# short brief and calls small, read-only tools (apps.pipeline.newsletter_tools)
# to pull the specific figures and comparisons it needs. Unlike the daily
# summary sentence above, this is full free-form narrative drafting, so it
# gets CLAUDE.md invariant #4's *general* rule, not Plan 08's exception: this
# call never auto-publishes anything (see apps.pipeline.newsletter_drafting),
# and on failure the correct behaviour is "no draft created", never a
# fallback. See ".claude/plans/09-ai-monthly-newsletter.md" for the full
# decision record.

MONTHLY_NEWSLETTER_MODEL = "claude-sonnet-5"

# A one-shot-with-tooling call can loop through several tool round-trips
# before the model is ready to answer; this bounds it so a model that never
# stops calling tools can't spin the request forever. Generous enough for the
# three tools this call ever offers (get_month_stats, get_trend_vs_last_month,
# get_previous_newsletter) to all be called at least once with room to spare.
MAX_NEWSLETTER_TOOL_TURNS = 6

# A sane upper bound on the drafted issue's length — anything longer (or
# empty) fails the sanity check and the run produces no draft at all (Plan
# 09's failure handling — the opposite of Plan 08's daily page, which must
# ship regardless).
MAX_MONTHLY_NEWSLETTER_LENGTH = 6000

_MONTHLY_NEWSLETTER_SYSTEM_PROMPT = (
    "You are drafting one issue of a not-for-profit clinic's monthly "
    "newsletter for its public website. You do not have this month's figures "
    "memorised — call get_month_stats and get_trend_vs_last_month to retrieve "
    "them, and call get_previous_newsletter to match the previous issue's "
    "voice. Every number in your final newsletter text must come from a tool "
    "result you were just given; never invent, estimate, or recall a "
    "statistic. Write warm, factual prose suitable for donors and the local "
    "community, weaving in the admin's notes and any photo captions you are "
    "given. You are working from de-identified aggregate counts and "
    "admin-supplied notes only — never ask about or refer to an individual "
    "patient. When you are ready, respond with the final newsletter body text "
    "in plain prose and stop calling tools."
)

MONTHLY_NEWSLETTER_TOOLS: list[dict[str, object]] = [
    {
        "name": "get_month_stats",
        "description": (
            "Get this calendar month's aggregate clinic statistics — total "
            "visits, patient breakdowns, and category counts, computed from "
            "de-identified daily aggregates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "Calendar month as YYYY-MM.",
                }
            },
            "required": ["month"],
        },
    },
    {
        "name": "get_trend_vs_last_month",
        "description": (
            "Compare this calendar month's aggregate statistics against the "
            "month before it, including the change in total visits, new "
            "patients, and Zakat-beneficiary patients."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {
                    "type": "string",
                    "description": "Calendar month as YYYY-MM.",
                }
            },
            "required": ["month"],
        },
    },
    {
        "name": "get_previous_newsletter",
        "description": (
            "Get the most recently published newsletter issue's title and "
            "summary, for voice and style consistency. Returns null if there "
            "is no previously published issue."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _parse_tool_month(tool_input: dict[str, Any]) -> datetime.date:
    return datetime.datetime.strptime(tool_input["month"], "%Y-%m").date()


def _execute_newsletter_tool(name: str, tool_input: dict[str, Any]) -> Any:
    """Dispatch one model-requested tool call to its read-only implementation.

    Every branch here reads only ``DailyAggregate`` or published
    ``NewsletterPage`` rows (via ``apps.pipeline.newsletter_tools``) — never
    ``DeidentifiedVisit``, per the de-identification boundary this plan is
    built to respect.
    """
    from apps.pipeline import newsletter_tools

    if name == "get_month_stats":
        return newsletter_tools.get_month_stats(_parse_tool_month(tool_input))
    if name == "get_trend_vs_last_month":
        return newsletter_tools.get_trend_vs_last_month(_parse_tool_month(tool_input))
    if name == "get_previous_newsletter":
        return newsletter_tools.get_previous_newsletter()
    raise ValueError(f"Unknown tool requested by the model: {name!r}")


def build_monthly_newsletter_user_message(
    month: datetime.date, notes_text: str, photo_captions: list[str]
) -> str:
    """The one user message this call ever sends — the brief, not the figures.

    Figures are deliberately absent here: the model must call
    ``get_month_stats``/``get_trend_vs_last_month`` to get them, rather than
    receiving a pre-flattened blob (the "one-shot prompt with tooling" shape,
    brief §6.2).
    """
    lines = [
        f"Draft the newsletter issue for {month:%B %Y}.",
        "Call get_month_stats and get_trend_vs_last_month for this month's "
        "figures, and get_previous_newsletter to match the previous issue's "
        "voice, before you write the final text.",
    ]
    if notes_text.strip():
        lines.append("The admin's notes for this month:\n" + notes_text.strip())
    captions = [caption for caption in photo_captions if caption.strip()]
    if captions:
        lines.append(
            "Photos already selected for this issue (weave them naturally "
            "into the narrative where relevant; you do not need to describe "
            "them in detail):\n" + "\n".join(f"- {caption}" for caption in captions)
        )
    return "\n\n".join(lines)


def draft_monthly_newsletter_body(
    month: datetime.date,
    *,
    notes_text: str = "",
    photo_captions: list[str] | None = None,
    client: _AnthropicLike | None = None,
) -> str | None:
    """Run the one-shot-prompt-with-tooling call; return prose, or ``None``.

    Returns ``None`` — never raises — on any failure: client construction,
    the API call itself, exceeding :data:`MAX_NEWSLETTER_TOOL_TURNS` without a
    final answer, or a response that fails the basic sanity check (empty, or
    over :data:`MAX_MONTHLY_NEWSLETTER_LENGTH`). Unlike
    :func:`draft_daily_summary_sentence`, the caller
    (``apps.pipeline.newsletter_drafting.draft_monthly_newsletter``) does NOT
    fall back to publishing anything on ``None`` — it records a failed audit
    run and creates no draft at all (Plan 09's failure handling is the
    opposite of Plan 08's daily page). The broad ``except Exception`` here is
    deliberate for the same reason as the daily summary sentence: any failure
    mode of an external API call must degrade to "no draft", never raise.
    """
    try:
        active_client = client or get_anthropic_client()
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": build_monthly_newsletter_user_message(
                    month, notes_text, photo_captions or []
                ),
            }
        ]

        text = ""
        for _ in range(MAX_NEWSLETTER_TOOL_TURNS):
            response = active_client.messages.create(
                model=MONTHLY_NEWSLETTER_MODEL,
                max_tokens=4096,
                # Sonnet 5 runs adaptive thinking by default when `thinking`
                # is omitted (Opus, the previous model here, did not), and
                # thinking output counts against this same fixed max_tokens
                # across every tool-turn -- an unconfigured default risks
                # truncating a turn (stop_reason="max_tokens", read as a
                # failure below) purely from the model swap. Disabled
                # explicitly to preserve the prior no-thinking behavior and
                # budget.
                thinking={"type": "disabled"},
                system=_MONTHLY_NEWSLETTER_SYSTEM_PROMPT,
                tools=MONTHLY_NEWSLETTER_TOOLS,
                messages=messages,
            )
            if response.stop_reason == "end_turn":
                text = "".join(
                    block.text for block in response.content if block.type == "text"
                ).strip()
                break
            if response.stop_reason != "tool_use":
                # max_tokens (truncated mid-sentence), refusal, stop_sequence,
                # pause_turn, etc. — none of these is a clean completion, so
                # none may become the drafted text; degrade to "no draft"
                # rather than risk publishing a truncated or refused response.
                return None

            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(
                        _execute_newsletter_tool(block.name, block.input),
                        sort_keys=True,
                    ),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
        else:
            return None  # exceeded MAX_NEWSLETTER_TOOL_TURNS without an answer
    except Exception:  # noqa: BLE001 - any failure means "no draft", never raise
        return None

    if not text or len(text) > MAX_MONTHLY_NEWSLETTER_LENGTH:
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
