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

#: Seconds libpq may spend establishing a connection before giving up.
#:
#: libpq's default is ``0`` — wait indefinitely — which is what turned a
#: network blip into an outage. Note libpq silently clamps any positive value
#: below 2 up to 2 seconds, so values of 0 or 1 are not meaningfully
#: expressible; 5 is comfortably above that floor while still failing fast
#: enough to stay inside gunicorn's worker timeout.
#:
#: Sized against the real path rather than guessed: the app and its database
#: are co-located (Render ``singapore`` / Neon ``aws-ap-southeast-1``), where a
#: healthy connect is milliseconds. The margin here is for a Neon compute
#: resuming from scale-to-zero, not for network round trips.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5

#: TCP keepalive probing for connections that are already established.
#:
#: ``connect_timeout`` alone would still leave a gap. ``CONN_MAX_AGE`` is 60 in
#: production, so workers hold persistent connections between requests, and the
#: same vanished-network fault can strand a query on a socket whose peer is
#: gone. Without keepalives the kernel does not probe such a socket and the
#: read blocks indefinitely — the identical failure shape, just reached through
#: a different door.
#:
#: Values give up after roughly idle + (interval x count) = 60s of silence.
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
