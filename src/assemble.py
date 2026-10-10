"""Compose scenes into a single mp4 using MoviePy.

Each scene = image background + voiceover audio + burned-in caption.
Scenes are concatenated. No music / fades yet — that's Phase 3+.
"""
from __future__ import annotations

from pathlib import Path

# MoviePy 1.0.3 references Image.ANTIALIAS which was removed in Pillow 10.
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):
    _PILImage.ANTIALIAS = _PILImage.LANCZOS

# Point MoviePy at ImageMagick (installed via homebrew)
import os as _os
import shutil as _shutil
_magick = _shutil.which("magick") or _shutil.which("convert") or "/opt/homebrew/bin/convert"
_os.environ["IMAGEMAGICK_BINARY"] = _magick
from moviepy.config import change_settings as _change_settings
_change_settings({"IMAGEMAGICK_BINARY": _magick})

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)

W, H = 1152, 648
FPS = 24
CAPTION_FONTSIZE = 42
CAPTION_MARGIN = 60  # from bottom
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


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
    duration = audio.duration

    bg = ImageClip(str(image_path)).set_duration(duration).resize((W, H))

    caption = (
        TextClip(
            _wrap_caption(caption_text),
            fontsize=CAPTION_FONTSIZE,
            color="white",
            font=FONT_PATH,
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
