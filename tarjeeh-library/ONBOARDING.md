# Developer onboarding

Everything a developer needs to use the shared library. Roughly fifteen
minutes, once.

## What you do NOT need

- **No API keys.** Keys are only for extending the library. Syncing pulls from
  public URLs already recorded in the manifest.
- **No Pexels or Pixabay account.**
- **No Adobe subscription.**
- **No shared drive, Dropbox or Google Drive.**

## What you do need

- Read access to `umarmalik01/tarjeeh-image-library` (ask Malik to add you as
  a collaborator — it is a private repo)
- Python 3.8 or newer
- About 1 GB of free disk

## Setup

```bash
git clone https://github.com/umarmalik01/tarjeeh-image-library.git
cd tarjeeh-image-library
python3 bin/sync-library.py
```

That downloads every photograph in the manifest into `library/<industry>/`.
Ten to twenty minutes on a decent connection. You now hold a byte-identical
copy of the library.

To pull only what you need:

```bash
python3 bin/sync-library.py --industry cleaning
```

## Daily use

**Before every build, pull.** Someone else may have claimed images since you
last synced.

```bash
git pull
python3 bin/sync-library.py          # picks up anything new
```

**Claim images for the client:**

```bash
python3 bin/claim-images.py \
  --client al-noor-cleaning \
  --industry cleaning \
  --emirate dubai \
  --slots hero,about,service-deep,service-office,service-villa \
  --out ~/builds/al-noor-cleaning
```

This copies one image set into `v1/`, `v2/` and `v3/`, writes `IMAGE-MAP.md`
with full provenance, and creates `usage/al-noor-cleaning.json`.

**After the build, push the claim:**

```bash
git add usage/al-noor-cleaning.json
git commit -m "claim: al-noor-cleaning (cleaning/dubai)"
git push
```

This is the step that matters. Until you push, nobody else knows those
photographs are taken, and a colleague could hand the same hero image to a
competing Dubai cleaning company.

## Why there are no merge conflicts

Each build writes its own file under `usage/`. Two people building at the same
time create two different files, so git merges cleanly every time. There is no
single shared log to fight over.

Re-running a claim for the same client overwrites that client's file rather
than appending, so rebuilding a site does not permanently consume extra
images.

## When the library runs short

```
Only 4 unused images for cleaning in dubai, need 6.
Run: python3 bin/build-library.py --industry cleaning --per-industry 46
```

Topping up **does** need API keys. Either ask Malik to run it and push the
updated manifest, or get your own free keys from `pexels.com/api/key` and
`pixabay.com/api/docs`, put them in `keys.env`, and run it yourself.

If you run it, push `library-manifest.json` so everyone else benefits:

```bash
git add library-manifest.json
git commit -m "library: +20 cleaning"
git push
```

Never substitute an unrelated photograph because the library is short. Top it
up.

## Rules that are not negotiable

These come from the Tarjeeh project instructions and apply regardless of who
is building.

- Client-uploaded photographs override the library entirely.
- Every person shown must pass the worker test: dressed as a worker, hands
  engaged in the task, environment matching the service.
- Prefer photographs without identifiable faces. Free platforms provide no
  model releases and no indemnification, and every site we build is
  commercial use.
- Within a version, every slot gets its own photograph.
- The three versions share the photographs and differ by treatment — crop,
  grading, overlay, placement. Never source three separate sets.
- Relative paths only. Never hotlink; Pixabay's terms prohibit it outright.
- Ship `IMAGE-MAP.md` with every build. It is generated for you.

## If a sync fails

`sync-failures.json` lists photographs whose source URL has died, usually
meaning removal from the platform. Report them to Malik so the entries get
pruned and backfilled. Do not leave holes in the library.
