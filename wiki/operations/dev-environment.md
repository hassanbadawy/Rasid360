---
type: operations
status: current
sources: [run-dev.sh, stop-dev.sh, logs-dev.sh, container-runtime.sh, docker-compose.yml, .devcontainer]
updated: 2026-08-29
---

# Dev Environment

Local development runs everything inside the Frigate devcontainer. Four helper scripts wrap it,
and they work with **either podman or docker**.

## Container runtime

`container-runtime.sh` is sourced by every dev script and sets `CONTAINER_CMD`, `COMPOSE_CMD`,
and `CONTAINER_LABEL`. Detection order: an explicit `CONTAINER_RUNTIME` override, then podman,
then docker.

```bash
./run-dev.sh                          # auto-detect
CONTAINER_RUNTIME=docker ./run-dev.sh # force docker
```

It probes the **engine** (`podman info` / `docker info`), not just the binary. That matters: a
machine can carry a `docker-compose` binary with no docker at all, and `docker-compose version`
still succeeds there — so a `command -v` check would select a runtime that fails on the first
real command. This repo's own machine is in exactly that state.

With podman it prefers `podman-compose`, falling back to `podman compose`. Rootless podman
handles the compose file as-is, including the numeric `group_add` GIDs.

### podman-compose differences the scripts work around

**`ps` takes no service argument.** `docker compose ps devcontainer` is valid; `podman-compose ps
devcontainer` errors with `unrecognized arguments: devcontainer`. The scripts previously used
that to answer "is the container up?", which silently reported *not running* under podman. They
now call `compose_service_running` from `container-runtime.sh`, which queries the runtime
directly:

```bash
$CONTAINER_CMD ps --filter "name=${service}" --filter "status=running" --format '{{.Names}}'
```

`--filter name=` does substring matching, so it matches either provider's container naming
(`project_service_1` vs `project-service-1`).

**`exec -d` is silently ignored by podman-compose.** `podman-compose exec` *parses* `-d`, `-T`,
`-u` and `-w`, but `compose_exec_args()` never forwards `--detach` to `podman exec` (verified
against podman-compose 1.5.0). The exec therefore runs **attached** and blocks the caller
forever: `podman-compose exec -d -T devcontainer sleep 5` takes 5s, not 0s.

`container-runtime.sh` works around this with `compose_exec_detached <service> <cmd...>`, which
resolves the container name and calls the runtime's own `exec -d` — the same class of workaround
as `compose_service_running` above. Use it instead of `$COMPOSE_CMD exec -d`. The other flags
(`-T`, `-u`, `-w`) do work.

**Duplicate mount destinations are rejected.** `docker-compose.yml` mounted `/config` twice
(`./config` and `./data/frigate-config`). Docker silently lets the last definition win; podman
fails the container with `Error: /config: duplicate mount destination`. The vestigial mount was
removed 2026-08-25.

## Starting the frontend

`--docker-only` brings up the containers and the Frigate backend but **not** the Vite dev server,
because the default path ends in a blocking `logs -f`. Port 5173 is published either way, so
without Vite the browser gets `ERR_EMPTY_RESPONSE` — the port is bound, nothing is listening.

```bash
source ./container-runtime.sh
compose_exec_detached devcontainer bash -c "cd /workspace/frigate/web && npm run dev"
```

Or run `./run-dev.sh` with no flags once the image is built; it starts Vite and tails the logs.

**Podman setup on macOS:**

```bash
brew install podman podman-compose
podman machine init          # first time only
podman machine start
```

### Vite does not see host edits

File-change events do not cross the podman-machine boundary on macOS, so Vite's watcher never
fires and **HMR does not work**. Worse, a full page reload is not enough either: the dev server
keeps serving its cached transform, so an edited file looks like it never changed. Measured —
after editing `web/src/pages/Settings.tsx`, the container saw the new content while
`curl http://localhost:5173/src/pages/Settings.tsx` still returned the old module.

Restart Vite after editing frontend files:

```bash
podman exec <devcontainer> pkill -f vite
source ./container-runtime.sh
compose_exec_detached devcontainer bash -c "cd /workspace/frigate/web && npm run dev"
```

Backend edits need the Frigate processes restarted the same way; there is no reload there
either.

## Bring it up

```bash
./run-dev.sh
```

`run-dev.sh` (12 KB) performs, in order:

1. `check_requirements` — docker and `docker compose` present
2. `create_directories` — scaffold the `data/` tree
3. `check_docker_daemon`
4. `build_dev_container` — `docker compose build devcontainer`
5. `install_frontend_deps` — `npm install` in `/workspace/frigate/web`
6. `start_services` — `docker compose up -d`
7. `wait_for_services` — polls MQTT with `mosquitto_pub` until it answers
8. `start_frigate_backend` — starts **two** processes, each guarded by a `pgrep` check:
   - `python3 -m frigate`
   - `python3 -m frigate.extras.main`
9. frontend dev server on 5173

