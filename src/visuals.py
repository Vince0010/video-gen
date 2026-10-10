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
# Free-tier Pollinations only serves specific aspect buckets reliably.
LANDSCAPE = (1152, 648)
PORTRAIT = (648, 1152)
MODELS = ["flux", "turbo"]
BETWEEN_REQUESTS_SEC = 4
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


def fetch_image(prompt: str, out_path: Path, seed: int | None = None, size: tuple[int, int] = LANDSCAPE) -> Path:
    w, h = size
    encoded = urllib.parse.quote(prompt, safe="")
    url = f"{BASE}/{encoded}"
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        for model in MODELS:
            params = {"width": w, "height": h, "nologo": "true", "model": model}
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
            time.sleep(2)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Pollinations failed after {MAX_RETRIES} retries: {last_err}")


def fetch_scene_images_hybrid(
    scenes: list,                 # list of Scene objects (narration, image_prompt, search)
    scratch_dir: Path,
    aspect: str = "landscape",
    source: str = "web_first",    # "web_first" | "ai_first" | "web_only" | "ai_only"
    topic: str = "",
    progress_cb=None,
) -> list[Path]:
    """Fetch one image per scene using a configurable source order.

    source:
      web_first — Commons → Pollinations → placeholder
      ai_first  — Pollinations → Commons → placeholder
      web_only  — Commons → placeholder
      ai_only   — Pollinations → placeholder
    """
    from src.placeholder import generate_card
    from src.web_images import find_image as commons_find

    size = PORTRAIT if aspect == "portrait" else LANDSCAPE
    scratch_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    def _commons(scene, p) -> bool:
        q = (scene.search or "").strip() or scene.image_prompt
        if topic and topic.lower() not in q.lower():
            q = f"{topic} {q}"
        return commons_find(q, p, size)

    def _ai(scene, p) -> bool:
        seed = int(hashlib.md5(scene.image_prompt.encode()).hexdigest()[:8], 16) % (2**31)
        try:
            fetch_image(scene.image_prompt, p, seed=seed, size=size)
            return True
        except Exception:
            return False

    for i, scene in enumerate(scenes):
        p = scratch_dir / f"scene_{i:02d}.jpg"
        print(f"  scene {i+1}/{len(scenes)}: ", end="", flush=True)
        used = "placeholder"

        order = {
            "web_first": [("commons", _commons), ("pollinations", _ai)],
            "ai_first":  [("pollinations", _ai), ("commons", _commons)],
            "web_only":  [("commons", _commons)],
            "ai_only":   [("pollinations", _ai)],
        }[source]

        for name, fn in order:
            if fn(scene, p):
                used = name
                print(f"{name} OK")
                break
        else:
            seed = int(hashlib.md5(scene.image_prompt.encode()).hexdigest()[:8], 16) % (2**31)
            generate_card(i, p, seed=seed, size=size)
            print("all sources failed → placeholder")

        paths.append(p)
        if progress_cb:
            try:
                progress_cb(i, len(scenes), p, used)
            except Exception:
                pass
        if i < len(scenes) - 1 and used == "pollinations":
            time.sleep(BETWEEN_REQUESTS_SEC)
    return paths


def fetch_scene_images(
    prompts: list[str],
    scratch_dir: Path,
    aspect: str = "landscape",
    progress_cb=None,
) -> list[Path]:
    """One image per prompt. Falls back to a local-rendered card on API failure.

    aspect: "landscape" (1152x648) or "portrait" (648x1152).
    progress_cb: optional (idx, total, path, source) -> None, called after each image
                 so the UI can show thumbnails live. `source` is "pollinations" or "placeholder".
    """
    from src.placeholder import generate_card

    size = PORTRAIT if aspect == "portrait" else LANDSCAPE
    scratch_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, prompt in enumerate(prompts):
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % (2**31)
        p = scratch_dir / f"scene_{i:02d}.jpg"
        print(f"  scene {i+1}/{len(prompts)}: ", end="", flush=True)
        source = "pollinations"
        try:
            fetch_image(prompt, p, seed=seed, size=size)
            print("Pollinations OK", flush=True)
        except Exception as e:
            print(f"Pollinations failed ({str(e)[:60]}) → local placeholder", flush=True)
            generate_card(i, p, seed=seed, size=size)
            source = "placeholder"
        paths.append(p)
        if progress_cb:
            try:
                progress_cb(i, len(prompts), p, source)
            except Exception:
                pass
        if i < len(prompts) - 1:
            time.sleep(BETWEEN_REQUESTS_SEC)
    return paths
