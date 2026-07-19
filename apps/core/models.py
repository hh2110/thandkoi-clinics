"""
Core content models.

For Plan 01 this is just a minimal Wagtail ``HomePage`` placeholder so the site
has a servable root page and later plans have a page type to extend. Real
homepage fields (mission, impact numbers, latest report) arrive in later plans.
"""

from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page


class HomePage(Page):
    """The site's root page. Intentionally minimal for the foundation step."""

    intro = RichTextField(
        blank=True,
        help_text="Short introductory text shown on the home page.",
    )

    content_panels = [
        *Page.content_panels,
        FieldPanel("intro"),
    ]

    # Only one HomePage, sitting directly under the Wagtail root.
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]
    subpage_types: list[str] = []

    class Meta:
        verbose_name = "Home page"
