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
    voice: str | None = None  # optional override: an edge-tts voice id


def load_script_file(path: Path) -> Script:
    data = json.loads(Path(path).read_text())
    scenes = [Scene(narration=s["narration"], image_prompt=s["image_prompt"]) for s in data["scenes"]]
    return Script(title=data["title"], scenes=scenes, voice=data.get("voice"))


# ---------- LLM path (requires ANTHROPIC_API_KEY with credit) ----------

SYSTEM = """You write short-form educational explainer scripts for 30–60 second videos.

Return STRICT JSON ONLY matching:
{
  "title": "<3–6 word punchy title>",
  "scenes": [
    {
      "narration": "<1–2 sentences, 12–25 words, spoken aloud>",
      "image_prompt": "<concrete visual: nouns + setting + mood, 15–30 words, no text in image>"
    }
  ]
}

Rules: exactly 5 scenes. Narration flows as a single explainer. No markdown, no fences, no commentary.
"""


def generate_script(topic: str) -> Script:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    data = json.loads(raw)
    scenes = [Scene(narration=s["narration"], image_prompt=s["image_prompt"]) for s in data["scenes"]]
    return Script(title=data["title"], scenes=scenes)
