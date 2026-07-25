"""Generate the site's social preview (OpenGraph) cards.

Why this exists
---------------
Every link pasted into WhatsApp, X, or a Slack/Signal chat renders whatever
``og:image`` the page declares. Before this script the whole site shared one
512x512 favicon, so every link looked identical and none of them looked like a
card. This renders a family of 1200x630 cards -- one per section -- from the
brand assets and real clinic photography, so a shared link carries some of the
page's own character.

The rules the output has to satisfy are set by WhatsApp, which is the strictest
of the platforms we care about (it is also how most of our audience shares
links):

* **1200x630** (1.91:1). WhatsApp needs >=300px wide and an aspect ratio no
  wider than 4:1 to render the large card rather than a small square thumb.
* **Under 600 KB, hard.** Over that WhatsApp silently drops the image and
  unfurls the link with no picture at all -- which is exactly what was
  happening to the old 786 KB ``og-newsletter.png``. We target <300 KB so the
  card survives WhatsApp's own recompression with detail intact.
* **JPEG.** Only JPG/PNG/WebP are supported, and a photographic card is far
  smaller as JPEG than as the RGBA PNG this replaced.

Running it
----------
    uv run --with "fonttools[woff]" python scripts/generate_og_cards.py

Outputs are written to ``static/images/og/`` and committed -- this is a
build-time tool, never called at request time. Re-run it whenever a source
photo or a card's wording changes.

Fonts are converted from the site's own ``.woff2`` files at run time so the
cards use the same Archivo the site's headings use, rather than a lookalike.
That conversion is why ``fonttools[woff]`` is needed above; it is deliberately
not a project dependency, since nothing at request time needs it.

Text is English-only, and that is a limitation rather than a choice. Pillow
here is built without libraqm, so it cannot shape Arabic-script text: the
site's Nastaliq webfont renders as tofu, and while Naskh can be shaped in pure
Python (arabic-reshaper + python-bidi) it would put a visibly different script
on the cards from the one the pages themselves use. This is why the newsletter
card no longer carries the "chiragh shifa" lockup the old hand-made PNG had --
see the note in core/newsletter_page.html. Giving the cards Urdu properly means
either a shaping-capable renderer or pre-rendered transparent-PNG lockups.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES = BASE_DIR / "brand" / "og-sources"
OUTPUT = BASE_DIR / "static" / "images" / "og"
FONTS = BASE_DIR / "static" / "fonts"

WIDTH, HEIGHT = 1200, 630

# Brand tokens, from docs/brand-guidelines.md section 3. Named rather than
# inlined so a palette change stays a one-line edit here.
TEAL_DEEP = "#0A3E48"
PALE_AQUA = "#A0E0E8"
CORAL = "#EF5148"
AMBER_DARK = "#E8B04A"
PAPER = "#F2F6F6"
WHITE = "#FFFFFF"

# The photo occupies the right of the card and is faded into the teal ground
# across this span, so the left column always has flat colour to set text on.
FADE_START, FADE_END = 470, 980

# Left column geometry.
MARGIN = 78
TEXT_MAX_WIDTH = 560


@dataclass(frozen=True)
class Card:
    """One output card.

    ``photo_focus`` is the point of the source photo to keep centred when it is
    cropped to the panel's aspect ratio, as (x, y) fractions -- 0.5/0.5 is a
    plain centre crop. Faces and hands sit off-centre in most of these frames,
    so most cards nudge it.

    ``photo_zoom`` scales the crop in, anchored on that focus point.
    """

    slug: str
    title: str
    eyebrow: str = ""
    kicker: str = ""
    photo: str = ""
    accent: str = CORAL
    photo_focus: tuple[float, float] = (0.5, 0.5)
    photo_zoom: float = 1.0
    photo_shift_y: float = 0.0
    title_size: int = 74


CARDS: list[Card] = [
    # Sitewide default -- what any page without its own card falls back to,
    # replacing the bare favicon. The busy corridor reads as "this place is
    # used", which is the single most useful thing a cold link can say.
    Card(
        slug="default",
        title="The Thandkoi Clinics",
        kicker="THANDKOI, SWABI",
        photo="corridor.jpg",
        photo_focus=(0.55, 0.45),
        title_size=68,
    ),
    # Donate is the link most likely to be forwarded into a family group chat,
    # so it is the one card whose wording is doing real work. Amber, not coral:
    # brand-guidelines.md reserves amber for the donate CTA and explicitly
    # rules coral out of anything CTA-shaped.
    Card(
        slug="donate",
        eyebrow="DONATE",
        title="Your Zakat, delivered whole",
        kicker="FREE CONSULTATIONS · FREE MEDICINE",
        photo="pharmacy.jpg",
        accent=AMBER_DARK,
        photo_focus=(0.42, 0.5),
        title_size=62,
    ),
    Card(
        slug="about",
        eyebrow="ABOUT US",
        title="A family-run clinic",
        kicker="NOT-FOR-PROFIT · ZAKAT & SADAQA FUNDED",
        photo="three-generations.jpg",
        photo_focus=(0.55, 0.42),
    ),
    Card(
        slug="our-work",
        eyebrow="OUR WORK",
        title="Primary care, free at the point of need",
        kicker="CONSULT · DIAGNOSE · DISPENSE",
        photo="bp-check.jpg",
        photo_focus=(0.45, 0.5),
        title_size=54,
    ),
    Card(
        slug="team",
        eyebrow="OUR TEAM",
        title="The people behind the clinic",
        kicker="DOCTORS · NURSES · DIETITIANS",
        photo="staff-lineup.jpg",
        photo_focus=(0.5, 0.45),
        title_size=58,
    ),
    Card(
        slug="gallery",
        eyebrow="GALLERY",
        title="A day at the clinic",
        kicker="PHOTOGRAPHS FROM THANDKOI",
        photo="paediatric.jpg",
        photo_focus=(0.5, 0.45),
    ),
    Card(
        slug="contact",
        eyebrow="CONTACT",
        title="Find us in Thandkoi",
        kicker="SWABI, KHYBER PAKHTUNKHWA",
        photo="corridor.jpg",
        photo_focus=(0.5, 0.5),
    ),
    Card(
        slug="donors-partners",
        eyebrow="DONORS & PARTNERS",
        title="Who makes this possible",
        kicker="WITH THANKS",
        # The inauguration-day photo, rather than another clinical shot: this
        # page is about the people who made the clinic exist at all.
        photo="inauguration.jpg",
        accent=AMBER_DARK,
        photo_focus=(0.55, 0.4),
    ),
    Card(
        slug="reports",
        eyebrow="REPORTS",
        title="What the clinic did today",
        kicker="PUBLISHED DAILY",
        photo="thermometer.jpg",
        photo_focus=(0.45, 0.45),
        title_size=62,
    ),
    Card(
        slug="camps",
        eyebrow="MEDICAL CAMPS",
        title="Care beyond the clinic walls",
        kicker="OUTREACH IN SWABI",
        photo="camp-team.jpg",
        photo_focus=(0.5, 0.45),
        title_size=58,
    ),
    # The newsletter keeps its clay-lamp (chiragh) motif -- CLAUDE.md records
    # that as the newsletter's branding. What it loses is the retired Urdu
    # lockup and the hardcoded "MAY-JUNE 2026", which was wrong on every issue
    # but one, since this single static card serves every newsletter page.
    Card(
        slug="newsletter",
        eyebrow="NEWSLETTER",
        title="The Thandkoi Beacon",
        kicker="DISPATCHES FROM THE CLINIC",
        photo="chiragh.jpg",
        photo_focus=(0.5, 0.42),
        title_size=68,
    ),
]


def load_fonts() -> dict[str, Path]:
    """Convert the site's woff2 webfonts to ttf so Pillow can use them.

    Pillow reads ttf/otf but not woff2, and these are the same variable fonts
    the site serves, so converting is preferable to shipping a second copy of
    Archivo in a different format that could drift from it.
    """
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        sys.exit(
            "fontTools is required. Run this with:\n"
            '  uv run --with "fonttools[woff]" python scripts/generate_og_cards.py'
        )

    out_dir = Path(__file__).resolve().parent / ".fontcache"
    out_dir.mkdir(exist_ok=True)
    converted = {}
    for name, rel in {
        "archivo": "archivo/archivo-latin-700-800.woff2",
        "public-sans": "public-sans/public-sans-latin-400-600.woff2",
    }.items():
        target = out_dir / f"{name}.ttf"
        if not target.exists():
            font = TTFont(FONTS / rel)
            font.flavor = None
            font.save(target)
        converted[name] = target
    return converted


def variable(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Load a variable font at a specific optical weight."""
    font = ImageFont.truetype(str(path), size)
    try:
        font.set_variation_by_axes([weight])
    except OSError:
        # Static font, or a Pillow build without variation support -- the
        # default instance is still the right family, just fixed-weight.
        pass
    return font


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    tracking: float = 0.0,
) -> int:
    """Draw text with letter-spacing, returning the width drawn.

    Pillow has no tracking option, so wide-spaced small caps -- which the
    eyebrow and kicker both need -- have to be drawn a character at a time.
    """
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + tracking
    return int(x - xy[0])


def wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    """Greedy word wrap to a pixel width."""
    lines: list[str] = []
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


PANEL_WIDTH = WIDTH - FADE_START


def photo_panel(card: Card) -> Image.Image | None:
    """Crop and fade a source photo into the card's right-hand panel.

    Only the panel region is rendered, not the whole card -- everything left of
    ``FADE_START`` is flat teal anyway. That matters for source quality: the
    panel is 730px wide rather than 1200, so a photo only has to cover 730px
    before it is being upscaled. The lamp on the newsletter card is the binding
    case, since the only copy of it we still have is small.

    The result is masked with a horizontal gradient so the photo dissolves into
    the teal ground rather than sitting in a hard-edged box.
    """
    if not card.photo:
        return None
    source_path = SOURCES / card.photo
    if not source_path.exists():
        print(f"  ! missing source photo {card.photo}, rendering without it")
        return None

    photo = Image.open(source_path).convert("RGB")

    # Scale so the photo covers the panel, honouring the card's zoom, then
    # crop around the focus point.
    scale = max(PANEL_WIDTH / photo.width, HEIGHT / photo.height) * card.photo_zoom
    photo = photo.resize(
        (max(1, round(photo.width * scale)), max(1, round(photo.height * scale))),
        Image.LANCZOS,
    )

    focus_x, focus_y = card.photo_focus
    left = round((photo.width - PANEL_WIDTH) * focus_x)
    top = round((photo.height - HEIGHT) * focus_y + card.photo_shift_y)
    left = max(0, min(left, photo.width - PANEL_WIDTH))
    top = max(0, min(top, photo.height - HEIGHT))
    photo = photo.crop((left, top, left + PANEL_WIDTH, top + HEIGHT))

    # Horizontal alpha ramp across the panel: transparent at its left edge,
    # fully opaque by FADE_END, smoothstepped so there is no banding edge.
    ramp = Image.new("L", (PANEL_WIDTH, 1))
    pixels = ramp.load()
    opaque_at = FADE_END - FADE_START
    for x in range(PANEL_WIDTH):
        if x >= opaque_at:
            value = 1.0
        else:
            t = x / opaque_at
            value = t * t * (3 - 2 * t)
        pixels[x, 0] = round(value * 255)

    photo.putalpha(ramp.resize((PANEL_WIDTH, HEIGHT), Image.NEAREST))
    return photo


