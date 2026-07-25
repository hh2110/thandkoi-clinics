"""Sentry PHI-scrub hooks and trace sampling policy (Plan 12 Track A, Plan 17).

These live here rather than inside ``config/settings/prod.py`` deliberately
(Plan 17 Decision 2). Importing the prod settings module executes the entire
production settings file and demands every required secret, which is exactly
why the original ``before_send`` scrub shipped with **no unit test** — CI's
``manage.py check --deploy`` gate (Plan 15 Track A2) proves the hook *imports*,
not that it *scrubs*. A Sentry PHI leak is the one defect class this codebase
has already shipped once (Plan 15 Track A1), so the hooks are plain functions
in a plain module that the test suite can exercise directly.

Nothing here reads Django settings or touches the ORM, so it is safe to import
from a settings module at import time.
"""

import logging

logger = logging.getLogger(__name__)

#: Paths whose transactions are never sampled — see ``traces_sampler``.
#: ``/healthz`` is registered without a trailing slash in ``config/urls.py``;
#: both spellings are listed so an ``APPEND_SLASH`` redirect can't sneak the
#: probe back into the sample.
UNSAMPLED_PATHS = frozenset({"/healthz", "/healthz/"})


def _strip_request_body(event):
    """Drop any request-body representation from a Sentry event, in place.

    The upload view receives a full daily clinic export as a multipart request
    body, and that body is raw PHI (CLAUDE.md invariant #1). An unhandled
    error *anywhere* in the request — not just in the upload path — would
    otherwise let Sentry attach the body (or a URL/form representation of it)
    to the outgoing event. We positively delete the representation rather than
    trust any single ``sentry_sdk.init`` knob to cover every shape it takes.
    """
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("body", None)
    return event


def before_send(event, hint):
    """Scrub error events. Registered as ``sentry_sdk.init(before_send=...)``."""
    return _strip_request_body(event)


def before_send_transaction(event, hint):
    """Scrub performance (transaction) events.

    Load-bearing, and the reason this module exists (Plan 17 Decision 1):
    ``before_send`` fires **only for error events**. A transaction event
    carries its own ``request`` section, so enabling ``traces_sample_rate``
    without this hook would reopen the very hole Plan 15 Track A1 closed —
    through a new door, on every sampled request rather than only on errors.
    """
    return _strip_request_body(event)


def before_send_log(record, hint):
    """Pass structured log records through unchanged, for now.

    Registered so that turning log forwarding on (Plan 17 Track B) has a
    single, named place to scrub from if a future log call ever carries
    something it shouldn't — rather than that scrub having to be retrofitted
    under pressure, which is how Plan 15 Track A1 went.

    Nothing is stripped today because the forwarded set is deliberately narrow
    (``WARNING`` and above only) and its members were audited in Plan 17
    Decision 5: log records carry the formatted message, never frame-locals,
    and the one message that touches the export path is structural-only by the
    ``ExportParseError`` contract.
    """
    return record


def _path_from_sampling_context(sampling_context):
    """Best-effort request path for a sampling decision, or ``None``.

    The WSGI integration puts the raw environ on the sampling context
    (verified against sentry-sdk 2.66.1,
    ``sentry_sdk/integrations/wsgi.py``); the ASGI key is checked too so this
    keeps working if the service ever moves off gunicorn's WSGI worker.
    """
    environ = sampling_context.get("wsgi_environ")
    if isinstance(environ, dict):
        return environ.get("PATH_INFO")

    scope = sampling_context.get("asgi_scope")
    if isinstance(scope, dict):
        return scope.get("path")

    return None


def make_traces_sampler(rate):
    """Build a ``traces_sampler`` that samples at ``rate`` but never health checks.

    Health-check traffic is the highest-volume route on this site by a wide
    margin — a 60-second uptime poll is ~43k requests/month on its own — and
    its latency says nothing (it's a bare 200). Sampling it would spend most
    of the span budget on noise *and* drag the p50 of every "all transactions"
    widget toward zero, making the dashboard actively misleading (Plan 17
    Decision 3).
    """

    def traces_sampler(sampling_context):
        path = _path_from_sampling_context(sampling_context)
        if path in UNSAMPLED_PATHS:
            return 0.0
        return rate

    return traces_sampler


def parse_sample_rate(raw, default=1.0):
    """Coerce a ``SENTRY_TRACES_SAMPLE_RATE`` string to a rate in [0.0, 1.0].

    Soft-fail by design, mirroring ``SENTRY_DSN``'s treatment (Plan 12
    Decisions, Plan 17 Decision 4): a typo in an observability env var must
    degrade to the default sample rate, never take the site down. A bad value
    is logged so it's still discoverable in the Render log tail.
    """
    if raw is None or raw == "":
        return default

    try:
        rate = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparseable SENTRY_TRACES_SAMPLE_RATE %r; using %s",
            raw,
            default,
        )
        return default

    if not 0.0 <= rate <= 1.0:
        logger.warning(
            "Ignoring out-of-range SENTRY_TRACES_SAMPLE_RATE %r; using %s",
            raw,
            default,
        )
        return default

    return rate
