---
type: component
status: current
sources: [frigate/extras/main.py, frigate/extras/config.py, frigate/extras/utils/mqtt_client.py, frigate/extras/utils/frigate_api.py, frigate/extras/actions/base_action.py, run-dev.sh, frigate/camera/activity_manager.py]
updated: 2026-08-29
---

# Extras Service

The out-of-process violation detection worker. Entry point: `python3 -m frigate.extras.main`.

Despite living inside the `frigate/` package, this is **not part of the Frigate application**.
It is a separate process that talks to Frigate only over MQTT and HTTP.

## Startup sequence

`EventDispatcher.__init__` (`frigate/extras/main.py`):

1. Configure logging — level and file from `config.yml`, defaulting to `/tmp/frigate_extras.log`
   plus stdout
2. Initialise the analytics database at `$ANALYTICS_DB_PATH` (default `/config/analytics.db`),
   creating tables with `safe=True`
3. Load `config.yml` via `ConfigLoader`
4. Construct `FrigateAPI` and run a health check — logs a warning and continues on failure
5. Construct `MQTTClient` and register `_dispatch_event` as the callback
6. Load enabled action handlers via `_load_actions`
7. Install `SIGINT` / `SIGTERM` handlers for graceful shutdown

## Action handler contract

`BaseAction` (`actions/base_action.py`) is the plugin ABC:

| Method | Purpose |
|---|---|
| `process_event(event_data)` | **abstract** — the handler's actual logic |
| `should_process_event(event_data)` | Camera filtering; overridable |
| `get_camera_filter()` | Cameras this handler cares about |
| `is_enabled()` | Config-driven on/off |
| `create_event(...)` | Convenience wrapper over `FrigateAPI.create_event` |
| `log_info` / `log_warning` / `log_error` / `log_debug` | Prefixed logging |

Two handlers ship:

- **`DSLViolationDetector`** — the general rule engine. This is the one that matters.
- **`WrongWayDetection`** — a hardcoded predecessor, superseded by the DSL's `zone_sequence`
  rule type. Retained but redundant.

Handlers are independent: each event is offered to every enabled handler in turn.

### Where rules come from

`DSLViolationDetector._resolve_camera_rules` prefers `cameras.<name>.violations` from the Frigate
config, fetched via `FrigateAPI.get_config()`. That is what the
[Rules Editor](web-rules-editor.md) writes and what config validation cross-checks.

`frigate/extras/config.yml` is the fallback for cameras with no rules in the Frigate config; the
worker logs a warning naming them. Rules fetched from the API are stripped of null values first
(`_strip_unset`) — pydantic serializes unset optionals as `null`, and the DSL rule classes read
config with `config.get(key, default)`, which returns the null rather than the default.
`monitor_duration: None` would then fail the `<= 0` check with a TypeError.

## MQTT layer

`MQTTClient` (`utils/mqtt_client.py`) wraps paho-mqtt with callback-API-v2 signatures
(`_on_connect(client, userdata, flags, reason_code, properties)`), subscribes to
`frigate/events`, and parses each payload as JSON before invoking the registered callback.

**A second class of topic** was added on 2026-08-29 for `zone_occupancy` rules. Frigate
republishes a zone's object count on every change to `frigate/<zone>/<label>`, and the payload is
a **bare integer, not event JSON** — so `_on_message` routes anything that is not
`frigate/events` to a separate raw callback instead of parsing it as an event.

`EventDispatcher` works out which zones any rule actually watches
(`_zones_watched_for_occupancy`), subscribes to only those, and turns each count into a
`{"type": "zone_count", ...}` event carrying the camera. The camera has to be attached here
because the topic does not contain one — which is also why a zone counted this way must have a
name unique across cameras, enforced at config parse time.

Rules that read it are described in
[DSL Rule Language](../concepts/dsl-rule-language.md) § `zone_occupancy`.

