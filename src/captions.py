"""PIL-rendered captions.

MoviePy's TextClip (via ImageMagick) has lousy stroke rendering and can't
anti-alias well at smaller sizes. We render captions here with PIL and hand
back a transparent PNG that MoviePy can composite as a plain ImageClip.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


DEFAULT_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def _wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Greedy word-wrap by measuring with the actual font."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_caption(
    text: str,
    canvas_w: int,
    canvas_h: int,
    fontsize: int,
    font_path: str = DEFAULT_FONT,
    text_padding_x: int = 36,
    text_padding_y: int = 20,
    line_spacing: int = 10,
    bg_opacity: int = 170,
    shadow_offset: int = 2,
) -> Image.Image:
    """Return an RGBA image sized (canvas_w, canvas_h) with the caption
    drawn at the bottom on a rounded dark background. Transparent elsewhere.
    """
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, fontsize)

    inner_w = canvas_w - 2 * text_padding_x - 60  # keep text away from edges
    lines = _wrap_to_width(draw, text, font, inner_w)

    # Measure block
    line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    block_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
    block_w = max(draw.textlength(ln, font=font) for ln in lines) if lines else 0

    # Background box (rounded) sits with some padding around the text
    bg_w = int(block_w + 2 * text_padding_x)
    bg_h = int(block_h + 2 * text_padding_y)
    bg_x = (canvas_w - bg_w) // 2
    bg_y = canvas_h - bg_h - 40  # bottom margin

    radius = 18
    draw.rounded_rectangle(
        (bg_x, bg_y, bg_x + bg_w, bg_y + bg_h),
        radius=radius,
        fill=(0, 0, 0, bg_opacity),
    )

    # Draw each line centered, with a soft drop shadow for readability
    y = bg_y + text_padding_y
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        x = (canvas_w - tw) // 2
        # Shadow — a slightly blurred darker pass, offset
        shadow_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_img)
        sdraw.text((x + shadow_offset, y + shadow_offset), ln, font=font, fill=(0, 0, 0, 220))
        shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(1.2))
        img.alpha_composite(shadow_img)
        # Main text
        draw.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
        y += line_h + line_spacing

    return img


def render_caption_to_file(text: str, out_path: Path, **kwargs) -> Path:
    img = render_caption(text, **kwargs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
