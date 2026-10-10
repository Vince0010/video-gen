"""Compose scenes into a single mp4 using MoviePy.

Pipeline per scene:
  image (Ken Burns zoom) + voiceover + burned caption on lower-third
Scene chain:
  title card → crossfaded scenes → outro card
Audio:
  per-scene voiceover (full volume) mixed with a looped ambient bed (ducked)
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

from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.audio.fx.audio_loop import audio_loop
from moviepy.audio.fx.volumex import volumex
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)

W, H = 1152, 648
FPS = 24
CAPTION_FONTSIZE = 44
CAPTION_BOTTOM_PAD = 50
LOWER_THIRD_HEIGHT = 180
CROSSFADE = 0.5
TITLE_DURATION = 2.2
OUTRO_DURATION = 2.2
MUSIC_VOLUME = 0.14
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

ROOT = Path(__file__).resolve().parent.parent
MUSIC_PATH = ROOT / "assets" / "music" / "ambient.mp3"


def _wrap_caption(text: str, max_chars: int = 55) -> str:
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


def _title_card(text: str, duration: float, subtitle: str | None = None):
    bg = ColorClip(size=(W, H), color=(5, 10, 8)).set_duration(duration)
    title = (
        TextClip(
            text.upper(),
            fontsize=96,
            color="#2fff8c",
            font=FONT_PATH,
            method="label",
            stroke_color="black",
            stroke_width=1,
        )
        .set_duration(duration)
        .set_position(("center", "center"))
    )
    layers = [bg, title]
    if subtitle:
        sub = (
            TextClip(
                subtitle,
                fontsize=28,
                color="white",
                font=FONT_PATH,
                method="label",
            )
            .set_duration(duration)
            .set_position(("center", H // 2 + 70))
        )
        layers.append(sub)
    clip = CompositeVideoClip(layers, size=(W, H)).set_duration(duration)
    return clip.crossfadein(0.4).crossfadeout(0.4)


def build_scene_clip(image_path: Path, audio_path: Path, caption_text: str, scene_idx: int):
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration

    # Ken Burns: alternate scenes zoom in / zoom out slightly to add life.
    zoom_in = scene_idx % 2 == 0
    base = ImageClip(str(image_path)).set_duration(duration)
    base = base.resize((int(W * 1.15), int(H * 1.15)))  # oversize so we can zoom without edges

    if zoom_in:
        base = base.resize(lambda t: 1.0 + 0.04 * t / max(duration, 0.1))
    else:
        base = base.resize(lambda t: 1.04 - 0.04 * t / max(duration, 0.1))
    base = base.set_position(("center", "center"))

    lower = (
        ColorClip(size=(W, LOWER_THIRD_HEIGHT), color=(0, 0, 0))
        .set_opacity(0.55)
        .set_duration(duration)
        .set_position((0, H - LOWER_THIRD_HEIGHT))
    )

    caption = (
        TextClip(
            _wrap_caption(caption_text),
            fontsize=CAPTION_FONTSIZE,
            color="white",
            font=FONT_PATH,
            method="caption",
            size=(W - 160, None),
            align="center",
            stroke_color="black",
            stroke_width=1,
        )
        .set_duration(duration)
    )
    caption = caption.set_position(("center", H - CAPTION_BOTTOM_PAD - caption.h))

    return (
        CompositeVideoClip([base, lower, caption], size=(W, H))
        .set_audio(audio)
        .set_duration(duration)
    )


def assemble_video(
    image_paths: list[Path],
    audio_paths: list[Path],
    narrations: list[str],
    out_path: Path,
    title: str = "",
) -> Path:
    assert len(image_paths) == len(audio_paths) == len(narrations), "scene lengths must match"

    scene_clips = []
    for i, (img, aud, text) in enumerate(zip(image_paths, audio_paths, narrations)):
        c = build_scene_clip(img, aud, text, scene_idx=i)
        if i > 0:
            c = c.crossfadein(CROSSFADE)
        scene_clips.append(c)

    clips = []
    if title:
        clips.append(_title_card(title, TITLE_DURATION))
    clips.extend(scene_clips)
    clips.append(_title_card(title or "", OUTRO_DURATION, subtitle="— fin —"))

    final = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE)

    # Background ambient bed mixed under narration (ducked).
    if MUSIC_PATH.exists():
        music = (
            AudioFileClip(str(MUSIC_PATH))
            .fx(audio_loop, duration=final.duration)
            .fx(volumex, MUSIC_VOLUME)
        )
        original_audio = final.audio  # the per-scene voiceover already attached
        if original_audio is not None:
            final = final.set_audio(CompositeAudioClip([original_audio, music]))
        else:
            final = final.set_audio(music)

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
