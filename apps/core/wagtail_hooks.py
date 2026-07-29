"""Register core app snippets in the Wagtail admin.

Mirrors ``apps.pipeline.wagtail_hooks``'s ``SnippetViewSet`` pattern (no
in-repo precedent for an *editor-authored* snippet existed before this — the
pipeline app's two registered snippets are read-mostly audit trails).
"""

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from apps.core.models import UpcomingEvent


class UpcomingEventViewSet(SnippetViewSet):
    """Admin listing for Plan 19's "Upcoming events" home-page card.

    ``menu_order`` sits low (near core content, unlike the pipeline app's
    audit-trail snippets at 9100+) since this is content an admin edits
    directly, not something they occasionally check.
    """

    model = UpcomingEvent
    icon = "date"
    menu_label = "Upcoming events"
    menu_order = 200
    list_display = ("date", "title", "link_url")
    ordering = ["date"]


register_snippet(UpcomingEventViewSet)
