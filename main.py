"""Automated video generator.

Usage:
    python main.py "your topic here"
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.assemble import assemble_video
from src.script import generate_script
from src.tts import synthesize_scenes
from src.visuals import fetch_scene_images

load_dotenv()

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
SCRATCH_ROOT = ROOT / "scratch"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "video"


def main(topic: str) -> Path:
    t0 = time.time()
    slug = _slugify(topic)
    scratch = SCRATCH_ROOT / slug
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    print(f"[1/4] Writing script with Claude for: {topic!r}")
    script = generate_script(topic)
    print(f"      title: {script.title}  ({len(script.scenes)} scenes)")

    narrations = [s.narration for s in script.scenes]
    image_prompts = [s.image_prompt for s in script.scenes]

    print("[2/4] Synthesizing voiceover (edge-tts)")
    audio_paths = synthesize_scenes(narrations, scratch / "audio")

    print("[3/4] Fetching images (Pollinations.ai)")
    image_paths = fetch_scene_images(image_prompts, scratch / "images")

    print("[4/4] Assembling mp4 (MoviePy)")
    out_path = OUT_DIR / f"{slug}.mp4"
    assemble_video(image_paths, audio_paths, narrations, out_path)

    dt = time.time() - t0
    print(f"\nDone in {dt:.1f}s -> {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py \"your topic here\"", file=sys.stderr)
        sys.exit(2)
    main(" ".join(sys.argv[1:]))
