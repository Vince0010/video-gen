"""Streamlit frontend for the video generator.

Run:   streamlit run app.py
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.assemble import assemble_video
from src.script import Script, generate_script, load_script_file
from src.tts import synthesize_scenes
from src.visuals import fetch_scene_images

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "out"
SCRATCH_ROOT = ROOT / "scratch"
SAMPLES_DIR = ROOT / "samples"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "video"


def _run_pipeline(script: Script, out_name: str, log) -> Path:
    t0 = time.time()
    slug = _slugify(out_name)
    scratch = SCRATCH_ROOT / slug
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    narrations = [s.narration for s in script.scenes]
    image_prompts = [s.image_prompt for s in script.scenes]

    log(f"[1/3] Voiceover — {len(narrations)} scenes (voice: {script.voice or 'default'})")
    audio_paths = synthesize_scenes(narrations, scratch / "audio", voice=script.voice)

    log("[2/3] Images (Pollinations.ai) — this takes the longest")
    image_paths = fetch_scene_images(image_prompts, scratch / "images")

    log("[3/3] Assembling mp4")
    out_path = OUT_DIR / f"{slug}.mp4"
    assemble_video(image_paths, audio_paths, narrations, out_path, title=script.title)

    log(f"Done in {time.time() - t0:.1f}s")
    return out_path


# --------- UI ---------

st.set_page_config(page_title="video-gen", page_icon="🎬", layout="centered")
st.title("🎬 video-gen")
st.caption("Topic in → mp4 out. Script by Groq Llama, voice by edge-tts, visuals by Pollinations.ai, assembled by MoviePy.")

tab_topic, tab_sample = st.tabs(["🧠 From topic", "📂 From script file"])

with tab_topic:
    topic = st.text_input(
        "Topic",
        placeholder="why octopuses are smart, how neural networks learn, the history of coffee…",
        key="topic_input",
    )
    col1, col2 = st.columns(2)
    with col1:
        voice = st.selectbox(
            "Voice",
            options=[
                "en-US-GuyNeural",
                "en-US-AndrewMultilingualNeural",
                "en-US-AriaNeural",
                "en-US-JennyNeural",
                "en-GB-RyanNeural",
                "en-GB-SoniaNeural",
            ],
            index=1,
        )
    with col2:
        has_groq = bool(os.environ.get("GROQ_API_KEY"))
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        provider = "Groq (Llama 3.3 70B)" if has_groq else ("Anthropic (Claude)" if has_anthropic else "— NONE —")
        st.text_input("LLM provider", value=provider, disabled=True)
        if not (has_groq or has_anthropic):
            st.warning("No LLM key configured. Set GROQ_API_KEY in .env (free) or ANTHROPIC_API_KEY.")

    gen_topic = st.button("Generate from topic", type="primary", disabled=not topic or not (has_groq or has_anthropic))

    if gen_topic:
        log_lines: list[str] = []
        log_box = st.empty()

        def log(msg: str) -> None:
            log_lines.append(msg)
            log_box.code("\n".join(log_lines))

        try:
            log(f"Writing script with {provider}…")
            script = generate_script(topic)
            if voice:
                script.voice = voice
            log(f"  title: {script.title!r}")
            log(f"  {len(script.scenes)} scenes")
            for i, s in enumerate(script.scenes, 1):
                log(f"    [{i}] {s.narration}")
            out_path = _run_pipeline(script, topic, log)
            st.success(f"Generated: {out_path.name}")
            st.video(str(out_path))
            with open(out_path, "rb") as f:
                st.download_button("Download mp4", data=f, file_name=out_path.name, mime="video/mp4")
        except Exception as e:
            st.error(f"Failed: {e}")

with tab_sample:
    sample_files = sorted(SAMPLES_DIR.glob("*.json"))
    if not sample_files:
        st.info("No sample scripts in samples/.")
    else:
        choice = st.selectbox("Pick a script", options=[p.name for p in sample_files])
        gen_sample = st.button("Generate from sample", type="primary")
        if gen_sample:
            log_lines: list[str] = []
            log_box = st.empty()

            def log(msg: str) -> None:
                log_lines.append(msg)
                log_box.code("\n".join(log_lines))

            try:
                script = load_script_file(SAMPLES_DIR / choice)
                log(f"Loaded: {script.title!r} ({len(script.scenes)} scenes)")
                out_path = _run_pipeline(script, Path(choice).stem, log)
                st.success(f"Generated: {out_path.name}")
                st.video(str(out_path))
                with open(out_path, "rb") as f:
                    st.download_button("Download mp4", data=f, file_name=out_path.name, mime="video/mp4")
            except Exception as e:
                st.error(f"Failed: {e}")

st.divider()
st.caption(
    "edge-tts (free, no key) · Pollinations.ai (free, no key for small images) · "
    "Groq free tier for script · ffmpeg + MoviePy for assembly"
)
