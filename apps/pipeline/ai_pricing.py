"""Anthropic per-token pricing, for computing AI-call cost (Plan 11 C2).

The Anthropic API does not return a cost figure on a response — only token
counts (``response.usage.input_tokens`` / ``.output_tokens``). This module is
the one place that maps a model id to its published USD-per-token rate, so
:meth:`apps.pipeline.models.AiCallLog.record` (and anything else that needs a
cost figure) has a single source to update when Anthropic's pricing changes,
rather than a rate hard-coded at every call site.

**Source:** https://platform.claude.com/docs/en/about-claude/pricing
(fetched 2026-07-23).

Only the two models this codebase actually calls (CLAUDE.md → Stack) have
rows — see ``NEWSLETTER_DRAFTING_MODEL``/``DAILY_SUMMARY_MODEL`` in
``apps.pipeline.ai``. Add a row here before wiring in any new model.
"""

from __future__ import annotations

from decimal import Decimal

# USD per 1,000,000 tokens, as (input_rate, output_rate). Keep this in sync
# with the pricing page above.
#
# Claude Sonnet 5 is running introductory pricing ($2 / $10 per MTok)
# through 2026-08-31; standard pricing ($3 / $15 per MTok) takes effect
# 2026-09-01 per that page's "Claude Sonnet 5 starting September 1, 2026"
# row — update the entry below on that date (or sooner, if Anthropic
# changes published rates before then).
PRICING_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
}

_TOKENS_PER_MILLION = Decimal("1000000")


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Compute the USD cost of one AI call from its token counts.

    Returns ``Decimal("0")`` for a model with no entry in
    :data:`PRICING_PER_MILLION_TOKENS`, rather than raising — an unrecognized
    or renamed model should never crash the call it's logging; it should just
    under-report cost (visibly, as a $0 row in admin) until this table is
    updated.
    """
    rates = PRICING_PER_MILLION_TOKENS.get(model)
    if rates is None:
        return Decimal("0")
    input_rate, output_rate = rates
    return (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / _TOKENS_PER_MILLION
