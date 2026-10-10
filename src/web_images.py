"""Wikipedia Commons image search — real photos, no API key required.

Flow per scene:
  1. srsearch Commons in the File namespace (6) for the search terms
  2. For the top N results, fetch imageinfo to get the actual file URL + size
  3. Pick the first result that is a reasonable raster photo (jpeg/png) and
     larger than MIN_PIXELS so we skip icons and logos
  4. Download, resize to our canvas, letterbox if aspect mismatches
"""
from __future__ import annotations

import hashlib
import io
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
MIN_PIXELS = 400 * 300          # skip tiny icons
MAX_RESULTS_PER_QUERY = 10
UA = "video-gen/0.1 (prototype; https://github.com/Vince0010/video-gen)"


def _search_commons(query: str, limit: int = MAX_RESULTS_PER_QUERY) -> list[str]:
    """Return a list of File:... titles from a Commons search."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,       # File namespace
        "srlimit": limit,
        "format": "json",
        "srinfo": "",
        "srprop": "",
    }
    r = requests.get(COMMONS_API, params=params, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    data = r.json()
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def _file_info(titles: list[str]) -> list[dict]:
    """Fetch imageinfo (url, size, mime) for a batch of File:... titles."""
    if not titles:
        return []
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": 1600,  # scaled-down URL
        "format": "json",
    }
    r = requests.get(COMMONS_API, params=params, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    data = r.json()
    pages = data.get("query", {}).get("pages", {})
    out = []
    for p in pages.values():
        infos = p.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        out.append({
            "title": p.get("title", ""),
            "url": info.get("thumburl") or info.get("url"),
            "width": info.get("thumbwidth") or info.get("width", 0),
            "height": info.get("thumbheight") or info.get("height", 0),
            "mime": info.get("mime", ""),
        })
    return out


def _is_usable_photo(info: dict) -> bool:
    mime = info.get("mime", "")
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        return False
    w, h = info.get("width", 0), info.get("height", 0)
    if w * h < MIN_PIXELS:
        return False
    # Skip obvious logos / coat-of-arms
    title = info.get("title", "").lower()
    if any(skip in title for skip in ("logo", "coat_of_arms", "crest", "icon", ".svg")):
        return False
    return True


def _download_fit(url: str, out_path: Path, size: tuple[int, int]) -> None:
    """Download, resize-and-crop to the target aspect ratio."""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    tw, th = size
    iw, ih = img.size
    # Cover-fit: scale so the shorter dim matches, then center-crop.
    scale = max(tw / iw, th / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - tw) // 2
    top = (new_h - th) // 2
    img = img.crop((left, top, left + tw, top + th))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92)


def _try_commons(query: str, out_path: Path, size: tuple[int, int]) -> bool:
    try:
        titles = _search_commons(query)
    except Exception as e:
        print(f"    commons({query!r}) search error: {e}")
        return False
    if not titles:
        return False
    infos = _file_info(titles)
    for info in infos:
        if not _is_usable_photo(info):
            continue
        try:
            _download_fit(info["url"], out_path, size)
            return True
        except Exception as e:
            print(f"    commons({query!r}) download fail: {e}")
            continue
    return False


def _try_openverse(query: str, out_path: Path, size: tuple[int, int]) -> bool:
    """Openverse aggregates CC-licensed images from Flickr, museums, Wikimedia, etc.
    No API key required for the public endpoint."""
    try:
        r = requests.get(
            OPENVERSE_API,
            params={"q": query, "page_size": 10, "license_type": "all"},
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=20,
        )
        if r.status_code != 200:
            return False
        results = r.json().get("results", [])
    except Exception as e:
        print(f"    openverse({query!r}) search error: {e}")
        return False
    for item in results:
        url = item.get("url") or item.get("thumbnail")
        if not url:
            continue
        w = item.get("width", 0) or 0
        h = item.get("height", 0) or 0
        if w and h and w * h < MIN_PIXELS:
            continue
        try:
            _download_fit(url, out_path, size)
            return True
        except Exception as e:
            print(f"    openverse download fail: {e}")
            continue
    return False


def _extract_nouns(text: str) -> list[str]:
    """Pull candidate 2-3 word noun phrases from a longer prompt — crude but works."""
    import re
    text = re.sub(r"[^A-Za-z0-9 ]", " ", text)
    words = [w for w in text.split() if len(w) > 2]
    stop = {"the", "and", "with", "that", "this", "from", "into", "them", "they", "them",
            "them", "then", "these", "those", "where", "when", "while", "there", "which",
            "cinematic", "35mm", "film", "still", "4K", "dramatic", "lighting", "mood"}
    kept = [w for w in words if w.lower() not in stop]
    phrases = []
    if len(kept) >= 2:
        phrases.append(" ".join(kept[:3]))
        phrases.append(" ".join(kept[:2]))
    phrases += kept[:5]
    seen, out = set(), []
    for p in phrases:
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        out.append(p)
    return out


def find_image(query: str, out_path: Path, size: tuple[int, int], topic: str = "") -> bool:
    """Search multiple web sources until a real photo is found.

    Query order:
      1. the provided query (most specific)
      2. the topic alone (reliable fallback for popular subjects)
      3. extracted noun phrases from the query
      4. the extracted phrases again, via Openverse
    """
    tried: list[str] = []

    def _attempt(q: str, source_fn) -> bool:
        q = q.strip()
        if not q or q in tried:
            return False
        tried.append(q)
        return source_fn(q, out_path, size)

    # Try Commons first (highest-quality curated photos)
    if _attempt(query, _try_commons):
        return True
    if topic and _attempt(topic, _try_commons):
        return True
    for phrase in _extract_nouns(query):
        if _attempt(phrase, _try_commons):
            return True

    # Then Openverse (aggregates many free sources)
    tried.clear()
    if _attempt(query, _try_openverse):
        return True
    if topic and _attempt(topic, _try_openverse):
        return True
    for phrase in _extract_nouns(query):
        if _attempt(phrase, _try_openverse):
            return True

    return False


def fetch_web_images(
    queries: list[str],
    scratch_dir: Path,
    size: tuple[int, int],
    progress_cb=None,
) -> list[Path | None]:
    """One image per query. Returns a list where None means 'not found'."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path | None] = []
    for i, q in enumerate(queries):
        p = scratch_dir / f"scene_{i:02d}.jpg"
        print(f"  scene {i+1}/{len(queries)}: Commons search {q!r} ... ", end="", flush=True)
        ok = find_image(q, p, size)
        print("OK" if ok else "no match")
        out.append(p if ok else None)
        if progress_cb:
            try:
                progress_cb(i, len(queries), p if ok else None, "commons" if ok else "miss")
            except Exception:
                pass
        time.sleep(0.3)  # polite rate
    return out
