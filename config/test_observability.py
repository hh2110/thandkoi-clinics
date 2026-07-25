"""Tests for the Sentry PHI-scrub hooks and trace sampling policy (Plan 17).

These exist because the original scrub had none. Before Plan 17 the hook lived
inside ``config/settings/prod.py``, where importing it executes the whole
production settings file and demands every required secret — so the only thing
standing behind it was CI's ``manage.py check --deploy`` step, which proves the
hook *imports*, not that it *scrubs* (Plan 17 Decision 2). Given that a Sentry
PHI leak is the one defect class this codebase has already shipped once
(Plan 15 Track A1), the scrub now gets asserted directly.

No Django DB or settings access is needed — ``config.observability`` is a plain
module by design.
"""

import logging

import pytest

from config import observability

# --- PHI scrubbing -----------------------------------------------------------


@pytest.mark.parametrize(
    "hook",
    [observability.before_send, observability.before_send_transaction],
    ids=["error_event", "transaction_event"],
)
def test_request_body_is_stripped_from_every_event_kind(hook):
    """Both hooks drop the request body — a raw patient export on the upload path.

    Parametrized over both hooks on purpose (Plan 17 Decision 1): ``before_send``
    fires for error events *only*, so enabling tracing without an equivalent
    transaction hook would let the upload view's multipart body — raw PHI,
    CLAUDE.md invariant #1 — ride out on every sampled request. If someone
    later wires only one of the two, this fails.
    """
    event = {
        "request": {
            "url": "https://thandkoiclinics.com/admin/pipeline/upload/",
            "method": "POST",
            "data": {"export": "Bibi Zainab,42,F,Hypertension"},
            "body": b"raw multipart patient export",
            "headers": {"Content-Type": "multipart/form-data"},
        }
    }

    scrubbed = hook(event, {})

    assert "data" not in scrubbed["request"]
    assert "body" not in scrubbed["request"]
    # Non-body request metadata is diagnostic, not identifying — it stays.
    assert scrubbed["request"]["url"].endswith("/admin/pipeline/upload/")
    assert scrubbed["request"]["method"] == "POST"


@pytest.mark.parametrize(
    "hook",
    [observability.before_send, observability.before_send_transaction],
    ids=["error_event", "transaction_event"],
)
@pytest.mark.parametrize(
    "event",
    [{}, {"request": None}, {"request": "not-a-dict"}, {"request": {}}],
    ids=["no_request", "null_request", "string_request", "empty_request"],
)
def test_scrub_passes_through_events_without_a_request_body(hook, event):
    """A malformed or request-less event must not raise inside the hook.

    An exception raised in ``before_send`` is swallowed by the SDK and drops
    the event silently, which would turn a scrub bug into invisible loss of
    error reporting.
    """
    assert hook(event, {}) is not None


def test_application_warnings_are_forwarded():
    """The signal this whole track exists to surface must survive the filter."""
    record = {
        "body": "Export upload failed to parse: missing column",
        "severity_text": "warn",
        "attributes": {"logger.name": "apps.pipeline.admin_views"},
    }

    assert observability.before_send_log(record, {}) == record


def test_bot_scan_404s_are_dropped():
    """404s are dropped or they drown the warnings panel (Plan 17).

    Django logs every 4xx at WARNING via ``django.request``, and on a public
    site almost all 404s are bots probing for ``/wp-login.php`` and friends.
    Measured against the real WSGI app while building this: four bot requests
    produced four such records. Forwarding them would bury the AI-drafting
    failures the dashboard is meant to show, in the panel meant to show them.
    """
    record = {
        "body": "Not Found: /wp-login.php",
        "severity_text": "warn",
        "attributes": {"logger.name": "django.request", "status_code": 404},
    }

    assert observability.before_send_log(record, {}) is None


