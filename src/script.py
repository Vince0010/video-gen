"""Script generation: either load a bundled JSON sample or ask an LLM."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Scene:
    narration: str
    image_prompt: str
    search: str = ""   # short keyword phrase for web image search (Wikipedia Commons, etc.)


@dataclass
class Script:
    title: str
    scenes: list[Scene]
    voice: str | None = None
    topic_context: str | None = None
    aspect: str = "landscape"  # "landscape" or "portrait"


# ---------- Format presets ----------

FORMATS: dict[str, dict] = {
    "explainer": {
        "label": "Explainer (16:9)",
        "aspect": "landscape",
        "scenes_default": 5,
        "tone": (
            "A short-form educational explainer. Narration flows as a single, continuous "
            "explanation; each scene builds on the previous one. No CTAs, no 'subscribe'. "
            "Serious but approachable."
        ),
    },
    "youtube_short": {
        "label": "YouTube Short (9:16)",
        "aspect": "portrait",
        "scenes_default": 4,
        "tone": (
            "A high-energy vertical social video. Short punchy lines (8-15 words). "
            "Scroll-stopping hook in scene 1. Each line is standalone — no 'as I was saying'. "
            "No CTAs."
        ),
    },
    "did_you_know": {
        "label": "Did You Know (fun facts)",
        "aspect": "landscape",
        "scenes_default": 5,
        "tone": (
            "A 'did you know' / fun-facts listicle. Scene 1 opens with 'Did you know...' or a "
            "similar hook. Each subsequent scene presents ONE surprising fact in 1-2 sentences. "
            "Facts must be concrete and specific, not vague."
        ),
    },
    "cinematic_teaser": {
        "label": "Cinematic Teaser (16:9)",
        "aspect": "landscape",
        "scenes_default": 5,
        "tone": (
            "A dramatic cinematic teaser trailer. Narration is sparse, evocative, mysterious — "
            "fragments more than full sentences. No exposition, no ads. Think movie trailer VO. "
            "Each line is a punch."
        ),
    },
}


def _build_system(format_key: str, scene_count: int) -> str:
    f = FORMATS[format_key]
    return f"""You are a professional video script writer. You write TIGHT, RESEARCHED, specific lines — never filler, never improv.

Format: {f["label"]}
Tone & structure: {f["tone"]}

First, identify the MAIN SUBJECT of the topic (the proper noun / specific thing). Examples:
  "did you know fun facts about Green Lantern" → main subject = "Green Lantern"
  "the history of Saturn's rings" → main subject = "Saturn"
  "the strangest deep sea creatures" → main subject = "deep sea creatures"

Return STRICT JSON ONLY matching:
{{
  "title": "<2-5 word title, no punctuation>",
  "topic_context": "<10-20 word visual style hint. MUST include the main subject name (e.g. 'Green Lantern comic book art, cinematic lighting, emerald glow, DC comics style')>",
  "scenes": [
    {{
      "narration": "<spoken by narrator, 10-25 words, matches the tone above>",
      "image_prompt": "<MUST start with the main subject name followed by the specific scene visual. Example for Green Lantern: 'Green Lantern Hal Jordan hovering with power ring glowing, emerald energy radiating, cinematic DC comics art'. 15-30 words. Include specific named characters, items, locations tied to the subject whenever possible.>",
      "search": "<MUST begin with the main subject name, followed by 1-3 extra concrete nouns describing this specific scene. Example: 'Green Lantern Hal Jordan', 'Saturn rings Cassini', 'octopus coral reef'. 3-5 words total.>"
    }}
  ]
}}

Hard rules — do NOT break these:
- Exactly {scene_count} scenes.
- EVERY image_prompt MUST literally contain the main subject's name. If the topic is Green Lantern, the words "Green Lantern" appear in every image_prompt.
- EVERY search field MUST begin with the main subject's name.
- Use specific named characters, items, places tied to the subject when relevant (e.g. for Green Lantern: Hal Jordan, Alan Scott, Guy Gardner, John Stewart, Kyle Rayner, Oa, Guardians, Central Power Battery, Sinestro, Yellow Lanterns).
- Narration must be REAL FACTS or coherent professional writing. If you don't know a fact, write a general true statement — do NOT invent nonsense.
- BANNED words/phrases in narration: "Yay", "Wild", "Truly wild", "Try that next time", "Wow", "OMG", filler exclamations, directly addressing the viewer, meta commentary.
- Each line must stand on its own and sound like a documentary narrator.
- Output JSON only — no markdown, no code fences, no commentary.
"""


# ---------- JSON file loading ----------

def load_script_file(path: Path) -> Script:
    data = json.loads(Path(path).read_text())
    ctx = data.get("topic_context")
    scenes = []
    for s in data["scenes"]:
        prompt = s["image_prompt"]
        if ctx:
            prompt = f"{ctx}. {prompt}"
        scenes.append(Scene(
            narration=s["narration"],
            image_prompt=prompt,
            search=s.get("search", ""),
        ))
    return Script(
        title=data["title"],
        scenes=scenes,
        voice=data.get("voice"),
        topic_context=ctx,
        aspect=data.get("aspect", "landscape"),
    )


# ---------- LLM paths ----------

def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def _build_script(data: dict, aspect: str) -> Script:
    ctx = data.get("topic_context")
    scenes = []
    for s in data["scenes"]:
        prompt = s["image_prompt"]
        if ctx:
            prompt = f"{ctx}. {prompt}"
        scenes.append(Scene(
            narration=s["narration"],
            image_prompt=prompt,
            search=s.get("search", ""),
        ))
    return Script(
        title=data["title"],
        scenes=scenes,
        voice=data.get("voice"),
        topic_context=ctx,
        aspect=aspect,
    )


def generate_script_groq(topic: str, format_key: str = "explainer", scene_count: int | None = None) -> Script:
    """Primary LLM path — free, no billing. Needs GROQ_API_KEY."""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    fmt = FORMATS[format_key]
    scenes = scene_count or fmt["scenes_default"]
    system = _build_system(format_key, scenes)

    models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    last_err = None
    resp = None
    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.6,  # lower temp → fewer "Yay"-style improvisations
                max_tokens=1500,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Topic: {topic}"},
                ],
            )
            break
        except Exception as e:
            last_err = e
    if resp is None:
        raise RuntimeError(f"All Groq models failed: {last_err}")

    return _build_script(_parse_json(resp.choices[0].message.content), fmt["aspect"])


def generate_script_anthropic(topic: str, format_key: str = "explainer", scene_count: int | None = None) -> Script:
    """Fallback LLM path — higher quality but needs paid credit."""
    import anthropic
    fmt = FORMATS[format_key]
    scenes = scene_count or fmt["scenes_default"]
    system = _build_system(format_key, scenes)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    return _build_script(_parse_json(msg.content[0].text), fmt["aspect"])


def generate_script(topic: str, format_key: str = "explainer", scene_count: int | None = None) -> Script:
    """Try Groq first (free), fall back to Anthropic if configured."""
    if os.environ.get("GROQ_API_KEY"):
        return generate_script_groq(topic, format_key, scene_count)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return generate_script_anthropic(topic, format_key, scene_count)
    raise RuntimeError("No LLM configured. Set GROQ_API_KEY (free) or ANTHROPIC_API_KEY in .env.")
