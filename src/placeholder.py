"""Local-render fallback: cinematic dark cards with a radial green glow.

Used when Pollinations rate-limits us. On-brand for the Lanterns demo
(dark minimalist teaser aesthetic) and guarantees the pipeline completes.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1152, 648


def _radial_gradient(center_x: int, center_y: int, inner_rgb, outer_rgb, max_radius: int) -> Image.Image:
    """Build a radial gradient as a new RGBA image."""
    img = Image.new("RGB", (W, H), outer_rgb)
    px = img.load()
    for y in range(H):
        for x in range(W):
            dx, dy = x - center_x, y - center_y
            d = math.sqrt(dx * dx + dy * dy)
            t = min(1.0, d / max_radius)
            r = int(inner_rgb[0] * (1 - t) + outer_rgb[0] * t)
            g = int(inner_rgb[1] * (1 - t) + outer_rgb[1] * t)
            b = int(inner_rgb[2] * (1 - t) + outer_rgb[2] * t)
            px[x, y] = (r, g, b)
    return img


def _add_grain(img: Image.Image, strength: int = 8) -> Image.Image:
    """Film-grain overlay for that cinematic feel."""
    rng = random.Random(42)
    noise = Image.new("L", (W, H))
    npx = noise.load()
    for y in range(H):
        for x in range(W):
            npx[x, y] = rng.randint(128 - strength, 128 + strength)
    return Image.blend(img, Image.merge("RGB", [noise] * 3), 0.08)


def _draw_ring(img: Image.Image, cx: int, cy: int, radius: int, thickness: int, color) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    for i in range(thickness):
        draw.ellipse(
            (cx - radius + i, cy - radius + i, cx + radius - i, cy + radius - i),
            outline=color,
            width=1,
        )


def generate_card(scene_index: int, out_path: Path, seed: int | None = None) -> Path:
    """Generate a dark cinematic card with a green glow — Lanterns-teaser aesthetic."""
    rng = random.Random(seed if seed is not None else scene_index)
    # Jitter the glow center so each card looks different
    cx = W // 2 + rng.randint(-120, 120)
    cy = H // 2 + rng.randint(-80, 80)
    img = _radial_gradient(cx, cy, inner_rgb=(10, 60, 30), outer_rgb=(5, 10, 8), max_radius=max(W, H))

    # Blur the gradient slightly for a soft glow
    img = img.filter(ImageFilter.GaussianBlur(radius=18))

    # Add a subtle ring motif
    ring_radius = 180 + rng.randint(-30, 30)
    _draw_ring(img, cx, cy, ring_radius, thickness=3, color=(40, 220, 90, 90))
    _draw_ring(img, cx, cy, ring_radius + 80, thickness=1, color=(40, 220, 90, 40))

    # Film grain
    img = _add_grain(img)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=90)
    return out_path
