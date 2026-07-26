"""Database connection hardening: bounded connect, detectable dead sockets.

These live here rather than inline in ``config/settings/prod.py`` for the same
reason ``config/observability.py`` does (Plan 17 Decision 2): importing the
prod settings module executes the entire production settings file and demands
every required secret, so anything defined inline there cannot be unit-tested.
This module reads no Django settings and touches no ORM, so it is safe to
import from a settings module at import time.

Why this exists — the 2026-07-26 production outage
--------------------------------------------------
At 17:11 UTC the Render instance lost outbound network connectivity. The
evidence that it was the *instance's* egress and not any one provider: the
Sentry SDK began failing to reach ``ingest.de.sentry.io`` (Google Cloud,
Germany) with ``[Errno 101] Network is unreachable`` in the same minute that
Postgres calls to Neon (AWS Singapore) started hanging — two unrelated
providers on two continents, together.

A blip in a dependency should degrade the site, not wedge it. It wedged it,
because **libpq's own ``connect_timeout`` default is 0, meaning "wait
forever"**, and this project set no ``OPTIONS`` at all. So every request that
touched the database blocked inside ``psycopg.waiting.wait_conn`` on a TCP
handshake that would never complete, until gunicorn killed the worker. The
loop then repeated on the next request, every ~31s for over 30 minutes.

The most expensive consequence was that it disarmed the readiness probe.
``apps.core.views.healthz`` wraps its query in ``except Exception`` precisely
so it can answer 503 when the database is unreachable — but a *block* is not
an exception, so that handler was unreachable and the probe hung instead of
reporting unhealthy. A timeout is what turns that hang back into the ordinary
error path the probe was always written to handle.

Both settings below are therefore about **bounding**, never about retrying or
hiding a fault: they convert "hang forever" into "raise ``OperationalError``
promptly", which every caller in this codebase already handles.
"""

import logging

#: Seconds libpq may spend establishing a connection before giving up.
#:
#: libpq's default is ``0`` — wait indefinitely — which is what turned a
#: network blip into an outage. Note libpq silently clamps any positive value
#: below 2 up to 2 seconds, so values of 0 or 1 are not meaningfully
#: expressible; 5 is comfortably above that floor while still failing fast
#: enough to stay inside gunicorn's worker timeout.
#:
#: What is actually known about the value: the app and its database are
#: co-located (Render ``singapore`` / Neon ``aws-ap-southeast-1``), and healthy
#: connects observed on 2026-07-26 were ~0.15s local and ~0.5s in production,
#: so 5s is ~10x the observed healthy case.
#:
#: What is NOT known, deliberately stated rather than implied: Neon autosuspend
#: is enabled on this project (``suspend_timeout_seconds: 0`` — the 5-minute
#: default), and **no cold resume was ever timed**. Today the UptimeRobot
#: ``/healthz`` poll queries the database often enough to keep the compute
#: warm, so resumes effectively do not happen; if that monitor is ever paused,
#: a resume slower than this bound would turn a slow first page load into a
#: 503. That is the one scenario where this value could be wrong, and the
#: reason it is overridable: ``DB_CONNECT_TIMEOUT`` is dialable from the Render
#: dashboard with no deploy. Raise it there first, then measure, before
#: changing this constant.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5

#: libpq silently clamps any positive connect_timeout below this up to it, and
#: reads 0 as "wait forever". Both make values under 2 meaningless-to-harmful,
#: so ``parse_connect_timeout`` refuses them rather than passing them through.
_LIBPQ_MINIMUM_CONNECT_TIMEOUT_SECONDS = 2

#: TCP keepalive probing for connections that are already established.
#:
#: ``connect_timeout`` only covers opening a connection. ``CONN_MAX_AGE`` is 60
#: in production, so a worker keeps a connection **idle between requests**, and
#: a vanished network leaves that socket dead with nothing to notice — the next
#: request then blocks on it. Keepalives make the kernel probe an idle socket
#: and fail it, giving up after roughly idle + (interval x count) = 60s.
#:
#: Be precise about the limit, because the gap is easy to misread as covered:
#: keepalives probe **idle** connections only. A query already in flight is
#: governed by TCP retransmission, not keepalives, so this does NOT bound a
#: request that was mid-query when the network dropped — that would need
#: ``tcp_user_timeout`` (Linux-only) or a server-side ``statement_timeout``.
#: Neither is set here: the observed outage failed at connect, and adding
#: query-deadline policy on top would be unverified scope. If a long-running
#: query path is ever added, that gap is still open and must be closed then.
KEEPALIVE_OPTIONS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

#: Only libpq understands the options above; applying them to another backend
#: would raise at connection time. The project is Postgres-only, but a settings
#: helper that silently assumes so is a trap for whoever adds a second alias.
_POSTGRESQL_BACKEND_MARKER = "postgresql"

logger = logging.getLogger(__name__)


def parse_connect_timeout(raw, default=DEFAULT_CONNECT_TIMEOUT_SECONDS):
    """Coerce a ``DB_CONNECT_TIMEOUT`` string to a usable positive bound.

    Soft-fail by design, mirroring ``observability.parse_sample_rate`` (Plan 17
    Decision 4): a typo in an operational dial must degrade to the default,
    never take the site down.

    This is not hypothetical caution. The obvious spelling,
    ``env.int("DB_CONNECT_TIMEOUT", default=...)``, calls ``int()`` on the raw
    string, so a **blank** value raises ``ValueError`` during settings import
    and every worker dies at boot. Blank is the natural state of a
    ``sync: false`` key an operator has added in the Render dashboard but not
    yet filled in — so the knob whose whole purpose is preventing an outage
    would have been able to cause a total one. Read as a string and coerced
    here instead.

    ``0`` is rejected rather than honoured: to libpq it means "wait forever",
    which is the exact default this module exists to replace, and no operator
    typing it into a field labelled *timeout* means "never time out". Values
    below libpq's floor of 2 are likewise refused rather than silently clamped.
    """
    if raw is None or raw == "":
        return default

    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparseable DB_CONNECT_TIMEOUT %r; using %s seconds",
            raw,
            default,
        )
        return default

    if timeout < _LIBPQ_MINIMUM_CONNECT_TIMEOUT_SECONDS:
        logger.warning(
            "Ignoring DB_CONNECT_TIMEOUT %r: 0 means 'wait forever' to libpq "
            "and anything under %s is clamped up to it anyway; using %s seconds",
            raw,
            _LIBPQ_MINIMUM_CONNECT_TIMEOUT_SECONDS,
            default,
        )
        return default

    return timeout


def harden_connection(
    db_config,
    connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
):
    """Bound connect time and enable keepalives on one ``DATABASES`` entry.

    Mutates ``db_config`` in place (and returns it, for convenience) because
    that is how Django settings modules already assemble this dict — see the
    ``CONN_MAX_AGE`` line that sits directly above each call site.

    Existing values always win. ``django-environ``'s ``env.db()`` folds any
    query string on ``DATABASE_URL`` into ``OPTIONS``, so an operator who has
    pinned, say, ``?connect_timeout=10`` on the connection string keeps it;
    this only supplies a default where the deployment expressed no opinion.

    Non-PostgreSQL entries are returned untouched.
    """
    if _POSTGRESQL_BACKEND_MARKER not in db_config.get("ENGINE", ""):
        return db_config

    options = db_config.setdefault("OPTIONS", {})
    options.setdefault("connect_timeout", connect_timeout)
    for name, value in KEEPALIVE_OPTIONS.items():
        options.setdefault(name, value)
    return db_config
