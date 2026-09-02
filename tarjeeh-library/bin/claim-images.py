#!/usr/bin/env python3
"""
Allocate library images to a client build.

Solves the one real drawback of a shared library: two competing Sharjah
cleaning companies landing the same hero. The usage log records which client
took which file, and allocation refuses to repeat a photo inside the same
industry+emirate pair.

Copies ONE image set for the client and mirrors it into v1/, v2/ and v3/.
The three versions share the photographs and differ by treatment -- crop,
grading, overlay, placement. That is what keeps licensing at 1x instead of 3x.

Usage:
    python3 bin/claim-images.py \
        --client bearing-mart --industry trading-wholesale --emirate sharjah \
        --slots hero,about,service-bearings,service-seals,service-belts \
        --out /home/claude/build/bearing-mart
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "library-manifest.json"
LIBRARY = ROOT / "library"
USAGE_DIR = ROOT / "usage"          # one file per client, never one shared file

# A single usage-log.json would conflict in git every time two people ran a
# build in parallel. One small file per client is append-only by construction,
# so git merges are always clean and nobody has to resolve JSON by hand.

# Recommended dimensions per slot type, used for IMAGE-MAP.md.
SLOT_DIMS = {
    "hero": "1920x1080",
    "about": "1200x800",
    "cta": "1920x600",
    "gallery": "1200x900",
}


def slot_dims(slot):
    for k, v in SLOT_DIMS.items():
        if slot.startswith(k):
            return v
    return "1200x800"          # service and generic slots


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--industry", required=True)
    ap.add_argument("--emirate", default="uae")
    ap.add_argument("--slots", required=True,
                    help="comma-separated slot names, e.g. hero,about,service-ac")
    ap.add_argument("--out", required=True, help="client build folder")
    ap.add_argument("--variants", default="v1,v2,v3")
    ap.add_argument("--auto-topup", action="store_true",
                    help="if the library is short, fetch more and continue "
                         "instead of stopping. Needs API keys and network.")
    args = ap.parse_args()

    manifest = load(MANIFEST, None)
    if not manifest:
        raise SystemExit("No manifest. Run build-library.py / sync-library.py first.")

    pool = manifest["industries"].get(args.industry)
    if not pool:
        raise SystemExit(f"No images for industry '{args.industry}'. "
                         f"Available: {', '.join(sorted(manifest['industries']))}")

    USAGE_DIR.mkdir(exist_ok=True)
    claims = []
    for f in sorted(USAGE_DIR.glob("*.json")):
        try:
            claims.extend(json.loads(f.read_text()).get("claims", []))
        except Exception as e:
            print(f"  ! unreadable usage file {f.name}: {e}")
    slots = [s.strip() for s in args.slots.split(",") if s.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]

    # Photos already used in this industry+emirate are off limits.
    blocked = {c["filename"] for c in claims
               if c["industry"] == args.industry and c["emirate"] == args.emirate
               and c["client"] != args.client}
    # Global use count, so the library wears evenly instead of always
    # handing out the first forty results.
    counts = {}
    for c in claims:
        counts[c["filename"]] = counts.get(c["filename"], 0) + 1

    available = [p for p in pool
                 if p["filename"] not in blocked
                 and (LIBRARY / args.industry / p["filename"]).exists()]
    available.sort(key=lambda p: counts.get(p["filename"], 0))

    if len(available) < len(slots):
        shortfall = len(slots) - len(available)
        topup = shortfall + 15          # headroom, so the next client is fine too
        if args.auto_topup:
            print(f"Library short by {shortfall}. Fetching {topup} more "
                  f"for {args.industry}...")
            before = len(pool)
            r = subprocess.run(
                [sys.executable, str(ROOT / "bin" / "build-library.py"),
                 "--industry", args.industry, "--add", str(topup)])
            if r.returncode != 0:
                raise SystemExit("Top-up failed. Check API keys and network egress.")
            r = subprocess.run(
                [sys.executable, str(ROOT / "bin" / "sync-library.py"),
                 "--industry", args.industry])
            if r.returncode != 0:
                raise SystemExit("Sync failed after top-up.")
            # Re-read: the manifest and the folder have both changed.
            manifest = load(MANIFEST, None)
            pool = manifest["industries"][args.industry]
            # build-library.py catches API errors internally and still exits 0,
            # so a zero exit code does not mean images arrived. Check the count.
            if len(pool) == before:
                raise SystemExit(
                    "Top-up added 0 images. Almost always one of:\n"
                    "  - PEXELS_API_KEY / PIXABAY_API_KEY not set "
                    "(source keys.env)\n"
                    "  - network egress blocked in this chat "
                    "(test: curl -s -o /dev/null -w '%{http_code}' "
                    "https://images.pexels.com/)\n"
                    "  - search terms for this industry exhausted "
                    "(add more in config/industries.json)\n"
                    "Do NOT proceed with unrelated or duplicate photographs.")
            available = [p for p in pool
                         if p["filename"] not in blocked
                         and (LIBRARY / args.industry / p["filename"]).exists()]
            available.sort(key=lambda p: counts.get(p["filename"], 0))
            print(f"Top-up done. {len(available)} now available.\n")

    if len(available) < len(slots):
        raise SystemExit(
            f"Only {len(available)} unused images for {args.industry} in "
            f"{args.emirate}, need {len(slots)}.\n"
            f"Run: python3 bin/build-library.py --industry {args.industry} "
            f"--add {len(slots) - len(available) + 15}\n"
            f"Or re-run this command with --auto-topup.")

    out = Path(args.out)
    assigned, rows, new_claims = [], [], []

    for slot, photo in zip(slots, available):
        src = LIBRARY / args.industry / photo["filename"]
        target_name = f"{slot}.jpg"
        for v in variants:
            dest_dir = out / v / "assets" / "img"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / target_name)
        assigned.append((slot, photo))
        rows.append((target_name, slot, photo["source"], slot_dims(slot),
                     photo["description"][:70]))
        new_claims.append({
            "client": args.client,
            "industry": args.industry,
            "emirate": args.emirate,
            "slot": slot,
            "filename": photo["filename"],
            "source_url": photo["source_url"],
            "claimed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    # Re-claiming for the same client overwrites that client's file, so a
    # rebuild does not permanently burn images.
    (USAGE_DIR / f"{args.client}.json").write_text(
        json.dumps({"client": args.client, "industry": args.industry,
                    "emirate": args.emirate, "claims": new_claims}, indent=2))

    # IMAGE-MAP.md is a mandatory deliverable, so generate it rather than
    # relying on it being written by hand at the end of a long build.
    w = max(len(r[0]) for r in rows) + 2
    lines = [f"# Image map - {args.client}", "",
             f"Industry: {args.industry}    Emirate: {args.emirate}",
             f"Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", "",
             "Same image set across v1/v2/v3. Versions differ by treatment",
             "(crop, aspect, grading, overlay, placement), not by photograph.", "",
             f"| {'File'.ljust(w)} | Slot | Source | Size | Shows |",
             f"|{'-'*(w+2)}|------|--------|------|-------|"]
    for fn, slot, src, dims, desc in rows:
        lines.append(f"| {fn.ljust(w)} | {slot} | {src} | {dims} | {desc} |")
    lines += ["", "## Provenance", ""]
    for slot, p in assigned:
        lines.append(f"- **{slot}.jpg** - {p['license']}")
        lines.append(f"  - source: {p['source_url']}")
        lines.append(f"  - photographer: {p.get('photographer') or 'n/a'}")
    lines += ["", "## Replacing with client photos", "",
              "Overwrite the file in each variant's `assets/img/` using the exact",
              "filename above. No code changes are needed.", ""]

    (out / "IMAGE-MAP.md").write_text("\n".join(lines))

    print(f"Claimed {len(assigned)} images for {args.client}")
    for v in variants:
        print(f"  -> {out / v / 'assets' / 'img'}")
    print(f"  -> {out / 'IMAGE-MAP.md'}")
    print(f"\nRemaining unused for {args.industry}/{args.emirate}: "
          f"{len(available) - len(assigned)}")


if __name__ == "__main__":
    main()
