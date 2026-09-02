#!/usr/bin/env python3
"""
Materialise the image library from library-manifest.json.

This is the script that makes the library portable. The manifest lives in git;
the pixels do not. Anyone with the repo -- you, your developer, a fresh Claude
sandbox, a new laptop -- runs this once and ends up with a byte-identical
library. No shared drive, no 400MB repo, no per-account setup.

Usage:
    python3 bin/sync-library.py                     # everything
    python3 bin/sync-library.py --industry cleaning # one industry
    python3 bin/sync-library.py --verify            # check, download nothing
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "library-manifest.json"
LIBRARY = ROOT / "library"

UA = {"User-Agent": "Mozilla/5.0 (compatible; TarjeehLibrary/1.0)"}


def fetch(url, dest, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < 10000:
        raise ValueError(f"suspiciously small ({len(data)} bytes)")
    dest.write_bytes(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--industry")
    ap.add_argument("--verify", action="store_true",
                    help="report what is missing without downloading")
    args = ap.parse_args()

    if not MANIFEST.exists():
        sys.exit(f"No manifest at {MANIFEST}. Run build-library.py first, "
                 f"or pull the repo that contains it.")

    manifest = json.loads(MANIFEST.read_text())
    industries = manifest.get("industries", {})

    have = miss = failed = 0
    failures = []

    for industry, photos in industries.items():
        if args.industry and industry != args.industry:
            continue
        outdir = LIBRARY / industry
        outdir.mkdir(parents=True, exist_ok=True)

        for p in photos:
            dest = outdir / p["filename"]
            if dest.exists() and dest.stat().st_size > 10000:
                have += 1
                continue
            if args.verify:
                miss += 1
                continue
            try:
                size = fetch(p["download_url"], dest)
                have += 1
                print(f"  + {industry}/{p['filename']}  {size//1024}KB")
            except Exception as e:
                failed += 1
                failures.append((industry, p["filename"], p["source_url"], str(e)))
                print(f"  ! {industry}/{p['filename']}: {e}", file=sys.stderr)

    print(f"\npresent: {have}   missing: {miss}   failed: {failed}")

    if failures:
        # A dead URL usually means the photo was removed from the source
        # platform. That is exactly when provenance disappears, so record it
        # and prune the entry rather than leaving a hole in the library.
        report = ROOT / "sync-failures.json"
        report.write_text(json.dumps(
            [{"industry": i, "file": f, "source": s, "error": e}
             for i, f, s, e in failures], indent=2))
        print(f"Failures recorded in {report}")
        print("Prune these from the manifest and re-run build-library.py to backfill.")


if __name__ == "__main__":
    main()
