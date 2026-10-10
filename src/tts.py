"""Edge-TTS voiceover: narration text -> mp3 files per scene."""
from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

VOICE = "en-US-GuyNeural"  # natural male narrator; swap for en-US-AriaNeural for female


async def _synth(text: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate="+0%", pitch="+0Hz")
    await communicate.save(str(out_path))


def synthesize_scenes(narrations: list[str], scratch_dir: Path) -> list[Path]:
    """Write one mp3 per narration. Returns list of file paths (same order)."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    async def run_all():
        for i, text in enumerate(narrations):
            p = scratch_dir / f"scene_{i:02d}.mp3"
            await _synth(text, p)
            paths.append(p)

    asyncio.run(run_all())
    return paths
