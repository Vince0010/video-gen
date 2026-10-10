"""Pollinations.ai image fetch: prompt -> jpg. No API key required."""
from __future__ import annotations

import hashlib
import urllib.parse
from pathlib import Path

import requests

BASE = "https://image.pollinations.ai/prompt"
WIDTH = 1280
HEIGHT = 720
MODEL = "flux"  # fast + decent quality


def fetch_image(prompt: str, out_path: Path, seed: int | None = None) -> Path:
    """Fetch one image. Pollinations encodes the prompt in the URL path."""
    encoded = urllib.parse.quote(prompt, safe="")
    params = {"width": WIDTH, "height": HEIGHT, "nologo": "true", "model": MODEL}
    if seed is not None:
        params["seed"] = seed
    url = f"{BASE}/{encoded}"
    r = requests.get(url, params=params, timeout=90)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return out_path


def fetch_scene_images(prompts: list[str], scratch_dir: Path) -> list[Path]:
    """One image per prompt. Deterministic seed per prompt so re-runs are stable."""
    paths: list[Path] = []
    for i, prompt in enumerate(prompts):
        seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % (2**31)
        p = scratch_dir / f"scene_{i:02d}.jpg"
        fetch_image(prompt, p, seed=seed)
        paths.append(p)
    return paths
