---
type: operations
status: current
sources: [data/frigate-config/config.yml, frigate/camera/activity_manager.py, frigate/extras/config.yml, frigate/extras/config.py, docker-compose.yml, .gitignore, frigate/api/app.py, frigate/util/builtin.py, web/src/hooks/use-stats.ts, web/src/types/graph.ts, frigate/config/config.py, frigate/config/camera/objects.py]
updated: 2026-09-06
---

# Configuration

There are **two config files**, but since 2026-08-25 violation rules live in the Frigate config
rather than the worker's:

| File | Read by | Purpose | In git? |
|---|---|---|---|
| `data/frigate-config/config.yml` | Frigate **and** the worker | cameras, zones, detectors, recording, LPR, **violation rules** | **yes** (tracked) |
| `frigate/extras/config.yml` | Extras worker | MQTT, API URL, logging; violation rules only as a fallback | **yes** |

## Frigate config

Mounted at `/config/config.yml`. Standard upstream schema — see
[docs.frigate.video](https://docs.frigate.video). This deployment configures cameras including
`Road01`, `EmbassyGate`, and `LPR_Camera`, with zones, object filters, and licence-plate
recognition (`min_area: 1500`).

**Zones defined here are the vocabulary the DSL rules draw on.** A `zone_sequence` rule naming
`zone01` requires a zone called `zone01` on that camera in *this* file. Nothing validates the
cross-reference; a mismatch produces a rule that never fires and never errors
([DSL Engine](../components/dsl-engine.md)).

For `speed_limit` rules, the zone additionally needs a `distances` field, or Frigate's speed
estimation yields nothing.

### Recording

The `record:` block is edited from `Settings → Cameras → Recording` as well as by hand. Its
semantics are counter-intuitive enough to be worth stating here: `enabled` runs the capture
pipeline, it does **not** mean footage is stored — the retention windows decide that, and
`enabled: false` makes violation clips impossible for that camera. Full mechanism in
[Recording Retention](../components/recording-retention.md).

Global values are merged into every camera; anything set under `cameras.<name>.record`
overrides the global for that camera only.

### Review items are the storage control

This deployment runs with **ordinary review items off**:

```yaml
review:
  alerts:     { enabled: false }
  detections: { enabled: false }
```

That is not a display preference. A review item pins every recording segment it overlaps, and
on continuously busy cameras an ordinary review segment never closes — so leaving these on
retained ~220 GB/day, 93% of it footage no violation ever referenced. Violations are exempt
from both switches, so this leaves violation evidence intact. Turning either back on is
supported; understand the cost first —
[Recording Retention](../components/recording-retention.md).

`record.expire_interval` is `10` (default 60) for the same reason: segments are written to
permanent storage first and deleted at the next expiry pass, so the interval bounds the churn
held on disk.

### Editing config from the UI

Three endpoints, with different notions of what "the config" is:

| Endpoint | Serves | Notes |
|---|---|---|
| `GET /config` | the **running, merged** config | does not reflect `config/set` writes until restart |
| `GET /config/file` | the **file**, parsed | what settings forms should read-modify-write |
| `GET /config/raw` | the file, as text | backs the raw YAML editor |

`PUT /config/set` writes the file with ruamel round-trip (comments survive), re-parses to
validate, and rolls back on failure. Two sharp edges worth knowing:

- An **empty-string value means "delete this key"**, which is how a per-camera override is
  removed. No config field can therefore be set to an empty string through this API.
- Lists are replaced wholesale, never patched — which is why read-modify-write against the
  stale `/config` view loses data, and why `/config/file` exists.

`requires_restart: 0` swaps the API process's config; `update_topic` / `update_topics` publish
the change to the worker processes that subscribe to it, which is what makes a save apply
without a restart.

### Detection cost, and what drives it

Every camera shares one detector process. This deployment runs the **`cpu` detector** —
software inference at **~40 ms per call** — so detection cost is simply
`detections/sec × 40 ms`, and a single camera can eat a core.

The number that matters is `detection_fps` in `GET /api/stats`, not `camera_fps`. It counts
**inference calls**, and one frame can need several: motion produces regions, and each region is
its own call. Divide the two for regions per frame.

Worked example — EmbassyGate, 2026-08-29, which was warning *"high detect CPU usage (45%)"*:

| | Before | After |
|---|---:|---:|
| `camera_fps` | 10.0 | 5.1 |
| `detection_fps` | 27.2 | 9.7 |
| regions per frame | 2.86 | 2.06 |
| camera detect CPU | 47.3% | **20.9%** |

Two changes, compounding to 64% fewer inferences:

- **`detect.fps: 10 → 5`.** Most of the gain. 10 fps is double what the other cameras use and
  buys nothing at a gate.
- **`motion.threshold: 25 → 40`, `contour_area: 10 → 40`.** The originals are near Frigate's
  defaults and far too sensitive for a real scene: noise, shadows and light flicker each became
  a motion blob, and every blob is an inference call.

**`detect.fps` does not apply live.** Changing it through `config/set` leaves `camera_fps`
unchanged until a restart — it is baked into the frame pipeline. Motion settings do apply live.
If a tuning change appears to do nothing, this is why.

Still available on that camera: it has **no motion mask**, so the whole frame is live — masking
the irrelevant areas would push regions-per-frame toward 1.

The structural fix is hardware: a Coral TPU runs the same inference in ~8 ms rather than 40.

### The two CPU warnings are different problems

The UI raises them from separate numbers, at separate thresholds
(`web/src/types/graph.ts`, checked in `web/src/hooks/use-stats.ts`):

| Warning | Number | Fires at |
|---|---|---:|
| *"high detect CPU usage"* | `cpu_usages[camera.pid].cpu_average` — the `frigate.process:<cam>` worker, i.e. inference | ≥ **40%** |
| *"high FFmpeg CPU usage"* | `cpu_usages[camera.ffmpeg_pid].cpu_average` — the decoder | ≥ **20%** |

Everything above this section is about the first. The second has entirely different causes, and
the fixes for one do nothing for the other.

### FFmpeg cost is decode, and `detect.width/height` is not the lever

EmbassyGate warned *"high FFmpeg CPU usage (31%)"* on 2026-09-06. The obvious move —
`detect.width: 1280` / `detect.height: 720`, so ffmpeg pipes a smaller frame — **does not
work**, and it is worth knowing why before reaching for it.

Frigate's per-camera ffmpeg does the resize *after* decoding, in the same process:

```
-i <source> … -vf fps=5,scale=1280:720 -f rawvideo -pix_fmt yuv420p pipe:
```

Every full-size frame is decoded before swscale can shrink it. Measured over 30 s of stream,
flat out, inside the devcontainer:

| Work | CPU |
|---|---:|
| decode alone, EmbassyGate's 1080p **High**-profile clip | **30.5%** of a core |
| decode + `fps=5` + scale to 720p + rawvideo pipe + segment muxing | adds **< 1%** |

Decode is essentially the whole bill. Setting the detect resolution measured **28.7% → 31.6%**
— slightly worse, since downscaling is real work that the identity path skipped. It does reduce
the *detect* process's frame handling, so it is not useless; it is just not an ffmpeg lever.

What actually differs between cameras is the **source encode**, not the resolution. Road01 and
EmbassyGate are both 1080p, yet Road01 decodes for half the cost, because its clip is
Constrained Baseline (CAVLC, no B-frames) while EmbassyGate's was High profile (CABAC).
Measured decode cost per candidate:

| Source | Decode |
|---|---:|
| 1080p High *(was)* | 30.5% |
| 1080p Constrained Baseline | 19.7% — on top of the 20% threshold, would flap |
| **720p Constrained Baseline** *(now)* | **9.2%** |

Result after re-encoding the fixture: ffmpeg **28.7% → 7.3%**, whole-camera total **50.0% →
21.6%**, and the banner returns to *System is healthy*.

In production the right answer is a **detect substream** — a second input with `roles: [detect]`
at low resolution, leaving the 1080p input as `roles: [record]` and `-c:v copy`, never decoded.
That does not work for these file fixtures: the clip is 5 s on `-stream_loop -1`, so two
independent reads drift out of phase and recorded evidence stops matching the detections.
Hardware acceleration, the other production answer, is unavailable — the podman VM on macOS has
no hwaccel, and Frigate says so at startup.

### `min_area` is measured in detect-frame pixels

A consequence of changing detect resolution that is easy to miss. `min_area` / `max_area` are
pixel areas of the **detect frame** (`is_object_filtered`, `frigate/util/object.py`), so the
same object covers 2.25× fewer of them at 720p than at 1080p. EmbassyGate's `person.min_area:
5000` would have filtered out every person on the camera.

Any value below 1 is read as a fraction of the frame and converted at config load
(`convert_area_to_pixels`, `frigate/config/config.py`), which makes the filter
resolution-independent. EmbassyGate's are now written that way:

```yaml
person:
  min_area: 0.0024  # ~0.24% of frame, was 5000 px at 1080p
  max_area: 0.0965
```

`motion.contour_area` needs no such care: the motion detector resizes every frame to
`motion.frame_height` (default 100) first, so it is already resolution-independent.

Zone and mask coordinates are stored normalised (`0.101,0.406,…`), so they survive a resolution
change untouched.

### What lives in the global block, and what overrides it

Camera config inherits from the top-level blocks, and since 2026-09-06 the settings that were
identical on every camera live there instead of being restated nine times:

```yaml
detect:
  fps: 5
  width: 1280
  height: 720

motion:
  threshold: 40
  contour_area: 40
  improve_contrast: true
```

`detect.width/height` is the one that matters most, because **the default is not a default**: a
camera that omits them detects at its *source* resolution. That is exactly how EmbassyGate came
to run detect at 1920×1080 while all six Road cameras ran 720p — nothing was misconfigured, its
`detect` block simply had no `width`/`height` and the others did. Putting them in the global
block makes 720p what a new camera gets for free.

The deliberate overrides that remain:

| Camera | Overrides | Why |
|---|---|---|
| `LPR_Camera` | `detect: 640x480`, `motion: 15/5` | plates on stopped vehicles need sensitivity |
| `face_camera` | `detect: 640x480` | |
| `Road01` | `motion: 80/50` + mask | busy street, heavy shadow motion |
| `Road03/04/05` | motion `mask` only | now inherit 40/40 thresholds |
| `EmbassyGate` | `min_initialized`, `max_disappeared`, `stationary`, fractional filters | person places a bag and stands still |

Hoisting the motion numbers moved five disabled cameras (`Road02`–`Road06`) and `face_camera`
from Frigate's too-sensitive defaults (25/10, 30/10) onto 40/40. Every other effective value —
detect resolution, fps, tracked objects, filters, masks, zones — was verified byte-identical
before and after via `GET /api/config`.

### Decode cost is a property of the source, not the config

Since decode is the whole ffmpeg bill and no config setting changes it, the only thing that
predicts a camera's ffmpeg CPU is what its stream *is*. For the fixture clips:

| Camera | Fixture | Encode | Cost if enabled |
|---|---|---|---|
| Road01 | `wrongWayCar02.mp4` | 1080p Constrained Baseline @30 | ~15%, fine |
| EmbassyGate | `embassey_bag_720p_baseline.mp4` | 720p Constrained Baseline @24 | ~9%, fine |
| Road03 | `traffic01.mp4` | 640×360 Main @30 | cheap |
| Road06 | `CarBrokeDown01.mp4` | 640×302 Main @30 | cheap |
| Road05 | `wrongWayCar03.mp4` | 720p **High** @24 | moderate |
| `face_camera` | `construction/02.mp4` | 720p **High** @30 | moderate |
| Road02 | `falldown01.mp4` | 1080p **High** @24 | would warn |
| Road04 | `wrongWayCar01.mp4` | 1080p **High** @**60** | would warn, worst of the set |
| `LPR_Camera` | `lic-plate-02.mp4` | **3840×2160 High** @30 | 4K — far over |

Those five are disabled today, so they cost nothing. Enabling one means re-encoding its clip
the way EmbassyGate's was:

```bash
ffmpeg -i in.mp4 -vf scale=1280:720 -c:v libx264 -profile:v baseline -level 3.1 \
  -preset slow -crf 21 -g 48 -c:a copy -movflags +faststart out.mp4
```

Constrained Baseline is the load-bearing part — CAVLC instead of CABAC, no B-frames — and it is
worth roughly as much as halving the resolution.

### Rasid360-specific camera option

`detect.always_full_frame` (default `false`) runs detection on the whole frame when motion
detection finds no regions, for targets too stationary to trigger motion. Enabled on
`LPR_Camera`:

```yaml
detect:
  enabled: true
  always_full_frame: true
```

It costs a detection pass on every frame for that camera, so enable it per camera rather than
broadly. Added 2026-08-24, replacing a hardcoded camera-name check in `frigate/video.py` — see
[Core Pipeline Patches](../components/core-pipeline-patches.md).

## Extras config

`frigate/extras/config.yml` (239 lines), loaded by `ConfigLoader` (`frigate/extras/config.py`).
Three sections:

```yaml
mqtt:
  host: mqtt              # compose service name — resolves inside the container only
  port: 1883
  client_id: frigate_extras

frigate:
  api_url: http://localhost:5000/api   # container-internal port

actions:
  dsl_violations:
    enabled: true
    violation_templates: { ... }
    cameras: { ... }

logging:
  level: DEBUG
  file: /tmp/frigate_extras.log
```

Both defaults assume **the worker runs inside the devcontainer**. `mqtt` as a hostname only
resolves on the compose network, and port 5000 is container-internal (5001 from the host). A
worker run outside the container needs both changed.

Rule authoring reference: [DSL Rule Language](../concepts/dsl-rule-language.md).

`logging.level` ships as `DEBUG`, which is verbose for a production deployment.

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `ANALYTICS_DB_PATH` | `/config/analytics.db` | Extras worker only |

Note the asymmetry: the Frigate process derives the analytics path from
`config.database.path` (replacing `frigate.db` with `analytics.db`), while the worker reads this
env var. They normally agree, but nothing enforces it — see
[Analytics Database](../components/analytics-database.md).

## What is and is not in git

`.gitignore` contains `data/`, so runtime state stays local:

- `analytics.db`, `backup.db`, `*.db`
- `.jwt_secret`, `.exports`, `.vacuum`, `.search_stats.json`
- `backup_config.yaml`, `config-lpr.yml`

**But two files under `data/` are tracked anyway** — `data/frigate-config/config.yml` and
`data/frigate-config/go2rtc_homekit.yml` — because they were committed *before* `data/` was
added to `.gitignore`, and gitignore does not retroactively untrack.

The practical consequence: edits to those two files show up as git changes, while every other
file beside them is invisible. That asymmetry is easy to trip over.

Checked for credential exposure — **there is none**. The tracked config contains no `rtsp://`
URLs, usernames, or passwords.

## The tracked config is a test-fixture config

Every camera in `data/frigate-config/config.yml` reads from a **looped local MP4**, not a live
stream:

```yaml
ffmpeg:
  inputs:
    - path: /media/streams/streams/street/wrongWayCar02.mp4
      input_args: -re -stream_loop -1 -fflags +genpts
```

Fixtures include `wrongWayCar01-03.mp4`, `falldown01.mp4`, and `traffic01.mp4` — one clip per
violation type the DSL is meant to catch. `-re -stream_loop -1` replays them in real time,
forever, so the system behaves as if fed by continuous cameras.

Two consequences worth internalising:

**The system has been exercised against recorded video, not live cameras.** *(inferred from the
config, which is the only camera configuration in the repository.)* This contextualises a lot of
what is otherwise puzzling: the `cooldown: 600` values explicitly commented as testing figures,
the `DEVELOPMENT HACK` in `video.py`, and the absence of any handling for stream disconnects or
camera restarts. Deterministic looping footage also means the same violation recurs on a fixed
period, which is ideal for development and misleading for capacity planning.

**A fresh clone cannot run it.** `.gitignore` excludes `*.mp4` and `debug`, and the fixtures are
mounted from `./debug/media`. So the tracked config references video files that are not in the
repository and are not obtainable from it. Anyone setting this up from scratch must supply their
own footage at those paths, or repoint the cameras. This is the single biggest onboarding
obstacle in the project, and nothing documents it.

## Related

- [Dev Environment](dev-environment.md)
- [DSL Rule Language](../concepts/dsl-rule-language.md)
