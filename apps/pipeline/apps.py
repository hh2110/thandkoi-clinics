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

        ``apps.pipeline.parser_clinic_v1`` (the pre-sample, provisional
        schema) is deliberately **not** imported/registered here (decision,
        2026-07-22): now that the real export sample has landed and
        ``tkc_daily_activity_v1`` is grounded in it, the provisional parser
        no longer needs to appear as a selectable upload format. The module
        itself stays in the tree — its privacy-guardrail tests and its use
        as generic fixture data elsewhere in ``apps/pipeline/tests.py`` are
        still-useful regression coverage — it's just no longer wired up as a
        real format choice.
        """
        from apps.pipeline import parser_tkc_daily_v1

        parser_tkc_daily_v1.register()
