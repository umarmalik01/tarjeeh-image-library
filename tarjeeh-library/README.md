# Tarjeeh Image Library

A shared, vetted stock library organised by industry. Source a photograph once,
use it across hundreds of client builds.

At 200–300 sites a month, sourcing images per client means roughly 3,600
downloads monthly, three API integrations to keep inside rate limits, and a
build that stalls whenever a quota runs out. Sourcing once per *industry*
instead means about 800 photographs total, assembled in an afternoon, and
builds that touch the network zero times.

---

## Why the manifest is the artefact, not the images

`library-manifest.json` holds provenance for every photograph — source URL,
photographer, licence, dimensions, description, download URL. It is a few
hundred KB and lives in git.

The actual JPEGs are **not** committed. Anyone who needs them runs
`sync-library.py` and rebuilds a byte-identical library from the manifest.

This is what makes the library shareable. Your developer, working from his own
Claude account on his own machine, clones the repo and runs one command. No
shared drive, no 400 MB repository, no per-account API setup, no drift between
his library and yours. When you add photographs, you commit the manifest; he
pulls and syncs.

---

## One-time setup

### 1. Get the free API keys

| Source | Where | Limits | Attribution |
|---|---|---|---|
| Pexels | `pexels.com/api/key` — instant | 200/hour, 20,000/month | Not required for the images themselves |
| Pixabay | `pixabay.com/api/docs` — shown inline once logged in | ~100 per 60s | Not required |
| Openverse | none needed | ~1 req/sec anonymous | CC0/PDM only, so none |

Both keys are free permanently. There is no paid tier for either.

If you expect to exceed the Pexels quota, they lift the limit free of charge
for eligible applications — worth requesting once the library is running.

### 2. Store the keys

```bash
cp keys.env.example keys.env      # then edit
source keys.env
```

`keys.env` is gitignored. Keys never go into chat, never into a client
package, never into the repo.

### 3. Seed the library

```bash
python3 bin/build-library.py --per-industry 40
```

Twenty industries at forty photographs each is 800 images, assembled with
roughly a hundred API calls. Comfortably inside a single day's quota.

**The library is additive and never rebuilt.** Every later run reads the
existing manifest, dedupes by (source, id), and appends. Nothing is replaced
and nothing is re-downloaded, so re-running is always safe.

To grow an industry, use `--add`, which is relative to what you already have:

```bash
python3 bin/build-library.py --industry cleaning --add 20   # 40 -> 60
```

### 4. Materialise it

```bash
python3 bin/sync-library.py
```

---

## Per-build usage

```bash
python3 bin/claim-images.py \
  --client bearing-mart \
  --industry trading-wholesale \
  --emirate sharjah \
  --slots hero,about,service-bearings,service-seals,service-belts \
  --out /home/claude/build/bearing-mart
```

This copies one image set into `v1/`, `v2/` and `v3/`, writes `IMAGE-MAP.md`
with full provenance, and records the claim so no other client in the same
industry and emirate receives the same photograph.

The three versions **share** the photographs. They differ by treatment — crop,
aspect ratio, focal point, grading, duotone, overlay, placement. That is art
direction, and it keeps licensing at 1× instead of 3×.

### When an industry runs short

Either let the build top itself up and carry on:

```bash
python3 bin/claim-images.py ... --auto-topup
```

That fetches the shortfall plus fifteen for headroom, syncs, and continues in
one step. It needs API keys and network. If it fetches nothing it stops and
says why rather than proceeding with duplicates.

Or handle it explicitly:

```
Only 4 unused images for trading-wholesale in sharjah, need 6.
Run: python3 bin/build-library.py --industry trading-wholesale --add 17
```

Either way the new photographs land in the **library** first and the build
claims from there. Images never go straight into a client folder, so every
top-up permanently benefits every future build.

---

## Keeping your developer in sync

```bash
# you, after adding photographs
git add library-manifest.json usage/ && git commit -m "library: +40 cleaning" && git push

# your developer
git pull && python3 bin/sync-library.py
```

Commit the files under `usage/` too — they prevent two people independently
handing the same hero image to two competing clients. One file per client
means git never produces a merge conflict, however many people build at once.

New developers: see ONBOARDING.md. They need repo access and Python. No API
keys, no accounts, no shared drive.

---

## Legal position — read this once

Free platforms carry **no indemnification and no model release verification**.
Pixabay's own terms state that commercial use — anything promoting a product or
service — likely requires consent or a licence, including model releases.
Pexels and Unsplash disclaim liability entirely and require *you* to indemnify
*them*.

Three practical consequences:

**Prefer photographs without identifiable faces.** Workers in PPE, gloved hands
on the task, figures from behind, cropped at the shoulder, focus on the work.
This is already what the worker test demands, so enforcing image quality
removes most of the legal exposure as a side effect.

**Keep the provenance.** Platforms delete the trail when a photograph is
removed, which is precisely when you would need it. The manifest is that
record — treat it as a compliance document, not a cache.

**Use Adobe for the exceptions.** The few heroes per year that genuinely need
an identifiable face justify a 10-credit Adobe plan, which carries up to
$10,000 in indemnification. Record those in the manifest with
`"source": "adobe"` and the licence ID.

`sync-failures.json` lists photographs whose source URL has died — usually
meaning removal from the platform. Prune those entries and backfill rather
than leaving holes.

---

## Files

```
config/industries.json     search terms per industry — edit to tune
bin/build-library.py       search, filter, dedupe, write manifest
bin/sync-library.py        manifest -> actual image files
bin/claim-images.py        allocate to a client, write IMAGE-MAP.md
library-manifest.json      provenance record (COMMIT THIS)
usage/<client>.json        which client got which photo (COMMIT THESE)
library/<industry>/        the JPEGs (gitignored)
keys.env                   API keys (gitignored)
```
