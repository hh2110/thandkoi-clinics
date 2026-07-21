"""App config for the clinic data pipeline.

The pipeline turns a daily clinic Excel export into de-identified aggregates.
Plan 02 provided the privacy-guardrail skeleton — the aggregate-and-discard
function, the AI payload builder, and a deterministic report renderer — plus
the tests that pin the privacy invariants from CLAUDE.md. Plan 08 builds the
real intake view, parser registry, persisted aggregate/row-level models, and
Wagtail report pages on top of that base.
"""

from django.apps import AppConfig


class PipelineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline"
    verbose_name = "Clinic data pipeline"

    def ready(self):
        """Import concrete parser modules so they self-register.

        Each parser module's ``register()`` call adds itself to
        ``ParserRegistry`` on import; this is the one place that import needs
        to happen so every registered parser is available regardless of
        which view or management command runs first.
        """
        from apps.pipeline import parser_clinic_v1

        parser_clinic_v1.register()
