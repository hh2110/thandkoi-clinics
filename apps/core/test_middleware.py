"""Page-cache policy tests (Plan 24 Track A).

Two of these are disclosure guards rather than behaviour tests — caching an
authenticated response, or one that sets a cookie, would hand one visitor's
page to another. They are written against the pure predicates so they stay
readable, and exercised end-to-end through the real client below.
"""

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory, override_settings

from apps.core.middleware import (
    DEFAULT_CACHE_SECONDS,
    PageCacheMiddleware,
    cache_key_for,
    clear_page_cache,
    is_cacheable_request,
    is_scanner_path,
    parse_cache_seconds,
    should_cache_response,
)


@pytest.fixture
def rf():
    return RequestFactory()


def _anon(request):
    request.user = AnonymousUser()
    return request


# --- Which requests may be served from cache --------------------------------


def test_anonymous_get_is_cacheable(rf):
    assert is_cacheable_request(_anon(rf.get("/en/about/"))) is True


@pytest.mark.parametrize("method", ["post", "head", "put", "delete"])
def test_only_get_is_cacheable(rf, method):
    """HEAD is excluded too: a bodyless response must not poison a GET's key."""
    request = _anon(getattr(rf, method)("/en/about/"))
    assert is_cacheable_request(request) is False


@pytest.mark.parametrize(
    "path", ["/admin/", "/admin/pages/", "/django-admin/", "/documents/1/x.pdf"]
)
def test_authenticated_surfaces_are_never_cacheable(rf, path):
    assert is_cacheable_request(_anon(rf.get(path))) is False


@pytest.mark.django_db
def test_a_logged_in_user_is_never_served_from_cache(rf):
    """Disclosure guard: caching a signed-in editor's page would leak it.

    Deliberately asserted on the real `is_authenticated` path rather than on
    the absence of a cookie, so the guard still holds if authentication ever
    stops being cookie-based.
    """
    request = rf.get("/en/about/")
    request.user = User.objects.create_user("editor", password="x")  # noqa: S106

    assert is_cacheable_request(request) is False


# --- Which responses may be stored ------------------------------------------


def test_a_plain_200_is_storable(rf):
    request = _anon(rf.get("/en/about/"))
    assert should_cache_response(request, HttpResponse("hi")) is True


@pytest.mark.parametrize("status", [301, 302, 404, 500, 503])
def test_only_200_is_storable(rf, status):
    request = _anon(rf.get("/en/about/"))
    response = HttpResponse("hi", status=status)
    assert should_cache_response(request, response) is False


def test_a_response_that_sets_a_cookie_is_never_stored(rf):
    """Disclosure guard, and the load-bearing one.

    Refusing on `Set-Cookie` is what keeps any session- or CSRF-establishing
    response out of a shared cache without reasoning about `Vary` at all. If
    this check is removed, one visitor's session cookie is served to the next.
    """
    request = _anon(rf.get("/en/about/"))
    response = HttpResponse("hi")
    response.set_cookie("sessionid", "secret-value")

    assert should_cache_response(request, response) is False


@pytest.mark.parametrize(
    "cache_control", ["no-store", "private", "private, max-age=60", "max-age=0"]
)
def test_an_explicit_no_cache_directive_is_honoured(rf, cache_control):
    request = _anon(rf.get("/en/about/"))
    response = HttpResponse("hi")
    response["Cache-Control"] = cache_control

    assert should_cache_response(request, response) is False


def test_a_streaming_response_is_not_stored(rf):
    """Reading one to store it would consume it, serving an empty body."""
    request = _anon(rf.get("/en/about/"))
    response = StreamingHttpResponse(iter([b"chunk"]))

    assert should_cache_response(request, response) is False


# --- Keys --------------------------------------------------------------------


def test_the_query_string_is_part_of_the_key(rf):
    """The dashboard's date ranges must not collide with each other."""
    a = cache_key_for(rf.get("/en/reports/dashboard/", {"start": "2026-08-01"}))
    b = cache_key_for(rf.get("/en/reports/dashboard/", {"start": "2026-08-02"}))

    assert a != b


def test_locales_get_separate_keys(rf):
    assert cache_key_for(rf.get("/en/about/")) != cache_key_for(rf.get("/ur/about/"))


# --- The TTL dial ------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "not-a-number", "-5"])
def test_a_bad_ttl_degrades_to_the_default(raw):
    """An operational dial must never take the site down on a typo."""
    assert parse_cache_seconds(raw) == DEFAULT_CACHE_SECONDS


def test_zero_is_honoured_as_off():
    """Unlike the other dials, 0 is meaningful here — it is the rollback lever."""
    assert parse_cache_seconds("0") == 0


