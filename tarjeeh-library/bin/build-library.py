#!/usr/bin/env python3
"""
Tarjeeh image library builder.

Searches free stock APIs by industry, applies the worker-test caption filter,
dedupes, and writes a provenance manifest. Downloads NOTHING -- the manifest
is the shared artefact. Run sync-library.py to materialise the actual files.

Keeping the manifest and the pixels separate is deliberate: the manifest is a
few hundred KB of JSON that lives in git, so any machine or any Claude account
can rebuild the identical library from it.

Usage:
    export PEXELS_API_KEY=...        # https://www.pexels.com/api/key/
    export PIXABAY_API_KEY=...       # https://pixabay.com/api/docs/
    python3 build-library.py --per-industry 40
    python3 build-library.py --industry cleaning --per-industry 60
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "industries.json"
MANIFEST = ROOT / "library-manifest.json"

# ---------------------------------------------------------------------------
# Worker test, rule 4: reject on the photo's own description.
# Stock libraries label their lifestyle shoots honestly, so this is the
# cheapest filter available and it catches most failures before a human looks.
# ---------------------------------------------------------------------------
CAPTION_BLOCKLIST = [
    "dancing", "dance", "singing", "having fun", "headphones", "cheerful",
    "housewife", "lifestyle", "model", "portrait of a beautiful", "beautiful woman",
    "sexy", "bikini", "fashion", "posing", "smiling at camera", "selfie",
    "happy family", "romantic", "couple", "vacation", "holiday", "party",
    "yoga", "fitness", "workout", "celebrating", "girl", "boy",
    # Added after the first real seeding run: 16 of 80 photos failed the
    # worker test using wording the original list did not know.
    "posing", "poses", "shows", "showing off", "renovating her",
    "renovating his", "diy", "do it yourself", "homeowner",
    "hotel", "luggage", "room service", "guest room", "suite",
    "learning session", "training session", "seminar", "classroom",
    "fun and", "relaxing", "resting", "leisure",
    "black and white", "greyscale", "grayscale", "monochrome",
]

# Rejected regardless of caption: AI slop and illustration masquerading as photo.
FORMAT_BLOCKLIST = ["illustration", "vector", "3d render", "cartoon", "clipart",
                    "ai generated", "ai-generated", "digital art"]

MIN_WIDTH = 1600
MIN_HEIGHT = 900


# Pexels' edge rejects the default Python-urllib User-Agent with a 403 that
# looks exactly like a bad API key. Always send a browser UA.
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}


def http_json(url, headers=None, timeout=25):
    h = dict(BASE_HEADERS)
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def caption_clean(text):
    """True if the caption survives the worker test's rule 4."""
    t = (text or "").lower()
    for bad in CAPTION_BLOCKLIST + FORMAT_BLOCKLIST:
        if bad in t:
            return False
    return True


def big_enough(w, h):
    return (w or 0) >= MIN_WIDTH and (h or 0) >= MIN_HEIGHT


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def search_pexels(query, per_page=40):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    url = ("https://api.pexels.com/v1/search?"
           + urllib.parse.urlencode({"query": query, "per_page": min(per_page, 80),
                                     "orientation": "landscape"}))
    try:
        data = http_json(url, {"Authorization": key})
    except Exception as e:
        print(f"    pexels error: {e}", file=sys.stderr)
        return []
    out = []
    for p in data.get("photos", []):
        alt = p.get("alt") or ""
        if not caption_clean(alt) or not big_enough(p.get("width"), p.get("height")):
            continue
        out.append({
            "source": "pexels",
            "source_id": str(p["id"]),
            "description": alt,
            "width": p["width"], "height": p["height"],
            "download_url": p["src"]["large2x"],
            "source_url": p["url"],
            "photographer": p.get("photographer"),
            "photographer_url": p.get("photographer_url"),
            "license": "Pexels License - free commercial use, no attribution required",
            "attribution_required": False,
        })
    return out


def search_pixabay(query, per_page=40):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    url = ("https://pixabay.com/api/?"
           + urllib.parse.urlencode({"key": key, "q": query,
                                     "image_type": "photo", "orientation": "horizontal",
                                     "per_page": min(per_page, 200), "safesearch": "true",
                                     "min_width": MIN_WIDTH}))
    try:
        data = http_json(url)
    except Exception as e:
        print(f"    pixabay error: {e}", file=sys.stderr)
        return []
    out = []
    for p in data.get("hits", []):
        tags = p.get("tags") or ""
        if not caption_clean(tags) or not big_enough(p.get("imageWidth"), p.get("imageHeight")):
            continue
        out.append({
            "source": "pixabay",
            "source_id": str(p["id"]),
            "description": tags,
            "width": p["imageWidth"], "height": p["imageHeight"],
            "download_url": p.get("largeImageURL"),
            "source_url": p.get("pageURL"),
            "photographer": p.get("user"),
            "photographer_url": f"https://pixabay.com/users/{p.get('user')}-{p.get('user_id')}/",
            "license": "Pixabay Content License - free commercial use, no attribution required",
            "attribution_required": False,
        })
    return out


