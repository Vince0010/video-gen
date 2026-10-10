"""Pollinations.ai image fetch: prompt -> jpg.

Works keyless, but if POLLINATIONS_API_KEY is set we send it as a Bearer
header — unlocks higher quality (flux-pro), no watermark, higher rate limit.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from pathlib import Path

import requests

BASE = "https://image.pollinations.ai/prompt"
WIDTH = 1152
HEIGHT = 648
# Model order to try: lightest free model first, then flux as fallback.
MODELS = ["flux", "turbo"]
BETWEEN_REQUESTS_SEC = 4  # Pollinations free tier throttles aggressively on bursts
MAX_RETRIES = 3


def _get(url: str, params: dict) -> requests.Response:
    headers = {}
    key = os.environ.get("POLLINATIONS_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return requests.get(url, params=params, headers=headers, timeout=120)


WATERMARK_CROP_PX = 60  # strip bottom N px (where Pollinations stamps its mark)


def _strip_watermark(path: Path) -> None:
    """Crop bottom N px and resize back to original dims so downstream math stays simple."""
    from PIL import Image as _Image
    img = _Image.open(path)
    w, h = img.size
    cropped = img.crop((0, 0, w, max(1, h - WATERMARK_CROP_PX)))
    cropped = cropped.resize((w, h), _Image.LANCZOS)
    cropped.save(path, "JPEG", quality=90)


def fetch_image(prompt: str, out_path: Path, seed: int | None = None) -> Path:
    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{BASE}/{encoded}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        for model in MODELS:
            params = {"width": WIDTH, "height": HEIGHT, "nologo": "true", "model": model}
            if seed is not None:
                params["seed"] = seed
            try:
                r = _get(url, params)
                if r.ok and r.headers.get("content-type", "").startswith("image/"):
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(r.content)
                    _strip_watermark(out_path)
                    return out_path
                last_err = requests.HTTPError(f"{r.status_code} on model={model}: {r.text[:120]}")
            except requests.RequestException as e:
                last_err = e
            time.sleep(2)  # back off a bit before trying next model
        # Longer wait between full retry cycles
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Pollinations failed after {MAX_RETRIES} retries: {last_err}")


def fetch_scene_images(prompts: list[str], scratch_dir: Path) -> list[Path]:
    """One image per prompt. Falls back to a local-rendered card on API failure.

    Deterministic seeds so re-runs are stable.
    """
    from src.placeholder import generate_card

    scratch_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, prompt in enumerate(prompts):
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % (2**31)
        p = scratch_dir / f"scene_{i:02d}.jpg"
        print(f"  scene {i+1}/{len(prompts)}: ", end="", flush=True)
        try:
            fetch_image(prompt, p, seed=seed)
            print("Pollinations OK", flush=True)
        except Exception as e:
            print(f"Pollinations failed ({str(e)[:60]}) → local placeholder", flush=True)
            generate_card(i, p, seed=seed)
        paths.append(p)
        if i < len(prompts) - 1:
            time.sleep(BETWEEN_REQUESTS_SEC)
    return paths