def test_a_valid_ttl_is_used():
    assert parse_cache_seconds("600") == 600


# --- End to end through the middleware ---------------------------------------


@pytest.fixture
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def _counting_middleware(counter):
    def get_response(request):
        counter["calls"] += 1
        return HttpResponse(f"rendered {counter['calls']}")

    return PageCacheMiddleware(get_response)


@override_settings(CACHE_PAGE_SECONDS="300")
def test_a_second_request_is_served_without_calling_the_view(rf, clean_cache):
    """The whole point: the second crawler hit must not reach the database."""
    counter = {"calls": 0}
    middleware = _counting_middleware(counter)

    first = middleware(_anon(rf.get("/en/about/")))
    second = middleware(_anon(rf.get("/en/about/")))

    assert counter["calls"] == 1
    assert first.content == second.content == b"rendered 1"


@override_settings(CACHE_PAGE_SECONDS="0")
def test_zero_seconds_disables_the_cache_entirely(rf, clean_cache):
    """The no-deploy rollback lever (D8) must really bypass the cache."""
    counter = {"calls": 0}
    middleware = _counting_middleware(counter)

    middleware(_anon(rf.get("/en/about/")))
    middleware(_anon(rf.get("/en/about/")))

    assert counter["calls"] == 2


@override_settings(CACHE_PAGE_SECONDS="300")
def test_publishing_clears_the_cache(rf, clean_cache):
    """Stale published content is the failure mode that matters most here."""
    counter = {"calls": 0}
    middleware = _counting_middleware(counter)

    middleware(_anon(rf.get("/en/about/")))
    clear_page_cache()
    middleware(_anon(rf.get("/en/about/")))

    assert counter["calls"] == 2


# --- Invalidation beyond page publishes (Plan 24) ----------------------------


@pytest.mark.django_db
@override_settings(CACHE_PAGE_SECONDS="300")
def test_saving_a_settings_singleton_clears_the_cache(rf, clean_cache):
    """Bank details must never be served stale.

    `ContactBankSettings` is edited in the admin and saved with **no page
    publish**, so `page_published` never fires for it. Without the
    snippet/settings receivers wired in `CoreConfig.ready`, an editor
    correcting the clinic's account number would see the old one served for up
    to CACHE_PAGE_SECONDS — three hours of wrong bank details on a donations
    page. That is not a staleness cost worth paying for compute.
    """
    from wagtail.models import Site

    from apps.core.models import ContactBankSettings

    counter = {"calls": 0}
    middleware = _counting_middleware(counter)
    middleware(_anon(rf.get("/en/contact/")))

    settings_obj = ContactBankSettings.for_site(Site.objects.first())
    settings_obj.save()

    middleware(_anon(rf.get("/en/contact/")))

    assert counter["calls"] == 2, "saving site settings must invalidate the cache"


@pytest.mark.django_db
@override_settings(CACHE_PAGE_SECONDS="300")
def test_saving_a_public_snippet_clears_the_cache(rf, clean_cache):
    """Same reasoning for snippets rendered on public pages (upcoming events)."""
    from apps.core.factories import UpcomingEventFactory

    counter = {"calls": 0}
    middleware = _counting_middleware(counter)
    middleware(_anon(rf.get("/en/")))

    UpcomingEventFactory()

    middleware(_anon(rf.get("/en/")))

    assert counter["calls"] == 2, "saving a public snippet must invalidate the cache"


@pytest.mark.django_db
@override_settings(CACHE_PAGE_SECONDS="300")
def test_internal_log_snippets_do_not_clear_the_cache(rf, clean_cache):
    """AiCallLog is a snippet but never renders publicly, and one is written on
    *every* AI call — including inside the daily report's auto-publish. Wiring
    it to invalidation would clear the cache repeatedly for no reader-visible
    reason, quietly undoing the compute saving this whole plan exists for."""
    from apps.pipeline.models import AiCallLog

    counter = {"calls": 0}
    middleware = _counting_middleware(counter)
    middleware(_anon(rf.get("/en/")))

    AiCallLog.objects.create(
        call_site="daily_summary",
        model="claude-haiku-4-5",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0,
    )

    middleware(_anon(rf.get("/en/")))

    assert counter["calls"] == 1, "internal log snippets must not clear the cache"


# --- A broken cache must not break the site ----------------------------------


