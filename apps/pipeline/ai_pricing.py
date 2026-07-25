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
rows — see ``MONTHLY_NEWSLETTER_MODEL`` (``claude-sonnet-5``) and
``DAILY_SUMMARY_MODEL`` (``claude-haiku-4-5``) in ``apps.pipeline.ai``. Add a
row here before wiring in any new model.
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


class UncountedCacheTokensError(Exception):
    """A response reported prompt-cache tokens this module does not price.

    Plan 15 Track D3. :func:`compute_cost_usd` prices only plain
    ``input_tokens``/``output_tokens``. Prompt caching (deferred — no call
    site enables it today) bills ``cache_read_input_tokens`` and
    ``cache_creation_input_tokens`` at *different* rates (a read is cheaper
    than a fresh input token, a creation dearer), so a cost computed from the
    plain counts alone would silently mis-report the moment caching is turned
    on. This is raised so that turning caching on forces
    :data:`PRICING_PER_MILLION_TOKENS` to gain cache rates first, rather than
    letting the meter drift unnoticed.
    """


def assert_no_uncounted_cache_tokens(usage: object) -> None:
    """Raise :class:`UncountedCacheTokensError` if ``usage`` reports cache
    tokens (Plan 15 Track D3).

    ``usage`` is the SDK's ``response.usage``. The two cache fields are absent
    (or zero) on every response today, so this is a no-op until prompt
    caching is deliberately enabled — at which point it fires loudly instead
    of the meter silently under-counting.
    """
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if cache_read or cache_creation:
        raise UncountedCacheTokensError(
            "response.usage reported prompt-cache tokens "
            f"(cache_read={cache_read}, cache_creation={cache_creation}) but "
            "ai_pricing does not price them yet — add cache rates to "
            "PRICING_PER_MILLION_TOKENS before enabling prompt caching."
        )


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