Both backend processes are launched with `compose_exec_detached`, so they are children of the
container's shell rather than supervised services — see
[Extras Service](../components/extras-service.md). They must **not** use `$COMPOSE_CMD exec -d`,
which hangs under podman-compose (see above).

### Do not run the test suite while the stack is up

`./run-tests.sh` starts a second container with the full dependency stack while nine camera
decoders are already running. On a default `podman machine` (5 CPUs, 7.45 GiB) that is enough to
take the VM down. Observed twice on 2026-08-28: the first time the machine died mid-run, the
second time `python3 -m frigate` was OOM-killed and nginx served `500` with only the extras
worker left alive.

The failure is confusing because the VM lies about it. `podman machine list` reports
**Currently running** while the API socket refuses connections, and `podman machine stop` prints
*stopped successfully* while leaving a live `krunkit` process behind. Recovery:

```bash
podman machine stop
pkill -f krunkit          # the stop above does not always kill it
podman machine start
./run-dev.sh --docker-only
```

Stop the stack before running the suite, or accept the risk. Commit first either way — nothing
in the working tree survives a VM you have to hard-kill.

### The UI Restart button

It works, and it takes the whole container down on the way — by design.

`restart_frigate()` (`frigate/util/services.py`) checks pid 1: if it is `s6-svscan` it sends it
SIGTERM, and s6 shuts every service down and exits. The devcontainer's entrypoint is `/init`,
so pid 1 *is* `s6-svscan` here just as in production, and production relies on the container's
restart policy to bring it straight back.

Three things used to make that a one-way door in dev, all now fixed:

- **No restart policy.** `docker-compose.yml` had none on any service, so a Restart stopped the
  stack permanently — container `Exited (143)`, which is SIGTERM, with a clean s6 shutdown in
  the logs. `devcontainer` now carries `restart: unless-stopped`.
- **Fake s6 services.** The devcontainer image replaced `frigate/run` and `frigate-extras/run`
  with heartbeat loops, on the assumption that the processes are started by hand. So even a
  restarted container came back with no Frigate in it. It now ships
  `docker/main/devcontainer_frigate_run` and `devcontainer_frigate_extras_run`, which run the
  real processes from the bind-mounted `/workspace/frigate`.
- **Vite was still hand-started.** Fixing the two above left a *half*-working restart, which is
  worse than one that plainly does nothing: the API came back on 5001 while the dev frontend on
  5173 stayed dead, because `run-dev.sh` starts Vite by hand and nothing brings a hand-started
  process back. `docker/main/devcontainer_s6/` adds a supervised `vite` service and its log
  pipeline, copied in during the devcontainer stage only — production serves the built assets
  through nginx and has no `/workspace/frigate`.

All three processes are supervised now, so `run-dev.sh` mostly reports that they are already
running rather than starting anything. Its Vite start carries the same `pgrep` guard the two
backend processes already had, so it does not fight the supervised one over port 5173.

Changing any of these files needs an image rebuild — `$COMPOSE_CMD build devcontainer` — and
then a recreate, not just a restart.

### /dev/shm sizing

`docker-compose.yml` sets `shm_size: "512mb"`. Frigate carves a shared-memory frame ring out of
`/dev/shm`, and undersizing it does not fail — it silently shortens the buffer.

At the shipped `256mb` this camera set (7 enabled, one of them 1080p) held **12 frames** against
the 50 Frigate wants — 2.4 seconds at 5 fps — and Frigate warned *"/dev/shm allocation (256 MB)
should be increased to at least 370 MB"*. 512mb gives 28 frames (~5.6 s), with room for another
camera or two.

