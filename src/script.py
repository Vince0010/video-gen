"""Script source: either a bundled JSON sample or (future) an LLM call.

For the prototype we support two modes:
  - load_script_file(path)  -> load a hand-authored JSON script
  - generate_script(topic)  -> Anthropic Claude writes it (requires credits)

The LLM path is kept so the pipeline is topic-agnostic once billing is set up,
but the sample path lets us demo the renderer immediately.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Scene:
    narration: str
    image_prompt: str


@dataclass
class Script:
    title: str
    scenes: list[Scene]
    voice: str | None = None            # optional override: an edge-tts voice id
    topic_context: str | None = None    # style/subject hint prepended to every image prompt


def load_script_file(path: Path) -> Script:
    data = json.loads(Path(path).read_text())
    ctx = data.get("topic_context")
    scenes = []
    for s in data["scenes"]:
        prompt = s["image_prompt"]
        if ctx:
            prompt = f"{ctx}. {prompt}"
        scenes.append(Scene(narration=s["narration"], image_prompt=prompt))
    return Script(title=data["title"], scenes=scenes, voice=data.get("voice"), topic_context=ctx)


# ---------- LLM path ----------

SYSTEM = """You write cinematic short-form video scripts for 30-60 second videos.

Return STRICT JSON ONLY matching:
{
  "title": "<2-5 word title, no punctuation>",
  "topic_context": "<style/subject hint prepended to every image_prompt — 10-20 words. Should set an overall look (e.g. 'cinematic film still, 35mm, dark fantasy sci-fi' or 'bright nature documentary, golden hour, 4K cinematography')>",
  "scenes": [
    {
      "narration": "<1-2 sentences spoken by narrator, 12-25 words, flows into the next scene>",
      "image_prompt": "<concrete visual: nouns + setting + mood, 15-30 words, no text, no brand names>"
    }
  ]
}

Rules:
- Exactly 5 scenes
- Narration must sound like a human script, not an ad; no "subscribe", no CTAs
- Image prompts must be concrete (nouns + setting + lighting + mood)
- No markdown, no code fences, no commentary — JSON only
"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def _build_script(data: dict) -> Script:
    ctx = data.get("topic_context")
    scenes = []
    for s in data["scenes"]:
        prompt = s["image_prompt"]
        if ctx:
            prompt = f"{ctx}. {prompt}"
        scenes.append(Scene(narration=s["narration"], image_prompt=prompt))
    return Script(title=data["title"], scenes=scenes, voice=data.get("voice"), topic_context=ctx)


def generate_script_groq(topic: str) -> Script:
    """Primary LLM path — free, no billing. Needs GROQ_API_KEY."""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    # Try models in order of preference; different Groq tiers expose different sets.
    models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    last_err = None
    resp = None
    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.9,
                max_tokens=1500,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Topic: {topic}"},
                ],
            )
            break
        except Exception as e:
            last_err = e
    if resp is None:
        raise RuntimeError(f"All Groq models failed: {last_err}")
    return _build_script(_parse_json(resp.choices[0].message.content))


def generate_script_anthropic(topic: str) -> Script:
    """Fallback LLM path — higher quality but needs paid credit."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    return _build_script(_parse_json(msg.content[0].text))


def generate_script(topic: str) -> Script:
    """Try Groq first (free), fall back to Anthropic if configured."""
    if os.environ.get("GROQ_API_KEY"):
        return generate_script_groq(topic)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return generate_script_anthropic(topic)
    raise RuntimeError("No LLM configured. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY in .env.")
