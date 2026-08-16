from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        """Clear the page cache whenever an editor publishes (Plan 24 D4).

        Connected here rather than at module scope so it is wired exactly once,
        after the app registry is populated. Wagtail's signals are imported
        inside the method for the same reason.

        Whole-cache invalidation, deliberately: publishing is rare on this site
        and a partial eviction that misses a path would leave withdrawn content
        publicly readable — a correctness bug traded for an optimisation nobody
        needs at this traffic level.
        """
        from django.db.models.signals import post_delete, post_save
        from wagtail.signals import page_published, page_unpublished

        from apps.core.middleware import clear_page_cache, clear_page_cache_for_model

        # dispatch_uid keeps a double-import of this module (autoreload, tests)
        # from connecting the receiver twice.
        page_published.connect(
            clear_page_cache, dispatch_uid="core.clear_page_cache.published"
        )
        page_unpublished.connect(
            clear_page_cache, dispatch_uid="core.clear_page_cache.unpublished"
        )

        # Pages are not the only thing rendered into a cached page. Snippets
        # (donors, partners, services, team members, upcoming events) and the
        # settings singletons (ContactBankSettings) are edited in the admin and
        # saved **without any page publish**, so the two signals above never
        # fire for them. Without this, an editor correcting the clinic's bank
        # details would see the old ones served for up to CACHE_PAGE_SECONDS —
        # three hours of wrong account numbers on a donations page, which is
        # not a staleness cost worth paying for compute.
        #
        # Scoped to the snippet and settings registries rather than a blanket
        # post_save: an export upload writes hundreds of DeidentifiedVisit rows
        # in one request, and clearing the cache once per row would be pure
        # waste. Those rows reach the public site only via a report page, whose
        # publish already fires page_published above.
        # Connected WITHOUT a sender, deliberately. The obvious version —
        # looping over `get_snippet_models()` here and connecting per model —
        # silently wires nothing: snippets are registered in `wagtail_hooks.py`,
        # which Wagtail loads *after* every AppConfig.ready(), so the registry
        # is still empty at this point. That version passed a naive test and
        # failed the real one. The receiver therefore decides at call time,
        # when the registries are populated — see
        # `middleware.clear_page_cache_for_model`.
        post_save.connect(
            clear_page_cache_for_model, dispatch_uid="core.clear_page_cache.save"
        )
        post_delete.connect(
            clear_page_cache_for_model, dispatch_uid="core.clear_page_cache.delete"
        )
