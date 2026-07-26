"""Tests for the database connection hardening (2026-07-26 outage follow-up).

These exist because the defect they guard against is invisible: an *absent*
``connect_timeout`` looks exactly like a present one until the network fails,
and then it costs a 30-minute outage. See ``config.database``'s module
docstring for the incident.

``config.database`` is a plain module by design (same rationale as
``config.observability``), so most of this needs no Django DB or settings
access. The final section is the one that does — it asserts the live settings
module actually *calls* the helper, because a guard on the helper alone would
keep passing if a settings module quietly stopped wiring it up.
"""

import logging

import pytest
from django.conf import settings

from config import database

# --- Bounded connect ---------------------------------------------------------


def _postgres_config(**extra):
    """A minimal DATABASES entry shaped like the one ``env.db()`` returns."""
    return {"ENGINE": "django.db.backends.postgresql", **extra}


def test_connect_timeout_is_applied_when_the_url_expressed_no_opinion():
    """The whole point: libpq's "wait forever" default is replaced by a bound."""
    config = database.harden_connection(_postgres_config())

    assert config["OPTIONS"]["connect_timeout"] == (
        database.DEFAULT_CONNECT_TIMEOUT_SECONDS
    )


def test_the_default_connect_timeout_is_a_usable_positive_bound():
    """Zero would mean "wait indefinitely"; libpq clamps anything under 2 up to 2.

    A default of 0 or 1 would silently reintroduce the outage (0) or be
    misleading about what actually takes effect (1), so the constant has to
    clear that floor.
    """
    assert database.DEFAULT_CONNECT_TIMEOUT_SECONDS >= 2


def test_an_explicit_connect_timeout_overrides_the_default():
    config = database.harden_connection(_postgres_config(), connect_timeout=11)

    assert config["OPTIONS"]["connect_timeout"] == 11


def test_a_timeout_pinned_on_the_database_url_is_never_clobbered():
    """``?connect_timeout=`` on DATABASE_URL lands in OPTIONS via ``env.db()``.

    An operator who has pinned a value in the connection string has expressed
    an opinion; this helper only supplies a default where none was given.
    """
    config = database.harden_connection(
        _postgres_config(OPTIONS={"connect_timeout": 30}),
    )

    assert config["OPTIONS"]["connect_timeout"] == 30


def test_unrelated_options_from_the_url_survive():
    """Neon requires sslmode; hardening must add to OPTIONS, never replace it."""
    config = database.harden_connection(
        _postgres_config(OPTIONS={"sslmode": "require"}),
    )

    assert config["OPTIONS"]["sslmode"] == "require"
    assert "connect_timeout" in config["OPTIONS"]


# --- Dead-socket detection ---------------------------------------------------


def test_keepalives_are_enabled_for_persistent_connections():
    """CONN_MAX_AGE keeps sockets between requests; they need liveness probing.

    Without these, a query on a connection whose peer vanished blocks forever —
    the same failure as the unbounded connect, reached through a different door.
    """
    options = database.harden_connection(_postgres_config())["OPTIONS"]

    assert options["keepalives"] == 1
    assert options["keepalives_idle"] > 0
    assert options["keepalives_interval"] > 0
    assert options["keepalives_count"] > 0


def test_keepalives_pinned_on_the_database_url_are_never_clobbered():
    config = database.harden_connection(
        _postgres_config(OPTIONS={"keepalives_idle": 5}),
    )

    assert config["OPTIONS"]["keepalives_idle"] == 5


# --- DB_CONNECT_TIMEOUT parsing ----------------------------------------------
#
# These exist because the obvious spelling, env.int("DB_CONNECT_TIMEOUT", ...),
# raises ValueError on a blank value and kills every worker at boot. Blank is
# the natural state of a sync:false key added in the Render dashboard but not
# filled in, so this is the likely case, not the exotic one.


@pytest.mark.parametrize("raw", ["", None], ids=["blank", "unset"])
def test_an_unset_connect_timeout_falls_back_instead_of_raising(raw):
    """The boot-crash case. Must return a value, never raise."""
    assert database.parse_connect_timeout(raw) == (
        database.DEFAULT_CONNECT_TIMEOUT_SECONDS
    )


@pytest.mark.parametrize("raw", ["5s", "abc", "1.5", [], "  "])
def test_an_unparseable_connect_timeout_falls_back_instead_of_raising(raw):
    """A typo in an operational dial must degrade, never take the site down."""
    assert database.parse_connect_timeout(raw) == (
        database.DEFAULT_CONNECT_TIMEOUT_SECONDS
    )


def test_a_valid_connect_timeout_is_honoured():
    assert database.parse_connect_timeout("15") == 15


@pytest.mark.parametrize(
    "raw", ["0", "1", "-3"], ids=["zero", "below_floor", "negative"]
)
def test_a_connect_timeout_below_libpq_s_floor_is_refused(raw):
    """0 means "wait forever" to libpq — the exact default this module replaces.

    Honouring it would let a dashboard typo silently reinstate the 2026-07-26
    outage. Values under libpq's floor of 2 are clamped up by libpq anyway, so
    accepting them would only misreport what is actually in effect.
    """
    assert database.parse_connect_timeout(raw) == (
        database.DEFAULT_CONNECT_TIMEOUT_SECONDS
    )


def test_a_refused_connect_timeout_is_logged_so_it_stays_discoverable(caplog):
    """Silently ignoring an operator's setting would be its own trap."""
    with caplog.at_level(logging.WARNING):
        database.parse_connect_timeout("0")

    assert "DB_CONNECT_TIMEOUT" in caplog.text


# --- Backend safety ----------------------------------------------------------


def test_a_non_postgresql_backend_is_left_untouched():
    """These are libpq-specific options; another backend would raise on connect."""
    config = database.harden_connection(
        {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
    )

    assert "OPTIONS" not in config


def test_an_entry_with_no_engine_is_left_untouched():
    assert database.harden_connection({}) == {}


# --- The wiring, not just the helper -----------------------------------------


def test_the_live_settings_module_actually_hardens_the_default_connection():
    """Asserts the wiring, which the helper's own tests cannot.

    The tests above would all still pass if ``config/settings/dev.py`` (and by
    the same shape, ``prod.py``) stopped calling ``harden_connection`` — the
    helper would remain perfectly correct and perfectly unused. This reads the
    settings Django is actually running with.
    """
    options = settings.DATABASES["default"]["OPTIONS"]

    assert options["connect_timeout"] == database.DEFAULT_CONNECT_TIMEOUT_SECONDS
    assert options["keepalives"] == 1