@override_settings(CACHE_PAGE_SECONDS="300")
def test_a_failing_cache_read_still_serves_the_page(rf, clean_cache, monkeypatch):
    """The cache is an optimisation and must never be able to take the site down.

    FileBasedCache touches the filesystem on every read, so a full disk, a
    read-only mount or a permissions change would otherwise raise on *every
    request* — turning a cost optimisation into a total outage. Same principle
    `config/database.py` was written around after the 2026-07-26 outage: a blip
    in a dependency should degrade the site, not wedge it.
    """

    def _boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr("apps.core.middleware.cache.get", _boom)

    counter = {"calls": 0}
    response = _counting_middleware(counter)(_anon(rf.get("/en/about/")))

    assert response.status_code == 200
    assert counter["calls"] == 1


@override_settings(CACHE_PAGE_SECONDS="300")
def test_a_failing_cache_write_still_serves_the_page(rf, clean_cache, monkeypatch):
    """Failing to *store* a page is not a failed request either."""

    def _boom(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr("apps.core.middleware.cache.set", _boom)

    counter = {"calls": 0}
    response = _counting_middleware(counter)(_anon(rf.get("/en/about/")))

    assert response.status_code == 200
    assert counter["calls"] == 1


@pytest.fixture
def site_with_home(db):
    """A HomePage as the default site root, so real URLs actually resolve.

    Mirrors the `home_page` fixture in apps/core/tests.py; duplicated rather
    than imported because that one is module-local.
    """
    from wagtail.models import Page, Site

    from apps.core.factories import HomePageFactory

    root = Page.get_first_root_node()
    home = HomePageFactory(
        parent=root, title="The Thandkoi Clinics", slug="thandkoi-home"
    )
    site = Site.objects.get(is_default_site=True)
    old_root = site.root_page
    site.root_page = home
    site.save()
    if old_root and old_root.pk != home.pk:
        old_root.delete()
    return home


# --- Scanner short-circuit (Plan 24 Track E) ---------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/wp-admin/install.php",
        "/wp-login.php",
        "/xmlrpc.php",
        "/en/wp-admin/setup-config.php",  # language-prefixed by LocaleMiddleware
        "//blog/wp-includes/wlwmanifest.xml",
        "/wp-content/uploads/x.php",
        "/wp-json/wp/v2/users",
        "/en/wp/",
        "/en/wordpress/",
        "/phpmyadmin/index.php",
        "/.env",
        "/.git/config",
        "/examples/x/.env",
        "/shell.aspx",
        "/cmd.jsp",
    ],
)
def test_scanner_paths_are_recognised(path):
    assert is_scanner_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/en/",
        "/en/about/",
        "/en/reports/",
        "/en/reports/2026-08-15/",
        "/en/reports/dashboard/",
        "/ur/about/",
        "/healthz",
        "/readyz",
        "/robots.txt",
        "/admin/",
        "/admin/login/",
        "/documents/1/report.pdf",
        "/static/css/base.css",
        # Generic English words scanners also probe. The same 2026-08-16 scan
        # hit /news/ and /blog/, and this clinic could legitimately publish
        # either — blocking them would break a real page the day it is added.
        "/en/news/",
        "/en/blog/",
        "/en/newsletters/",
        "/en/our-work/",
        # A human mistyping a URL must still reach the branded 404, not the
        # bare one meant for bots.
        "/en/no-such-page/",
        "/en/abuot/",
    ],
)
def test_legitimate_and_mistyped_paths_are_not_short_circuited(path):
    assert is_scanner_path(path) is False


def test_well_known_is_deliberately_not_blocked():
    """404ing an ACME challenge could break TLS renewal for the whole site.

    Recorded as a test so nobody adds it later thinking it was an oversight.
    """
    assert is_scanner_path("/.well-known/acme-challenge/tokenvalue") is False


@pytest.mark.django_db
def test_a_scanner_probe_costs_zero_database_queries(client, django_assert_num_queries):
    """The whole point of Track E.

    Before this, one probe cost three queries — Wagtail's page lookup,
    RedirectMiddleware's redirect lookup, and ContactBankSettings while
    rendering 404.html's footer — and, far more expensively, restarted Neon's
    five-minute idle clock. Asserted over the whole request rather than on the
    middleware in isolation, because the queries came from middleware and
    template rendering, not from any view.
    """
    with django_assert_num_queries(0):
        response = client.get("/wp-admin/install.php")

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_mistyped_url_still_renders_the_branded_404(client, site_with_home):
    """The bare 404 is for bots only; humans keep the real page.

    If this starts failing, the marker list has grown too broad.
    """
    response = client.get("/en/no-such-page/")

    assert response.status_code == 404
    assert b"Not Found" != response.content
    # The branded page extends base.html, so it carries the site chrome.
    assert b"Thandkoi" in response.content


@pytest.mark.django_db
def test_real_pages_still_serve(client, site_with_home):
    assert client.get("/en/").status_code == 200
