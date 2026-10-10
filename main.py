"""Automated video generator.

Usage:
    python main.py "<topic>"                       # LLM writes the script
    python main.py "<topic>" --format youtube_short --scenes 4
    python main.py --script samples/foo.json       # bypass LLM
"""
from __future__ import annotations

import argparse
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

from src.assemble import assemble_video
from src.script import FORMATS, Script, generate_script, load_script_file
from src.tts import synthesize_scenes
from src.visuals import fetch_scene_images_hybrid

load_dotenv()

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
SCRATCH_ROOT = ROOT / "scratch"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "video"


def run(script: Script, out_name: str, source: str = "web_first", topic: str = "") -> Path:
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

    print(f"[2/3] Images (source={source}, aspect={script.aspect})")
    image_paths = fetch_scene_images_hybrid(
        script.scenes,
        scratch / "images",
        aspect=script.aspect,
        source=source,
        topic=topic,
    )

    print("[3/3] Assembling mp4")
    out_path = OUT_DIR / f"{slug}.mp4"
    assemble_video(image_paths, audio_paths, narrations, out_path, title=script.title, aspect=script.aspect)

    print(f"\nDone in {time.time() - t0:.1f}s -> {out_path}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Automated video generator")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("topic", nargs="?", help='Topic for the video (needs GROQ_API_KEY): "why octopuses are smart"')
    g.add_argument("--script", type=Path, help="Path to a prebuilt script JSON (bypasses LLM)")
    ap.add_argument("--format", default="explainer", choices=list(FORMATS.keys()),
                    help=f'Format preset: {", ".join(FORMATS.keys())}')
    ap.add_argument("--scenes", type=int, default=None, help="Number of scenes (default: format-specific)")
    ap.add_argument("--source", default="web_first",
                    choices=["web_first", "ai_first", "web_only", "ai_only"],
                    help="Image source order: web=Wikipedia Commons, ai=Pollinations")
    args = ap.parse_args()

    if args.script:
        script = load_script_file(args.script)
        name = args.script.stem
        print(f'Loaded script: {script.title!r} ({len(script.scenes)} scenes, aspect={script.aspect})')
    else:
        print(f'Generating script for topic: {args.topic!r} (format={args.format}, scenes={args.scenes or "default"})')
        script = generate_script(args.topic, format_key=args.format, scene_count=args.scenes)
        name = args.topic
        print(f'  title: {script.title!r}')
        print(f'  aspect: {script.aspect}')

    run(script, name, source=args.source, topic=args.topic or "")


if __name__ == "__main__":
    main()