@pytest.mark.parametrize("status_code", [400, 403, 500])
def test_other_django_request_statuses_are_kept(status_code):
    """Only 404 is noise. A 400 means something is misconfigured (DisallowedHost),
    a 403 is worth seeing, and neither arrives in bot-scan volumes."""
    record = {
        "body": f"Something: {status_code}",
        "severity_text": "warn",
        "attributes": {"logger.name": "django.request", "status_code": status_code},
    }

    assert observability.before_send_log(record, {}) == record


def test_a_404_from_another_logger_is_not_dropped():
    """The filter is scoped to Django's request logger, not to the number 404.

    An application warning that happens to carry a ``status_code`` of 404 —
    say a failed outbound fetch — is real signal and must not be swallowed by
    a filter aimed at Django's own request log.
    """
    record = {
        "body": "Upstream returned 404",
        "severity_text": "warn",
        "attributes": {"logger.name": "apps.pipeline.ai", "status_code": 404},
    }

    assert observability.before_send_log(record, {}) == record


@pytest.mark.parametrize(
    "record",
    [{}, {"attributes": None}, {"attributes": {}}],
    ids=["no_attributes", "null_attributes", "empty_attributes"],
)
def test_before_send_log_tolerates_records_without_attributes(record):
    """A record with no attributes must pass through, not raise.

    Raising here would drop the log silently inside the SDK — turning a filter
    bug into invisible loss of the signal.
    """
    assert observability.before_send_log(record, {}) is record


# --- Trace sampling ----------------------------------------------------------


@pytest.mark.parametrize("path", ["/healthz", "/healthz/"])
def test_health_checks_are_never_sampled(path):
    """`/healthz` is dropped at source (Plan 17 Decision 3).

    A 60-second uptime poll is ~43k requests/month — by far the highest-volume
    route on this site — and its latency is meaningless. Sampling it would
    burn the span budget on noise and drag every p50 widget toward zero.
    """
    sampler = observability.make_traces_sampler(1.0)

    assert sampler({"wsgi_environ": {"PATH_INFO": path}}) == 0.0


def test_ordinary_requests_are_sampled_at_the_configured_rate():
    sampler = observability.make_traces_sampler(0.25)

    assert sampler({"wsgi_environ": {"PATH_INFO": "/en/reports/"}}) == 0.25


def test_sampler_handles_an_asgi_scope():
    """The ASGI key is honoured too, so this survives a move off the WSGI worker."""
    sampler = observability.make_traces_sampler(1.0)

    assert sampler({"asgi_scope": {"path": "/healthz"}}) == 0.0


def test_sampler_falls_back_to_the_rate_when_the_path_is_unknown():
    """A non-HTTP transaction has no path; it must still be sampled, not dropped."""
    sampler = observability.make_traces_sampler(1.0)

    assert sampler({}) == 1.0


# --- Sample-rate parsing -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", 0.0), ("0.25", 0.25), ("1", 1.0), ("1.0", 1.0)],
)
def test_valid_sample_rates_are_parsed(raw, expected):
    assert observability.parse_sample_rate(raw) == expected


@pytest.mark.parametrize("raw", ["", None])
def test_unset_sample_rate_uses_the_default(raw):
    assert observability.parse_sample_rate(raw, default=0.5) == 0.5


@pytest.mark.parametrize("raw", ["banana", "0.5.1", "-0.1", "1.5", "100"])
def test_bad_sample_rates_degrade_to_the_default_rather_than_raising(raw, caplog):
    """A typo in an observability env var must never take the site down.

    Mirrors ``SENTRY_DSN``'s soft-fail treatment (Plan 12 Decisions): this
    value is read at settings-import time, so raising here would be a boot
    failure caused by monitoring config — precisely the outcome Plan 12
    ruled out. The bad value is logged so it stays discoverable.
    """
    with caplog.at_level(logging.WARNING):
        assert observability.parse_sample_rate(raw, default=1.0) == 1.0

    assert "SENTRY_TRACES_SAMPLE_RATE" in caplog.text
