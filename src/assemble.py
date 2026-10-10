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

LANDSCAPE = (1152, 648)
PORTRAIT = (648, 1152)
FPS = 24
CAPTION_BOTTOM_PAD = 50
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


def _title_card(text: str, duration: float, size: tuple[int, int], subtitle: str | None = None):
    """Title/outro card. Title font is scaled DOWN until the text fits within 92% of width."""
    W, H = size
    bg = ColorClip(size=(W, H), color=(5, 10, 8)).set_duration(duration)

    # Use PIL to measure and auto-fit the title width
    from PIL import ImageFont
    text_up = text.upper()
    max_px = int(W * 0.92)
    fontsize = int(min(W, H) * 0.16)  # start big
    font = ImageFont.truetype(FONT_PATH, fontsize)
    while fontsize > 24:
        bbox = font.getbbox(text_up)
        if (bbox[2] - bbox[0]) <= max_px:
            break
        fontsize -= 4
        font = ImageFont.truetype(FONT_PATH, fontsize)
    sub_font = max(22, int(fontsize * 0.4))

    title = (
        TextClip(
            text_up,
            fontsize=fontsize,
            color="#2fff8c",
            font=FONT_PATH,
            method="label",
        )
        .set_duration(duration)
    )
    title = title.set_position(("center", (H - title.h) // 2))
    layers = [bg, title]
    if subtitle:
        sub = (
            TextClip(
                subtitle,
                fontsize=sub_font,
                color="white",
                font=FONT_PATH,
                method="label",
            )
            .set_duration(duration)
        )
        sub = sub.set_position(("center", (H + title.h) // 2 + 20))
        layers.append(sub)
    clip = CompositeVideoClip(layers, size=(W, H)).set_duration(duration)
    return clip.crossfadein(0.4).crossfadeout(0.4)


def build_scene_clip(image_path: Path, audio_path: Path, caption_text: str, scene_idx: int, size: tuple[int, int], caption_dir: Path | None = None):
    W, H = size
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration

    is_portrait = H > W
    caption_fontsize = int(min(W, H) * 0.072) if is_portrait else 42

    # Ken Burns zoom
    zoom_in = scene_idx % 2 == 0
    base = ImageClip(str(image_path)).set_duration(duration)
    base = base.resize((int(W * 1.15), int(H * 1.15)))
    if zoom_in:
        base = base.resize(lambda t: 1.0 + 0.04 * t / max(duration, 0.1))
    else:
        base = base.resize(lambda t: 1.04 - 0.04 * t / max(duration, 0.1))
    base = base.set_position(("center", "center"))

    # PIL-rendered caption (much cleaner than TextClip + ImageMagick stroke)
    from src.captions import render_caption_to_file
    if caption_dir is None:
        caption_dir = Path("scratch/_captions")
    caption_png = caption_dir / f"cap_{scene_idx:02d}.png"
    render_caption_to_file(
        caption_text,
        caption_png,
        canvas_w=W,
        canvas_h=H,
        fontsize=caption_fontsize,
    )
    caption = ImageClip(str(caption_png)).set_duration(duration).set_position((0, 0))

    return (
        CompositeVideoClip([base, caption], size=(W, H))
        .set_audio(audio)
        .set_duration(duration)
    )


def assemble_video(
    image_paths: list[Path],
    audio_paths: list[Path],
    narrations: list[str],
    out_path: Path,
    title: str = "",
    aspect: str = "landscape",
) -> Path:
    assert len(image_paths) == len(audio_paths) == len(narrations), "scene lengths must match"
    size = PORTRAIT if aspect == "portrait" else LANDSCAPE
    caption_dir = out_path.parent.parent / "scratch" / "_captions" / out_path.stem
    caption_dir.mkdir(parents=True, exist_ok=True)

    scene_clips = []
    for i, (img, aud, text) in enumerate(zip(image_paths, audio_paths, narrations)):
        c = build_scene_clip(img, aud, text, scene_idx=i, size=size, caption_dir=caption_dir)
        if i > 0:
            c = c.crossfadein(CROSSFADE)
        scene_clips.append(c)

    clips = []
    if title:
        clips.append(_title_card(title, TITLE_DURATION, size=size))
    clips.extend(scene_clips)
    clips.append(_title_card(title or "", OUTRO_DURATION, size=size, subtitle="— fin —"))

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