| `shm_size` | frames buffered | ≈ seconds at 5 fps |
|---|---:|---:|
| 256mb | 12 | 2.4 |
| 370mb *(the warning's minimum)* | 20 | 4.0 |
| **512mb** *(shipped)* | **28** | **5.6** |
| 896mb | 50 *(capped)* | 10.0 |

Full 50 frames needs ~896mb, and tmpfs occupies what it holds — ~800 MB resident on a 7.45 GiB
machine that has already OOM-killed Frigate once. Not worth it here.

Recompute after changing cameras or resolutions:

```python
from frigate.util.services import calculate_shm_requirements   # returns min_shm, shm_frame_count
```

**`shm_size` only applies on container *recreation*.** A restart keeps the old tmpfs — use
`$COMPOSE_CMD down` then `./run-dev.sh --docker-only`.

## Ports

| Port | Service | Notes |
|---|---|---|
| 5173 | Vite frontend dev server | |
| 5001 → 5000 | Frigate UI **and** API | **Unauthenticated.** Host 5001 maps to container 5000 |
| 8971 | Frigate authenticated UI | |
| 8554 | RTSP (go2rtc) | |
| 1883 | Mosquitto MQTT | no-auth mode |
| 8123 | Home Assistant | added by this fork |

The 5000/5001 split matters: `frigate/extras/config.yml` points the extras worker at
`http://localhost:5000/api` because it runs **inside** the container. Host-side tools use 5001.

**Nothing binds host port 5000.** `run-dev.sh` used to advertise the production frontend at
`http://localhost:5000`; that URL never worked. On macOS the port belongs to Control Center's
AirPlay Receiver (`Server: AirTunes/…`), which answers `403 Forbidden` — so a wrong URL looked
like a broken frontend rather than a missing mapping. The built UI is served from **5001**.

WebRTC ports (8555 tcp/udp) and RTMP (1935) are present but commented out in
`docker-compose.yml`.

## Compose services

`docker-compose.yml` defines three: `devcontainer`, `mqtt` (`eclipse-mosquitto:2.0` in no-auth
mode), and `homeassistant` (`ghcr.io/home-assistant/home-assistant:stable`).

Fork-specific changes versus upstream:

- `container_name` removed from `devcontainer` and `mqtt`, allowing multiple instances
- `YOLO_MODELS` env var commented out
- Volume layout remapped to a `data/` tree:
  - `./data/frigate-config:/config`
  - `./data/frigate-storage:/media/frigate`
  - `./debug/media:/media/streams:ro`
- A commented `/dev/video0` device line for laptop webcam testing

Note `./config:/config` and `./data/frigate-config:/config` are **both** listed. The later
mount wins, so `data/frigate-config` is the effective config directory; the earlier line is
vestigial and should be removed to avoid confusion.

The file has no trailing newline and the `ports` block carries commented-out fragments —
cosmetic, but it makes diffs noisier than necessary.

## Logs

```bash
./logs-dev.sh              # all services
./logs-dev.sh <service>    # one service
./logs-dev.sh --help
```

Direct paths when the script is not enough:

| What | Where |
|---|---|
| Frigate | `/dev/shm/logs/frigate/current` inside the container |
| Extras worker | `/tmp/frigate_extras.log` (configurable in `frigate/extras/config.yml`) |
| Container | `docker compose logs devcontainer` |

The extras worker logs to both stdout and that file. Because it is started detached, its stdout
is discarded and **not** captured by `docker compose logs` — the file is the reliable source.
The same applies to `python3 -m frigate`: `/dev/shm/logs/frigate/current` belongs to the s6
service, which in the devcontainer is a placeholder that only prints
`The fake Frigate service is running...`, so it does **not** contain the manually-started
process's output.

## Tear down

```bash
./stop-dev.sh
```

## Running the tests

```bash
./run-tests.sh                                        # full suite
./run-tests.sh frigate.test.extras.test_dsl_rules     # one module
./run-tests.sh frigate.test.http_api.test_http_dashboard
```

Tests run inside a container because they need Frigate's full dependency stack — the import
chain reaches TensorFlow, so a plain host venv cannot load `frigate.api.fastapi_app`. The script
uses `ghcr.io/blakeblackshear/frigate:stable` (~4.6 GB, pulled once; override with
`TEST_IMAGE`).

**One environment wrinkle it handles for you.** The published image tracks upstream, whose
`peewee_migrate` is newer than the `1.13.*` this repo pins. Without pinning it back, every
migration-backed test errors with:

```
AttributeError: 'Migrator' object has no attribute 'change_columns'
```

That is an environment mismatch, not a test failure — it hits the pre-existing suite identically.
`run-tests.sh` installs the pin before running.

Current state: **286 tests** (2026-08-29) — 285 pass; `test_post_reviews_delete_many` is a
known intermittent isolation failure, see [Known Issues](../health/known-issues.md) #8d. It
passes when that module is run on its own.

**Give it time.** A full run is normally about a minute, but on a loaded machine — nine camera
decoders plus the test container — it has taken **twelve**. A run that looks hung usually is not;
`run-tests.sh` buffers its output, so nothing appears until it finishes.

The DSL tests alone need no container — they are pure logic over dicts:

```bash
python3 -m pytest frigate/test/extras/test_dsl_rules.py
```

## Verifying the violation path end to end

There is no automated test for the full MQTT-to-chart path. Manual sequence:

1. Confirm both processes are alive:
   ```bash
   docker compose exec devcontainer pgrep -af "frigate"
   ```
2. Watch the extras log for rule loading at startup:
   ```bash
   docker compose exec devcontainer tail -f /tmp/frigate_extras.log
   ```
3. Confirm MQTT is delivering events:
   ```bash
   docker compose exec mqtt mosquitto_sub -t 'frigate/events' -v
   ```
4. Trigger a configured violation. A firing rule logs `🚨 VIOLATION DETECTED` with camera,
   object, sub-label, severity, and zone path.
5. Confirm the event was created — it should appear in the UI with a `sub_label`.
6. Confirm evidence: `GET /api/events/{id}/evidence.jpg` should return a JPEG rather than a 404.
7. Charts will not update for up to **5 minutes**
   ([Analytics Scheduler](../components/analytics-scheduler.md)).

Step 6 is the most common failure — the 5-second snapshot polling window
([Violation Lifecycle](../concepts/violation-lifecycle.md) step 6).

## Related

- [Configuration](configuration.md)
- [Extras Service](../components/extras-service.md)