def logo_badge(size: int) -> Image.Image:
    """The logo mark on a white disc, as it appears on the newsletter card."""
    mark = Image.open(BASE_DIR / "brand" / "favicon-512.png").convert("RGBA")
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    disc = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(disc).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    disc = disc.resize((size, size), Image.LANCZOS)

    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    badge.paste(white, (0, 0), disc)

    inset = round(size * 0.11)
    inner = size - inset * 2
    mark = mark.resize((inner, inner), Image.LANCZOS)
    badge.paste(mark, (inset, inset), mark)
    return badge


def render(card: Card, fonts: dict[str, Path]) -> Image.Image:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), TEAL_DEEP)

    panel = photo_panel(card)
    if panel is not None:
        canvas.alpha_composite(panel, (FADE_START, 0))

    draw = ImageDraw.Draw(canvas)

    archivo = fonts["archivo"]
    wordmark_font = variable(archivo, 25, 700)
    eyebrow_font = variable(archivo, 21, 700)
    kicker_font = variable(archivo, 21, 700)
    title_font = variable(archivo, card.title_size, 800)

    # Masthead: logo disc plus wordmark, top-left on every card.
    badge_size = 62
    badge = logo_badge(badge_size)
    canvas.alpha_composite(badge, (MARGIN, 50))
    draw_tracked(
        draw,
        (MARGIN + badge_size + 22, 50 + badge_size // 2 - 15),
        "THE THANDKOI CLINICS",
        wordmark_font,
        PAPER,
        tracking=2.4,
    )

    # Title block is anchored from the bottom rule upwards, so cards with
    # one-line and three-line titles still share a baseline.
    rule_y = 548
    lines = wrap(draw, card.title, title_font, TEXT_MAX_WIDTH)
    line_height = round(card.title_size * 1.1)
    title_bottom = rule_y - 74
    title_top = title_bottom - line_height * len(lines)

    if card.eyebrow:
        draw_tracked(
            draw,
            (MARGIN, title_top - 46),
            card.eyebrow,
            eyebrow_font,
            PALE_AQUA,
            tracking=4.2,
        )

    for index, line in enumerate(lines):
        draw.text(
            (MARGIN, title_top + index * line_height),
            line,
            font=title_font,
            fill=WHITE,
        )

    # Accent rule + kicker along the bottom.
    draw.rectangle((MARGIN, rule_y, MARGIN + 46, rule_y + 5), fill=card.accent)
    if card.kicker:
        draw_tracked(
            draw,
            (MARGIN + 68, rule_y - 8),
            card.kicker,
            kicker_font,
            PAPER,
            tracking=2.4,
        )

    return canvas.convert("RGB")


def save(image: Image.Image, path: Path, budget_kb: int = 300) -> int:
    """Write a JPEG that fits the byte budget, stepping quality down as needed.

    WhatsApp's hard ceiling is 600 KB; the default budget is half that so the
    card still has detail left after WhatsApp recompresses it.
    """
    for quality in (88, 84, 80, 76, 72, 68):
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
        if buffer.tell() <= budget_kb * 1024:
            break
    path.write_bytes(buffer.getvalue())
    return buffer.tell()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()

    print(f"Rendering {len(CARDS)} cards to {OUTPUT.relative_to(BASE_DIR)}/\n")
    over_budget = []
    for card in CARDS:
        image = render(card, fonts)
        path = OUTPUT / f"og-{card.slug}.jpg"
        written = save(image, path)
        flag = "" if written <= 600 * 1024 else "  <-- OVER WHATSAPP LIMIT"
        if flag:
            over_budget.append(card.slug)
        print(f"  og-{card.slug}.jpg  {written / 1024:6.1f} KB{flag}")

    if over_budget:
        sys.exit(f"\nCards exceed WhatsApp's 600 KB cap: {', '.join(over_budget)}")
    print("\nAll cards within budget.")


if __name__ == "__main__":
    main()
