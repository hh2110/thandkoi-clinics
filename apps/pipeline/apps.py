"""App config for the clinic data pipeline.

The pipeline turns a daily clinic Excel export into de-identified aggregates.
Plan 02 provides the privacy-guardrail skeleton — the aggregate-and-discard
function, the AI payload builder, and a deterministic report renderer — plus the
tests that pin the privacy invariants from CLAUDE.md. Plan 08 builds the real
intake views, parser registry, and Wagtail report pages on top of this base.

This app deliberately has no models yet: the whole point of the pipeline is that
raw patient data is aggregated in memory and never persisted (invariant #1), so
there is nothing raw to store.
"""

from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline"
    verbose_name = "Clinic data pipeline"
