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
        help_text="RTL tagline (currently Pashto), rendered right-to-left.",
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


CIRCLE_OF_CARE_STAGE_COUNT_MESSAGE = (
    "Exactly 6 stages are required — the wheel's segments and label positions "
    "are fixed for a 6-part circle."
)


class CircleOfCareStageBlock(blocks.StructBlock):
    """One stage of a patient's visit, on the "Quality of Care" wheel.

    ``short`` is the on-ring label (the wedge geometry is fixed-width, so it
    needs to stay brief); ``name`` + ``desc`` fill the centre hub once a stage
    is selected.
    """

    name = blocks.CharBlock(
        max_length=80, help_text="Full stage name, shown in the hub."
    )
    short = blocks.CharBlock(
        max_length=28,
        help_text="On-ring label — keep brief so it fits the wedge (the "
        "longest example, 'Doctor's Consultation', is 21 characters).",
    )
    desc = blocks.TextBlock(
        help_text="Detail shown in the hub when this stage is selected."
    )

    class Meta:
        icon = "list-ul"
        label = "Care stage"


class CircleOfCareBlock(blocks.StructBlock):
    """The six-wedge "Quality of Care" wheel → ``circle_of_care.html`` partial.

    The wheel's SVG segments and on-ring label positions are fixed for exactly
    six stages (external design handoff, "Circle of Care Homepage Update"), so
    ``clean()`` refuses to save any other count rather than silently
    mis-rendering a partial wheel.
    """

    heading = blocks.CharBlock(
        required=False,
        max_length=120,
        help_text='Defaults to "Quality of Care" if left blank.',
    )
    stages = blocks.ListBlock(CircleOfCareStageBlock())

    def clean(self, value):
        result = super().clean(value)
        if len(result.get("stages") or []) != 6:
            raise StructBlockValidationError(
                block_errors={"stages": [CIRCLE_OF_CARE_STAGE_COUNT_MESSAGE]}
            )
        return result

    class Meta:
        icon = "crosshairs"
        label = "Quality of care circle"
        template = "blocks/circle_of_care_block.html"


CONSENT_REQUIRED_MESSAGE = "Confirm consent before publishing this photo."


class ConsentedImageBlock(blocks.StructBlock):
    """A photograph that may show an identifiable person, gated on consent.

    Plan 04 establishes this convention (it has no non-staff photo surface of
    its own yet — team/staff shots are implicitly consented as professional
    portraits) so **Plan 06** (camp / community photography) reuses it rather
    than inventing a second pattern. Per brand-guidelines.md §5 (dignity &
    consent): an image cannot be saved unless the admin ticks
    ``consent_confirmed``.

    Plan 06 is this block's first real user (Newsletter body photos, Camp
    Report photos), so it's also where the block first gets a render
    template — ``blocks/consented_image_block.html`` — shared by every
    StreamField that reuses this block, rather than each caller inventing its
    own markup for the same photo+caption shape.
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
                block_errors={"consent_confirmed": [CONSENT_REQUIRED_MESSAGE]}
            )
        return result

    class Meta:
        icon = "image"
        label = "Photo (consent required)"
        template = "blocks/consented_image_block.html"


# --- Plan 11 D14: Newsletter redesign ("The Thandkoi Beacon") ---------------


class NewsletterStatBlock(blocks.StructBlock):
    """One card in a newsletter issue's impact-stat band."""

    value = blocks.CharBlock(max_length=16, help_text='e.g. "763" or "64%"')
    label = blocks.CharBlock(max_length=90)

    class Meta:
        icon = "chart-line"
        label = "Stat"


class NewsletterStatBandBlock(blocks.StructBlock):
    """The issue's impact numbers, at a glance.

    Renders through the same ``stat_band.html`` partial Home's live impact
    band uses (Plan 11 D13) — here fed CMS-entered per-issue figures rather
    than a live ``DailyAggregate`` query, since a past issue's numbers are a
    fixed historical snapshot, not something to recompute on every render.
    """

    heading = blocks.CharBlock(default="Our impact, at a glance", max_length=120)
    updated = blocks.CharBlock(
        required=False, max_length=60, help_text='e.g. "May–June 2026"'
    )
    stats = blocks.ListBlock(NewsletterStatBlock(), max_num=3)

    class Meta:
        icon = "table"
        label = "Impact stat band"
        template = "blocks/newsletter_stat_band_block.html"


class NewsletterHighlightsBlock(blocks.StructBlock):
    """A short bulleted "highlights this issue" list, coral cross bullets."""

    heading = blocks.CharBlock(default="Highlights this issue", max_length=90)
    items = blocks.ListBlock(
        blocks.RichTextBlock(
            features=["bold"], help_text="Keep it to a sentence; bold the lead phrase."
        ),
        max_num=6,
    )

    class Meta:
        icon = "list-ul"
        label = "Highlights"
        template = "blocks/newsletter_highlights_block.html"


class NewsletterPullStatBlock(blocks.StructBlock):
    """A small inline stat beside an "In focus" split's body text."""

    value = blocks.CharBlock(max_length=16)
    label = blocks.CharBlock(max_length=90)

    class Meta:
        icon = "chart-line"
        label = "Pull stat"


class NewsletterFeatureSplitBlock(blocks.StructBlock):
    """An "In focus" photo + text split — the redesign's story sections.

    Distinct from ``partials/sections/feature_split.html`` (which a page
    template calls directly with context vars, and wraps its own
    ``<section>``): this is a StreamField block an editor repeats, so its own
    template renders standalone, matching how ``HeroBlock``/``CircleOfCareBlock``
    each render a full section from block data.
    """

    eyebrow = blocks.CharBlock(
        required=False,
        max_length=60,
        help_text='Optional, e.g. "In focus" — set on the first split only if wanted.',
    )
    heading = blocks.CharBlock(max_length=90)
    text = blocks.RichTextBlock(features=["bold", "italic", "link"])
    photo = ConsentedImageBlock()
    reverse = blocks.BooleanBlock(
        required=False, help_text="Show the photo on the right instead of the left."
    )
    pull_stats = blocks.ListBlock(NewsletterPullStatBlock(), max_num=2)

    class Meta:
        icon = "image"
        label = "In-focus split"
        template = "blocks/newsletter_feature_split_block.html"
