---
type: concept
status: current
sources: [.git, README.md, web/src/types/rasid360Config.ts, web/src/hooks/use-navigation.ts]
updated: 2026-08-28
---

# Fork Relationship

How Rasid360 relates to upstream Frigate, and what it costs to keep them related.

## The seam

| | |
|---|---|
| Upstream | `blakeblackshear/frigate` |
| Fork point | `de066d00` — "Fix i18n (#20857)", **2025-11-11** |
| Commits since | 24 |
| Aggregate diff | 666 files, +15,814 / −3,508 |
| Upstream git remote configured | **Yes** — `upstream` added 2026-08-24 |

### Measured gap, as of 2026-08-24

```
$ git rev-list --count de066d00..upstream/dev
1056
```

**1,056 commits behind.** Upstream's tip that day was `271051f15`, dated the same day — Frigate
is actively developed and the gap widens daily.

The overlap is worse than the raw count suggests:

- **511 files** changed by both upstream and this fork since the fork point
- **all** core-patched files are in that set: `video.py`, `camera/state.py`,
  `track/object_processing.py`, `app.py`, `api/fastapi_app.py`, and — since 2026-08-28 —
  `review/maintainer.py`, `util/builtin.py` and `api/media.py`

Re-measure with:

```bash
git fetch upstream
git rev-list --count de066d00..upstream/dev
comm -12 <(git diff --name-only de066d00 upstream/dev | sort) \
         <(git diff --name-only de066d00 HEAD | sort) | wc -l
```

## What makes merging feasible

The violation system is **almost entirely additive**. New directories (`frigate/extras/`),
new modules (`analytics_db.py`, `analytics_scheduler.py`, `api/dashboard.py`), new pages
(`web/src/pages/Dashboard.tsx`). None of it conflicts with upstream because upstream has no
files there.

Core Frigate files carry a small number of modified lines across a handful of files —
[Core Pipeline Patches](../components/core-pipeline-patches.md). That restraint was a good
decision and is the main asset when merging.

It is no longer quite as small as it was. The recording-retention work on 2026-08-28 patched
`review/maintainer.py` and `util/builtin.py`, two upstream files the fork had never touched,
taking the count from five to seven. Both patches are defensive and additive — `update_yaml`
only changes behaviour when the target key is absent, and the review maintainer's changes are
guarded by an `is_violation` flag that is False for everything upstream produces — but they are
two more files to reconcile.

## What makes merging painful

**The rename.** `FrigateConfig` → `Rasid360Config`, `frigateConfig.ts` → `rasid360Config.ts`,
`FrigatePlusSettingsView` → `Rasid360PlusSettingsView`, plus label and asset changes. This
touched roughly 500 files, nearly all of them in `web/src` — which is exactly where upstream
development is most active.

Every upstream commit touching a React component that imports the config type will now conflict.
The rename bought branding that is in any case incomplete: the Python package is still
`frigate/`, the class is still `FrigateAPI`, the database is still `frigate.db`, the MQTT topic
is still `frigate/events`, and the container image is still Frigate's.

**The route restructure.** `use-navigation.ts` remaps the app's information architecture:

| Route | Upstream | Rasid360 |
|---|---|---|
| `/` | Live | **Dashboard** |
| `/live` | — | Live |
| `/review` → `/playback` | Review | Playback |
| `/explore` → `/tickets` | Explore | Tickets |

Nav IDs were renumbered to insert `ID_DASHBOARD = 4`. Any upstream change to navigation
conflicts structurally, not just textually.

**Staleness compounds.** The fork point is roughly nine months old. Frigate is actively
developed; the gap includes security fixes the fork does not have.

## Merge strategy, if attempted

*(No merge has been attempted in this repo's history; this is a recommendation, not a record.)*

1. Re-measure the gap before deciding anything — it moves daily.
2. Merge into a scratch branch, never `main`.
3. Expect conflicts to cluster in `web/src` and to be overwhelmingly rename-vs-upstream-edit.
   Most resolve mechanically: take upstream's version, re-apply the type rename.
4. `frigate/extras/`, `analytics_*.py`, and `api/dashboard.py` should merge clean.
5. The core-patched files need manual review; all of them have upstream changes. The
   `always_full_frame` branch in `video.py` and its `DetectConfig` field are fork-specific and
   must be re-applied; `app.py`'s timeline cleanup is upstream's own code, so take upstream's
   version there.
6. Consider whether the rename is worth carrying. Reverting `Rasid360Config` → `FrigateConfig`
   in the type layer while keeping user-visible branding in translations and assets would
   permanently reduce merge cost.

## Branch topology

| Branch | Head | Notes |
|---|---|---|
| `main` | `a0dcd940` | 4 commits **ahead** of `dev` |
| `dev` | `2e072d59` | **`origin/HEAD` points here** |
| `feature/force-detection-without-motion` | `2e072d59` | Same commit as `dev` |

Note the trap: GitHub's default branch is `dev`, so a visitor to the repository sees the state
*before* the branding, dark theme, thumbnail fix, and playback-route work. All branches are
fully pushed and in sync with the remote; this is purely about which one is the front door.

Also outstanding: one stash (`stash@{0}: WIP on dev`) and an untracked 6.9 MB notebook,
`open_vocabulary_object_detection_with_qwen3_vl.ipynb`, in the repository root.

## Scope note

This wiki documents Rasid360's delta only. Upstream behaviour is documented at
[docs.frigate.video](https://docs.frigate.video) — see [SCHEMA](../SCHEMA.md).
