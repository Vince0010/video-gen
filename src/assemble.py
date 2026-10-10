"""Compose scenes into a single mp4 using MoviePy.

Each scene = image background + voiceover audio + burned-in caption.
Scenes are concatenated. No music / fades yet — that's Phase 3+.
"""
from __future__ import annotations

from pathlib import Path

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)

W, H = 1280, 720
FPS = 24
CAPTION_FONTSIZE = 42
CAPTION_MARGIN = 60  # from bottom


def _wrap_caption(text: str, max_chars: int = 55) -> str:
    """Soft wrap narration so the caption doesn't overflow."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def build_scene_clip(image_path: Path, audio_path: Path, caption_text: str):
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration + 0.4  # tiny tail pad so caption doesn't cut mid-word

    bg = ImageClip(str(image_path)).set_duration(duration).resize((W, H))

    caption = (
        TextClip(
            _wrap_caption(caption_text),
            fontsize=CAPTION_FONTSIZE,
            color="white",
            font="Arial-Bold",
            method="caption",
            size=(W - 120, None),
            align="center",
            stroke_color="black",
            stroke_width=2,
        )
        .set_duration(duration)
        .set_position(("center", H - CAPTION_MARGIN - 120))
    )

    composite = CompositeVideoClip([bg, caption], size=(W, H)).set_audio(audio).set_duration(duration)
    return composite


def assemble_video(
    image_paths: list[Path],
    audio_paths: list[Path],
    narrations: list[str],
    out_path: Path,
) -> Path:
    assert len(image_paths) == len(audio_paths) == len(narrations), "scene lengths must match"
    clips = [
        build_scene_clip(img, aud, text)
        for img, aud, text in zip(image_paths, audio_paths, narrations)
    ]
    final = concatenate_videoclips(clips, method="compose")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )
    return out_path
