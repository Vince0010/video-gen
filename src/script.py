"""Claude generates a scene-by-scene script for a given topic."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic


@dataclass
class Scene:
    narration: str
    image_prompt: str


@dataclass
class Script:
    title: str
    scenes: list[Scene]


SYSTEM = """You write short-form educational explainer scripts for 30–60 second videos.

Return STRICT JSON matching this schema and nothing else:
{
  "title": "<3–6 word punchy title>",
  "scenes": [
    {
      "narration": "<1–2 sentence line to be spoken aloud, ~12–25 words>",
      "image_prompt": "<concrete visual description for an AI image generator — cinematic, specific nouns, lighting, composition. 15–30 words. No text in image.>"
    }
  ]
}

Rules:
- 5 scenes exactly.
- Narration should flow as one continuous explainer when scenes are played in order.
- Image prompts must be visually concrete (nouns + setting + mood), not abstract.
- No markdown, no code fences, no commentary — just the JSON object.
"""


def generate_script(topic: str) -> Script:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    raw = msg.content[0].text.strip()
    # Strip accidental fences just in case
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    data = json.loads(raw)
    scenes = [Scene(narration=s["narration"], image_prompt=s["image_prompt"]) for s in data["scenes"]]
    return Script(title=data["title"], scenes=scenes)
