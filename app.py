"""Streamlit frontend for the video generator.

Run:   streamlit run app.py
"""
from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import asdict, replace
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.assemble import assemble_video
from src.script import FORMATS, Script, generate_script, load_script_file
from src.tts import synthesize_scenes
from src.visuals import fetch_scene_images_hybrid

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
SCRATCH_ROOT = ROOT / "scratch"
SAMPLES_DIR = ROOT / "samples"

VOICES = [
    "en-US-GuyNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "video"


def _render_pipeline(script: Script, out_name: str, log, image_slot, source: str = "web_first", topic: str = "") -> Path:
    """Run tts → images (with live thumbnails) → assemble."""
    t0 = time.time()
    slug = _slugify(out_name)
    scratch = SCRATCH_ROOT / slug
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    narrations = [s.narration for s in script.scenes]

    log(f"[1/3] Voiceover ({len(narrations)} scenes, voice={script.voice})")
    audio_paths = synthesize_scenes(narrations, scratch / "audio", voice=script.voice)
    log(f"      ✓ voiceover done ({time.time() - t0:.1f}s)")

    log(f"[2/3] Images (source={source}, aspect={script.aspect})")
    thumbs: list[tuple[Path, str]] = []

    def on_image(i: int, total: int, path: Path, src: str) -> None:
        thumbs.append((path, src))
        with image_slot.container():
            st.caption(f"Scenes rendered so far ({len(thumbs)}/{total})")
            cols = st.columns(min(total, 5))
            for idx, (p, s) in enumerate(thumbs):
                with cols[idx % len(cols)]:
                    st.image(str(p), caption=f"#{idx+1} · {s}", use_container_width=True)

    image_paths = fetch_scene_images_hybrid(
        script.scenes,
        scratch / "images",
        aspect=script.aspect,
        source=source,
        topic=topic,
        progress_cb=on_image,
    )
    log(f"      ✓ images done ({time.time() - t0:.1f}s)")

    log("[3/3] Assembling mp4 (MoviePy)")
    out_path = OUT_DIR / f"{slug}.mp4"
    assemble_video(image_paths, audio_paths, narrations, out_path, title=script.title, aspect=script.aspect)
    log(f"      ✓ mp4 ready ({time.time() - t0:.1f}s total)")
    return out_path


# --------- UI ---------

st.set_page_config(page_title="video-gen", page_icon="🎬", layout="wide")
st.title("🎬 video-gen")
st.caption("Topic in → mp4 out. Script by Groq, voice by edge-tts, visuals by Pollinations.ai, assembled by MoviePy.")

tab_topic, tab_sample = st.tabs(["🧠 From topic", "📂 From script file"])

# ================= TOPIC TAB =================
with tab_topic:
    left, right = st.columns([3, 2])

    with left:
        topic = st.text_area(
            "Topic",
            placeholder="e.g. did you know these wild fun facts about Green Lantern\n     the deep sea's strangest creatures\n     how CRISPR actually edits DNA",
            key="topic_input",
            height=90,
        )

    with right:
        format_key = st.selectbox(
            "Format",
            options=list(FORMATS.keys()),
            format_func=lambda k: FORMATS[k]["label"],
            index=0,
        )
        fmt = FORMATS[format_key]
        st.caption(f"**Aspect:** {fmt['aspect']}  ·  _{fmt['tone'][:80]}..._")

        scenes = st.slider(
            "Number of scenes",
            min_value=3, max_value=7,
            value=fmt["scenes_default"],
            help="Each scene is roughly 5–8 seconds, so total duration ≈ scenes × 6s.",
        )
        est_dur = scenes * 6 + 4  # +4 for title/outro cards
        st.caption(f"Estimated duration: **~{est_dur}s**")

        voice = st.selectbox("Voice", options=VOICES, index=1)
        source_label = st.selectbox(
            "Image source",
            options=["Web (Wikipedia Commons) → AI fallback", "AI (Pollinations) → Web fallback", "Web only", "AI only"],
            index=0,
            help="Web = real photos from Wikipedia Commons (no key, no rate-limit). AI = Pollinations.ai generated."
        )
        source_map = {
            "Web (Wikipedia Commons) → AI fallback": "web_first",
            "AI (Pollinations) → Web fallback": "ai_first",
            "Web only": "web_only",
            "AI only": "ai_only",
        }
        source = source_map[source_label]

    has_groq = bool(os.environ.get("GROQ_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not (has_groq or has_anthropic):
        st.warning("No LLM key configured. Set GROQ_API_KEY (free) in .env to use the topic tab.")

    col_write, col_cached = st.columns([1, 1])
    with col_write:
        write_btn = st.button(
            "📝 Write script",
            type="primary",
            disabled=not topic or not (has_groq or has_anthropic),
            use_container_width=True,
        )
    with col_cached:
        if "pending_script" in st.session_state:
            discard_btn = st.button("🗑 Discard draft", use_container_width=True)
            if discard_btn:
                st.session_state.pop("pending_script", None)
                st.rerun()

    if write_btn:
        with st.spinner("Asking Groq for a script..."):
            try:
                sc = generate_script(topic, format_key=format_key, scene_count=scenes)
                sc.voice = voice
                st.session_state["pending_script"] = sc
                st.session_state["pending_name"] = topic
            except Exception as e:
                st.error(f"Script generation failed: {e}")

    # Script preview + render button
    if "pending_script" in st.session_state:
        sc: Script = st.session_state["pending_script"]
        st.divider()
        st.subheader(f"📄 Draft script: {sc.title}")
        st.caption(f"{len(sc.scenes)} scenes · aspect: {sc.aspect} · voice: {sc.voice}")
        if sc.topic_context:
            st.markdown(f"**Visual style:** _{sc.topic_context}_")
        for i, scene in enumerate(sc.scenes, 1):
            with st.expander(f"Scene {i}", expanded=True):
                st.markdown(f"🗣️  {scene.narration}")
                st.caption(f"🖼  {scene.image_prompt}")

        render_btn = st.button("🎬 Render video from this script", type="primary", use_container_width=True)
        if render_btn:
            log_lines: list[str] = []
            log_box = st.empty()
            image_slot = st.empty()

            def log(msg: str) -> None:
                log_lines.append(msg)
                log_box.code("\n".join(log_lines))

            try:
                out_path = _render_pipeline(sc, st.session_state.get("pending_name", sc.title), log, image_slot, source=source, topic=st.session_state.get("pending_name", ""))
                st.success(f"Generated: {out_path.name}")
                st.video(str(out_path))
                with open(out_path, "rb") as f:
                    st.download_button("⬇ Download mp4", data=f, file_name=out_path.name, mime="video/mp4")
                st.session_state.pop("pending_script", None)
                st.session_state.pop("pending_name", None)
            except Exception as e:
                st.error(f"Render failed: {e}")

# ================= SAMPLE TAB =================
with tab_sample:
    sample_files = sorted(SAMPLES_DIR.glob("*.json"))
    if not sample_files:
        st.info("No sample scripts in samples/.")
    else:
        choice = st.selectbox("Pick a prebuilt script", options=[p.name for p in sample_files])
        if st.button("🎬 Render from sample", type="primary"):
            log_lines: list[str] = []
            log_box = st.empty()
            image_slot = st.empty()

            def log(msg: str) -> None:
                log_lines.append(msg)
                log_box.code("\n".join(log_lines))

            try:
                script = load_script_file(SAMPLES_DIR / choice)
                log(f"Loaded: {script.title!r} ({len(script.scenes)} scenes, aspect={script.aspect})")
                out_path = _render_pipeline(script, Path(choice).stem, log, image_slot)
                st.success(f"Generated: {out_path.name}")
                st.video(str(out_path))
                with open(out_path, "rb") as f:
                    st.download_button("⬇ Download mp4", data=f, file_name=out_path.name, mime="video/mp4")
            except Exception as e:
                st.error(f"Render failed: {e}")

st.divider()
st.caption(
    "edge-tts (free) · Pollinations.ai (free tier) · "
    "Groq free tier for script · ffmpeg + MoviePy for assembly"
)