def search_openverse(query, per_page=20):
    """No API key needed. Anonymous is throttled to ~1 req/sec, 20 per page.
    CC0 and Public Domain ONLY -- CC-BY would force visible attribution onto
    the client's site, which we will not ship."""
    url = ("https://api.openverse.org/v1/images/?"
           + urllib.parse.urlencode({"q": query, "license": "cc0,pdm",
                                     "page_size": min(per_page, 20),
                                     "aspect_ratio": "wide"}))
    try:
        data = http_json(url, {"User-Agent": "TarjeehLibrary/1.0"})
    except Exception as e:
        print(f"    openverse error: {e}", file=sys.stderr)
        return []
    out = []
    for p in data.get("results", []):
        title = p.get("title") or ""
        if not caption_clean(title) or not big_enough(p.get("width"), p.get("height")):
            continue
        out.append({
            "source": "openverse",
            "source_id": str(p["id"]),
            "description": title,
            "width": p.get("width"), "height": p.get("height"),
            "download_url": p.get("url"),
            "source_url": p.get("foreign_landing_url"),
            "photographer": p.get("creator"),
            "photographer_url": p.get("creator_url"),
            "license": f"{p.get('license','').upper()} via Openverse",
            "attribution_required": False,
        })
    return out


SOURCES = [
    ("pexels", search_pexels, 0.4),
    ("pixabay", search_pixabay, 0.7),
    ("openverse", search_openverse, 1.1),   # anonymous tier: ~1 req/sec
]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"generated": None, "industries": {}}


def build(industries, per_industry, only=None, add=None):
    manifest = load_manifest()
    manifest.setdefault("industries", {})

    for industry, queries in industries.items():
        if industry.startswith("_comment"):
            continue
        if only and industry != only:
            continue

        existing = manifest["industries"].get(industry, [])
        # --add is relative: "give me N MORE than I already have". The manifest
        # is always additive -- nothing is ever replaced or re-downloaded, and
        # dedupe is by (source, id), so re-running is safe and cheap.
        target = len(existing) + add if add else per_industry
        seen = {(p["source"], p["source_id"]) for p in existing}
        seen_urls = {p["download_url"] for p in existing}
        collected = list(existing)

        print(f"\n[{industry}] have {len(existing)}, target {target}")

        # A single productive term will otherwise fill the whole quota -- the
        # first cleaning run produced 40 photos of mopping and never reached
        # the other seven terms. Useless, because every service slot needs its
        # own matching photograph. Cap each term to a fair share on pass one,
        # then lift the cap on pass two to top up any shortfall.
        need = max(0, target - len(collected))
        fair_share = max(3, -(-need // max(1, len(queries)))) if need else 0

        for pass_no, cap in enumerate([fair_share, None], start=1):
          if len(collected) >= target:
              break
          if pass_no == 2:
              print(f"  -- pass 2: lifting per-term cap to reach {target}")
          for query in queries:
              if len(collected) >= target:
                  break
              print(f"  ? {query}")
              for name, fn, delay in SOURCES:
                  if len(collected) >= target:
                      break
                  results = fn(query)
                  added = 0
                  term_cap = cap
                  for r in results:
                      if len(collected) >= target:
                          break
                      if term_cap is not None and added >= term_cap:
                          break
                      kdup = (r["source"], r["source_id"])
                      if kdup in seen or r["download_url"] in seen_urls:
                          continue
                      if not r["download_url"]:
                          continue
                      r["query"] = query
                      r["industry"] = industry
                      r["added"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                      r["filename"] = f"{r['source']}-{r['source_id']}.jpg"
                      seen.add(kdup)
                      seen_urls.add(r["download_url"])
                      collected.append(r)
                      added += 1
                  print(f"      {name}: +{added} (total {len(collected)})")
                  time.sleep(delay)

        manifest["industries"][industry] = collected

    manifest["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["totals"] = {k: len(v) for k, v in manifest["industries"].items()}
    manifest["total_images"] = sum(manifest["totals"].values())
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written: {MANIFEST}")
    print(f"Total images: {manifest['total_images']}")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-industry", type=int, default=40)
    ap.add_argument("--industry", help="build one industry only")
    ap.add_argument("--add", type=int,
                    help="add N MORE images to what already exists "
                         "(relative; overrides --per-industry)")
    args = ap.parse_args()

    if not os.environ.get("PEXELS_API_KEY") and not os.environ.get("PIXABAY_API_KEY"):
        print("WARNING: no PEXELS_API_KEY or PIXABAY_API_KEY set.\n"
              "Openverse alone will be used and results will be thin.\n", file=sys.stderr)

    industries = json.loads(CONFIG.read_text())
    build(industries, args.per_industry, args.industry, args.add)


if __name__ == "__main__":
    main()
