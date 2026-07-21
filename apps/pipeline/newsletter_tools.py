"""The read-only tools the monthly-newsletter model can call (Plan 09).

Three thin, typed wrappers — ``get_month_stats``, ``get_trend_vs_last_month``,
``get_previous_newsletter`` — matching the shape named in
architecture-and-ai-brief.md §6.2 and ``.claude/plans/09-ai-monthly-newsletter.md``.
Each is independently unit-testable with no AI call involved; ``apps.pipeline.ai``
only wires them up as tool-use dispatch targets for the Anthropic call.

Neither this module nor ``apps.pipeline.monthly_rollup`` ever queries
``DeidentifiedVisit`` — the de-identification boundary sits upstream of the
``ai`` module (CLAUDE.md invariant #2), and a monthly rollup is, by
construction, an aggregation *over* ``DailyAggregate`` (Plan 08's derived
cache), never a re-read of row-level data.
"""

from __future__ import annotations

import datetime

from apps.core.models import NewsletterPage
from apps.pipeline.monthly_rollup import (
    compute_month_over_month_trend,
    compute_monthly_rollup,
)


def get_month_stats(month: datetime.date) -> dict[str, object]:
    """This calendar month's totals — a Python-computed ``DailyAggregate`` sum."""
    return compute_monthly_rollup(month).as_dict()


def get_trend_vs_last_month(month: datetime.date) -> dict[str, object]:
    """This month vs. the calendar month before it — both sides computed."""
    return compute_month_over_month_trend(month)


def get_previous_newsletter() -> dict[str, object] | None:
    """The most recently *published* newsletter issue, or ``None`` if there isn't one.

    Reads only ``NewsletterPage.objects.live()`` — published content only,
    matching the public-site-assistant principle (brief §6.3) of grounding on
    what's actually public, even though this tool's use is internal. Used for
    voice/style consistency, per the maintainer's decision that this tool's
    scope is just the immediately previous issue (PR #17).
    """
    previous = NewsletterPage.objects.live().order_by("-issue_date", "-pk").first()
    if previous is None:
        return None
    return {
        "issue_date": previous.issue_date.isoformat(),
        "title": previous.title,
        "summary": previous.summary,
    }