Events arrive with `before` / `after` state dicts; rules read from `after`.

## Frigate API layer

`FrigateAPI` (`utils/frigate_api.py`) wraps the REST API with a 5-second timeout:

| Method | Endpoint |
|---|---|
| `create_event` | `POST /events/{camera}/{label}/create` |
| `end_event` | ends a manual event |
| `get_event` | `GET /events/{id}` |
| `get_stats` / `get_config` | diagnostics |
| `get_tracked_objects(camera)` | current objects, for multi-object evidence drawing |
| `health_check` | startup probe |

The default base URL differs between files — `FrigateAPI.__init__` defaults to
`http://localhost:5001/api` while `config.yml` sets `http://localhost:5000/api`. The config wins
in practice. Port 5000 is Frigate's unauthenticated internal API *inside* the container; 5001 is
the host-side mapping in `docker-compose.yml`. Getting this wrong is a common cause of
"violations detected but no events created".

## How it is launched

**Supervised by s6 as of 2026-08-24.** The service is defined at
`docker/main/rootfs/etc/s6-overlay/s6-rc.d/frigate-extras/`, following the same shape as the
`frigate` and `go2rtc` services:

| File | Value |
|---|---|
| `type` | `longrun` |
| `run` | `exec python3 -u -m frigate.extras.main` from `/opt/frigate` |
| `finish` | logs the exit code |
| `dependencies.d/frigate` | starts after Frigate |
| `producer-for` | `frigate-extras-log` |
| `timeout-kill` | `30000` |

Paired with a `frigate-extras-log` service writing to `/dev/shm/logs/frigate-extras`, registered
in `user/contents.d/frigate-extras-pipeline`, with the log directory created by `log-prepare`.

Two deliberate differences from the `frigate` service:

**It does not call `s6-svc -O`.** The frigate service tells s6 not to restart it; this one wants
restarts, since that is the entire point — a dead worker previously stopped violation detection
silently. The one exception is a missing `config.yml`, where `run` disables restart and logs a
single clear message rather than restart-looping.

**Its `finish` does not halt the container.** The worker dying should not take Frigate down.

On the **devcontainer** the run script is `docker/main/devcontainer_frigate_extras_run`, which
differs from production only in reading the bind-mounted source at `/workspace/frigate` instead
of the baked `/opt/frigate`. It is supervised the same way.

It used to be `fake_frigate_extras_run`, a heartbeat loop, so that `run-dev.sh` kept control of
the worker. That was changed on 2026-08-29: with nothing supervising it, a container restart —
which is exactly what the UI's Restart button causes — came back with Frigate running and
violation detection silently dead, reintroducing the failure mode below. `run-dev.sh` still
works: its `pgrep` guard sees the supervised process and skips its manual start.

```bash
# still available for restarting the worker alone while iterating on rules
compose_exec_detached devcontainer bash -c "cd /workspace/frigate && python3 -m frigate.extras.main"
```

### The failure mode this closed

Before this, the worker was started only by `run-dev.sh` with a detached `exec`. If it
died, Frigate kept running perfectly — recording, detecting, serving the UI — while violation
detection stopped with no error anywhere. The symptom, no new violations, is indistinguishable
from a quiet period.

Empty `frigate-extras/` and `frigate-extras-log/` scaffolding directories had existed in the
tree, containing only empty `dependencies.d/` subdirectories, so git never tracked them.

## State is in-memory and volatile

`StateTracker` state — zone sequences, sustained-condition start times, detection counters,
stored frame times — lives in process memory only. A restart clears everything, so any violation
mid-accumulation is lost. For a rule with `monitor_duration: 30`, a restart discards up to 30
seconds of accumulated evidence per tracked object.

## Related

- [DSL Engine](dsl-engine.md) — what the detector calls into
- [Violation Lifecycle](../concepts/violation-lifecycle.md) — the full path
- [Dev Environment](../operations/dev-environment.md) — running it locally
