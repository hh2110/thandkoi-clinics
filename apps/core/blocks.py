"""
StreamField blocks for the Home page (Plan 04).

These blocks carry the *data* an admin enters; each one's template does nothing
but map that data onto the matching Plan 03.5 section partial
(``templates/partials/sections/*``). No section markup or CSS is authored here —
the block template ``{% include %}``s a 03.5 partial, so one markup source serves
both the StreamField block and any plain view (Plan 03.5 decision).

Numbers and copy are always inputs, never baked in (privacy invariant #3 / the
03.5 "no baked-in numbers" rule): the components render whatever the CMS supplies.
"""

from wagtail import blocks
from wagtail.blocks import StructBlockValidationError
from wagtail.images.blocks import ImageChooserBlock


class ImpactStatBlock(blocks.StructBlock):
    """A single number/label pair for the impact-stat band.

    ``value`` is free text, not a number field, so the admin controls the exact
    formatting the band renders ("120/day", "36k+", "100%"). Real figures are
    entered by hand for now; Plan 08's pipeline supplies computed ones later.
    """

    value = blocks.CharBlock(
        max_length=16,
        help_text='The figure, formatted exactly as it should show, e.g. "36k+".',
    )
    label = blocks.CharBlock(max_length=80, help_text="Short caption under the figure.")

    class Meta:
        icon = "form"
        label = "Impact figure"


class HeroBlock(blocks.StructBlock):
    """Two-column hero → ``partials/sections/hero.html``.

    The primary CTA is a page chooser rather than a hardcoded link so it points
    at a real page (e.g. the Plan 05 Donate page) once one exists, with no code
    change; until then the admin can leave it empty and the button is omitted.
    """

    eyebrow = blocks.CharBlock(required=False, max_length=80)
    headline = blocks.CharBlock(required=False, max_length=140)
    intro = blocks.TextBlock(required=False)
    primary_cta_label = blocks.CharBlock(required=False, max_length=40)
    primary_cta_page = blocks.PageChooserBlock(required=False)
    primary_cta_donate = blocks.BooleanBlock(
        required=False,
        help_text="Style the primary CTA as the amber Zakat/Sadaqa donate button "
        "(brand-guidelines.md §7). Leave off for any other link — amber is "
        "Donate-only.",
    )
    secondary_cta_label = blocks.CharBlock(required=False, max_length=40)
    secondary_cta_page = blocks.PageChooserBlock(required=False)
    tagline = blocks.CharBlock(
        required=False,
        max_length=80,
        help_text="Urdu tagline, rendered right-to-left.",
    )
    image = ImageChooserBlock(required=False)
    media_caption = blocks.CharBlock(
        required=False,
        max_length=80,
        help_text="Shown in the placeholder until a real image is chosen.",
    )
    stat_value = blocks.CharBlock(required=False, max_length=16)
    stat_label = blocks.CharBlock(required=False, max_length=60)

    class Meta:
        icon = "home"
        label = "Hero"
        template = "blocks/hero_block.html"


class ImpactStatsBlock(blocks.StructBlock):
    """Impact-stat band → ``partials/sections/stat_band.html``.

    With no figures entered the band shows its own "coming soon" empty state
    (stat_band.html), so a half-populated Home page never looks broken.
    """

    caption = blocks.CharBlock(required=False, max_length=140)
    stats = blocks.ListBlock(ImpactStatBlock())

    class Meta:
        icon = "table"
        label = "Impact figures"
        template = "blocks/impact_stats_block.html"


class DonateCTABlock(blocks.StructBlock):
    """Teal-Deep donate band → ``partials/sections/cta_band.html``.

    The band is *hidden entirely* until its CTA points somewhere — an internal
    page (the Plan 05 Donate page) or an external URL. Before then the whole
    section renders nothing rather than a dead "Donate" button (Plan 04 decision:
    "points at nothing (hidden) until Plan 05 exists"). See the block template's
    guard.
    """

    heading = blocks.CharBlock(required=False, max_length=120)
    body = blocks.TextBlock(required=False)
    cta_label = blocks.CharBlock(required=False, max_length=40)
    cta_page = blocks.PageChooserBlock(required=False)
    cta_url = blocks.URLBlock(
        required=False,
        help_text="External link, used only if no internal page is chosen.",
    )
    note = blocks.CharBlock(required=False, max_length=120)

    class Meta:
        icon = "pick"
        label = "Donate call to action"
        template = "blocks/donate_cta_block.html"


class ConsentedImageBlock(blocks.StructBlock):
    """A photograph that may show an identifiable person, gated on consent.

    Plan 04 establishes this convention (it has no non-staff photo surface of
    its own yet — team/staff shots are implicitly consented as professional
    portraits) so **Plan 06** (camp / community photography) reuses it rather
    than inventing a second pattern. Per brand-guidelines.md §5 (dignity &
    consent): an image cannot be saved unless the admin ticks
    ``consent_confirmed``.
    """

    image = ImageChooserBlock()
    alt_text = blocks.CharBlock(
        required=False,
        max_length=180,
        help_text="Describe the image for screen-reader users. "
        "Falls back to the image's own title if left blank.",
    )
    caption = blocks.CharBlock(required=False, max_length=180)
    consent_confirmed = blocks.BooleanBlock(
        required=False,
        help_text="Tick to confirm every identifiable person in this photo has "
        "consented to it being published (brand-guidelines.md §5).",
    )

    def clean(self, value):
        """Refuse to save an image without confirmed consent."""
        result = super().clean(value)
        if result.get("image") and not result.get("consent_confirmed"):
            raise StructBlockValidationError(
                block_errors={
                    "consent_confirmed": [
                        "Confirm consent before publishing this photo."
                    ]
                }
            )
        return result

    class Meta:
        icon = "image"
        label = "Photo (consent required)"
