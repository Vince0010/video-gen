# video-gen

Automated short-form video generator. **Topic in, mp4 out.** Built in a 2-hour timebox.

```
┌──────┐   ┌─────────┐   ┌─────────┐   ┌────────────┐   ┌─────────┐
│topic │──▶│ Groq    │──▶│edge-tts │──▶│Pollinations│──▶│ MoviePy │──▶ out/your-topic.mp4
│      │   │(script) │   │(voice)  │   │(images)    │   │(assemble)│
└──────┘   └─────────┘   └─────────┘   └────────────┘   └─────────┘
```

## What it does on its own

Give it a topic, it produces a ~30-second mp4 with:
- A 5-scene narrated script written by Llama / GPT-OSS (Groq free tier)
- Voiceover in a natural neural voice (edge-tts, no key)
- Scene-matched AI-generated images with Ken Burns zoom (Pollinations.ai)
- Burned-in captions on a semi-transparent lower-third
- Title + outro cards with crossfades
- A looped ambient music bed, auto-ducked under the narration

Zero clicks between the topic and the mp4.

## Setup

```bash
git clone https://github.com/Vince0010/video-gen.git
cd video-gen
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install ffmpeg imagemagick     # macOS; Linux: apt install ffmpeg imagemagick
cp .env.example .env                # then paste GROQ_API_KEY (free: console.groq.com)
```

## Usage

**CLI, from topic:**
```bash
.venv/bin/python main.py "why octopuses are smart"
# → out/why-octopuses-are-smart.mp4
```

**CLI, from a prebuilt script (no LLM):**
```bash
.venv/bin/python main.py --script samples/lanterns.json
# → out/lanterns.mp4
```

**Web UI:**
```bash
.venv/bin/streamlit run app.py
# open http://localhost:8501
```

## Keys

Only one is required: **`GROQ_API_KEY`** (free at [console.groq.com/keys](https://console.groq.com/keys)).

Optional:
- `POLLINATIONS_API_KEY` — slightly higher image rate limits
- `ANTHROPIC_API_KEY` — fallback LLM if Groq is unavailable

## Project layout

```
main.py              # CLI entry
app.py               # Streamlit UI
src/
  script.py          # Groq / Anthropic → scene JSON
  tts.py             # edge-tts voiceover per scene
  visuals.py         # Pollinations fetch + watermark strip + PIL fallback
  placeholder.py     # local cinematic card renderer (fallback when API 402s)
  assemble.py        # MoviePy: Ken Burns, lower-third, crossfades, music mix
samples/
  lanterns.json      # hand-authored script (bypass LLM)
assets/music/
  ambient.mp3        # ffmpeg-synthesized cinematic drone
out/                 # generated mp4s land here
scratch/             # per-run intermediate audio/images (gitignored)
```

## Pipeline, in detail

1. **Script** — Groq's `openai/gpt-oss-120b` is prompted for strict JSON: a title, a `topic_context` style hint, and 5 scenes with narration + image prompt. The context is prepended to every image prompt so visual style is consistent across the video.
2. **Voiceover** — Each scene's narration is sent to edge-tts, producing an mp3 per scene.
3. **Images** — Each image prompt is fetched from `image.pollinations.ai/prompt/...` at 1152x648 (the free tier's reliable 16:9 resolution). On 402 (rate limit), retries across models; if all fail, falls back to a locally-rendered dark cinematic card.
4. **Watermark strip** — Pollinations' free-tier watermark is cropped off the bottom of every image.
5. **Assembly** — MoviePy builds each scene clip: oversize the image, apply a time-varying zoom (Ken Burns), overlay a semi-transparent black lower-third, burn the caption on top, attach the voiceover audio. Crossfade between scenes. Prepend title card, append outro card. Mix a looped ambient music bed under the narration at 0.14 volume.
6. **Export** — `libx264` + `aac` into `out/<slug>.mp4`.

## Known limitations (2-hour prototype)

- One output format (short-form explainer). No listicle, product-demo, or news-clip layouts yet.
- Pollinations free tier rate-limits aggressively; a few scenes per run may fall back to the local placeholder. This is noticeable but doesn't break anything.
- Captions derived from the script (not Whisper-aligned), so timing is scene-granular not word-granular.
- English voices only (edge-tts can do more; just needs the voice picker expanded).
- No scene-length control from the UI (always 5 scenes); add `--scenes N` next.

## Why these choices

- **Groq over OpenAI/Anthropic for the LLM**: free tier, no card needed, response is near-instant.
- **edge-tts over ElevenLabs**: free, no key, Microsoft neural voices are already very good.
- **Pollinations over DALL·E/SD-API**: no key for small images, works everywhere, lets us demo without any paid dependency.
- **MoviePy over Remotion / After Effects**: single pip install, no browser/node runtime, mature.
- **Streamlit over React**: one Python file renders a complete UI; fits a 2-hour budget.
