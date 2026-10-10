"""Automated video generator.

Two usage modes:
  python main.py "<topic>"                 # LLM writes the script (needs Anthropic credit)
  python main.py --script samples/foo.json # Use a prebuilt JSON script (no LLM)
"""
from __future__ import annotations

import argparse
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

from src.assemble import assemble_video
from src.script import Script, generate_script, load_script_file
from src.tts import synthesize_scenes
from src.visuals import fetch_scene_images

load_dotenv()

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
SCRATCH_ROOT = ROOT / "scratch"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "video"


def run(script: Script, out_name: str) -> Path:
    t0 = time.time()
    slug = _slugify(out_name)
    scratch = SCRATCH_ROOT / slug
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    narrations = [s.narration for s in script.scenes]
    image_prompts = [s.image_prompt for s in script.scenes]

    print(f"[1/3] Voiceover (edge-tts, voice={script.voice or 'default'}) — {len(narrations)} scenes")
    audio_paths = synthesize_scenes(narrations, scratch / "audio", voice=script.voice)

    print(f"[2/3] Images (Pollinations.ai)")
    image_paths = fetch_scene_images(image_prompts, scratch / "images")

    print(f"[3/3] Assembling mp4")
    out_path = OUT_DIR / f"{slug}.mp4"
    assemble_video(image_paths, audio_paths, narrations, out_path)

    print(f"\nDone in {time.time() - t0:.1f}s -> {out_path}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Automated video generator")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("topic", nargs="?", help='Topic to generate (needs Anthropic credit): "why octopuses are smart"')
    g.add_argument("--script", type=Path, help="Path to a prebuilt script JSON (bypasses LLM)")
    args = ap.parse_args()

    if args.script:
        script = load_script_file(args.script)
        name = args.script.stem
        print(f'Loaded script: {script.title!r} ({len(script.scenes)} scenes) from {args.script}')
    else:
        print(f'Generating script for topic: {args.topic!r}')
        script = generate_script(args.topic)
        name = args.topic
        print(f'  title: {script.title!r}')

    run(script, name)


if __name__ == "__main__":
    main()
