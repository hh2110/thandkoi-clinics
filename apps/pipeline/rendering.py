"""Render a daily report — numbers from code, prose from the model.

Privacy invariant #3 (CLAUDE.md): every published figure is computed in Python
and injected into the page. The AI writes prose only and must never be the
source of a statistic. This renderer keeps those two things strictly separate:
the numeric figures come from the :class:`~apps.pipeline.aggregation.ClinicAggregate`
context, the ``prose`` string is placed in its own narrative block, and the two
never mix. A guardrail test proves the rendered figures equal the deterministic
aggregate byte-for-byte even when the (mocked) prose contains a different number.
"""

from __future__ import annotations

from django.template.loader import render_to_string

from apps.pipeline.aggregation import ClinicAggregate


def render_daily_report(aggregate: ClinicAggregate, prose: str) -> str:
    """Render the report HTML with figures taken only from ``aggregate``."""
    return render_to_string(
        "pipeline/daily_report.html",
        {
            "aggregate": aggregate,
            "by_gender": sorted(aggregate.by_gender.items()),
            "by_diagnosis": sorted(aggregate.by_diagnosis.items()),
            "prose": prose,
        },
    )
