---
type: operations
status: current
sources: [data/frigate-config/config.yml, frigate/extras/config.yml, frigate/extras/config.py, docker-compose.yml, .gitignore, frigate/api/app.py, frigate/util/builtin.py]
updated: 2026-08-28
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
