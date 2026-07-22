"""Install the memory-only upload handler *before* the body is ever parsed.

This exists as middleware, and not as a line in the upload view, because of
where Django parses the multipart body relative to where a view runs.

``CsrfViewMiddleware.process_view`` validates the CSRF token on every POST by
reading ``request.POST`` (``request.POST.get("csrfmiddlewaretoken")`` — it
does this unconditionally on a POST, before falling back to the header). That
read parses the multipart body using Django's *default* upload handlers
(``MemoryFileUploadHandler`` + ``TemporaryFileUploadHandler``) and locks
``request.upload_handlers``. It happens in ``process_view`` — *before* the
view function executes — so a handler swap inside the view is always too late
and raises ``"You cannot set the upload handlers after the upload has been
processed."`` (the production 500 this middleware fixes).

The Django-documented ``csrf_exempt`` (outer) / ``csrf_protect`` (inner) view
split can't rescue it either: Wagtail wraps every ``register_admin_urls`` view
in ``wagtail.admin.auth.require_admin_access``, whose inner ``decorated_view``
has no ``functools.wraps``, so a ``csrf_exempt`` marker set on our view never
propagates out to the callback the middleware inspects.

So the swap must run earlier than any body-parsing middleware. Listed before
``CsrfViewMiddleware`` in ``MIDDLEWARE``, this installs the memory-only handler
for the one clinic-export upload path. That does two things at once:

* the upload no longer 500s — the handler is set while the body is still
  unparsed, so the CSRF check parses it with the memory handler already in
  place; and
* privacy invariant #1 is restored — with no ``TemporaryFileUploadHandler`` in
  the chain, an oversized export is declined outright by the memory handler and
  never spooled to a temp file on disk (see ``apps.pipeline.admin_views`` for
  the guarantee this preserves), instead of being written to disk by the
  default handler chain before the view could swap it.

Scoped deliberately to the upload path only: swapping the handler chain
globally would break Wagtail's own admin image/document uploads (which rely on
``TemporaryFileUploadHandler`` to spool files larger than
``FILE_UPLOAD_MAX_MEMORY_SIZE``).
"""

from __future__ import annotations

from django.core.files.uploadhandler import MemoryFileUploadHandler
from django.urls import NoReverseMatch, reverse


class MemoryOnlyUploadHandlerMiddleware:
    """Force the clinic-export upload onto the memory-only handler, pre-CSRF.

    Must be listed **before** ``django.middleware.csrf.CsrfViewMiddleware`` in
    ``MIDDLEWARE`` — see the module docstring for why.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and self._is_export_upload(request):
            # Set before request.POST/FILES is touched anywhere downstream —
            # crucially before CsrfViewMiddleware.process_view parses the body.
            request.upload_handlers = [MemoryFileUploadHandler(request)]
        return self.get_response(request)

    @staticmethod
    def _is_export_upload(request) -> bool:
        try:
            return request.path == reverse("pipeline:upload_export")
        except NoReverseMatch:  # pragma: no cover - URL is always registered
            return False
