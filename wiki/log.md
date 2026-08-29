# Wiki Log

Append-only, newest at the bottom. Format: `## [YYYY-MM-DD] <op> | <title>`

```bash
grep "^## \[" wiki/log.md | tail -5
```

---

## [2026-08-24] ingest | Initial wiki construction

**Scope:** whole repository, as of `main` @ `a0dcd940`.

Built the wiki from scratch following the
[LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), with the
codebase as the raw source layer. Created [SCHEMA.md](SCHEMA.md), 17 content pages, an index,
and this log.

**Method:** read the full fork diff (`git diff de066d00..HEAD`), then traced the violation path
end to end through the source rather than summarising file-by-file. Derived structure from the
system's actual seams — detection, rules, analytics, API, frontend — not from the directory tree.

**Findings surfaced during writing** (documented in [Known Issues](health/known-issues.md)):

- Confirmed the `get_allowed_cameras_for_filter` arity/await bug at 8 sites in `dashboard.py`,
  and traced why the obvious fix converts an outage into a silent cross-camera data leak
- **New:** face-recognition and LPR results are counted as violations, because every aggregation
  filters on `sub_label IS NOT NULL` while upstream writes `sub_label` for enrichment results.
  `source_type="dsl_violation_detector"` already exists and would disambiguate
- **New:** ticket state is split across `Event.data` and `AnalyticsObservation`, and
  `aggregate_ticket_status` reads only the former — observations-API updates never reach a chart
- **New:** `ticket_updated_by` is hardcoded to `"admin"`, so the audit trail records nothing
- **New:** all cameras read looped MP4 fixtures; the system has been exercised against recorded
  video only, and a fresh clone cannot run it because the fixtures are gitignored
- **New:** `analytics.db` runs without WAL mode with three concurrent writers
- Verified there are **no credentials** in the tracked `data/frigate-config/config.yml`

**Corrections made mid-pass:** initially wrote that `aggregate_ticket_status` reads
`AnalyticsObservation.status` — it reads `Event.data["ticket_status"]`. Also upgraded the
face/LPR `sub_label` claim from inferred to verified after confirming
`EventMetadataTypeEnum.sub_label` producers in `frigate/data_processing/real_time/face.py`.

**Not covered:** upstream Frigate behaviour (out of scope per SCHEMA), the `docs/` Docusaurus
site, `notebooks/`, and the untracked Qwen3-VL notebook.

**Next:** first lint pass should re-check every `sources:` list against `git log` once any of
the [Known Issues](health/known-issues.md) items are fixed.

---

## [2026-08-24] fix | Resolve known issues 1-8

**Scope:** backend, docker supervision, frontend hook, tests. 12 files modified, 9 added.

Worked the [Known Issues](health/known-issues.md) list in the recommended order. Items 1-8 fixed,
9-15 left open and re-prioritised.

**Code changes:**

- **Access control** — added `resolve_camera_filter` to `frigate/api/dashboard.py`; all ten
  endpoints are now `async def` and route through it. Camera filters apply unconditionally, so
  an empty allowed-list fails closed.
- **Violation definition** — new `frigate/violations.py` with `violation_events_clause()`,
  requiring a detector marker in `Event.data["type"]` alongside `sub_label`. Applied in
  `analytics_scheduler.py`, `api/dashboard.py`, `api/event.py`.
- **Supervision** — completed the `frigate-extras` / `frigate-extras-log` s6 services, registered
  the pipeline, extended `log-prepare`, and added `fake_frigate_extras_run` so the devcontainer
  keeps its manual workflow.
- **Ticket state** — bidirectional best-effort sync between `Event.data` and
  `AnalyticsObservation`; real attribution via `Depends(get_current_user)`.
- **Dev hacks** — `detect.always_full_frame` config option replaces the hardcoded `"LPR_Camera"`
  check; timeline cleanup re-enabled behind an `OperationalError` guard.
- **Analytics** — WAL pragmas; queries materialised once; ticket status grouped in SQL; the
  extras worker now shares `init_analytics_db`.
- **Frontend** — `use-violations.ts` reads a new `GET /events/violation_types` instead of
  scanning 1,000 client-side events.

**Tests added:** `frigate/test/extras/test_dsl_rules.py` (17, passing) and
`frigate/test/http_api/test_http_dashboard.py`.

**Corrections to earlier wiki claims:**

- "No s6 service definition exists" was **wrong** — empty scaffolding directories were present.
  The original grep used `--include` filters that skipped extension-less s6 files. The
  conclusion (no working supervision) held; the detail did not.
- "A distinct-`sub_label` endpoint already exists in `frigate/api/event.py`" was **imprecise** —
  it was a query embedded in `/events/explore`, not a standalone endpoint. One was added.

**Caught while fixing:**

- `camera_name` is not in scope in `process_frames`; the replacement log line would have raised
  `NameError` on every firing, since f-strings evaluate eagerly. Uses `camera_config.name`.
- FastAPI matches routes in registration order, so `/events/violation_types` had to be declared
  **above** `/events/{event_id}` or it would never match.
- `after=0` is falsy, so `if cameras or after or before:` silently takes the unfiltered branch —
  affected a test being written, and is a latent sharp edge in the endpoints themselves.

**Verification:** DSL suite passes (17/17). The violation clause and fail-closed semantics were
verified against real SQLite in a scratch harness — the old clause matched 7 of 7 seeded rows
where only 4 were violations, and the old `if camera_list:` guard returned every row on an empty
allowed-list. All modified Python parses; all new shell scripts pass `bash -n`.

**Not verified:** the HTTP tests were **not executed** — the import chain reaches TensorFlow and
the container was unavailable (no Docker on PATH). Treat their first run as outstanding work.

**Also:** added the `upstream` git remote and measured the gap for the first time — 1,056 commits
behind, 511 overlapping files.

---

## [2026-08-24] fix | Podman support in dev scripts; test suite verified

**Scope:** dev tooling. Added `container-runtime.sh` and `run-tests.sh`; adapted `run-dev.sh`,
`stop-dev.sh`, `logs-dev.sh`.

The machine has podman, not docker, so the dev scripts could not run at all — every one
hardcoded `docker` / `docker compose`.

**Changes:**

- **`container-runtime.sh`** (new) — sourced by all dev scripts; sets `CONTAINER_CMD`,
  `COMPOSE_CMD`, `CONTAINER_LABEL`. Honours a `CONTAINER_RUNTIME` override, else prefers podman,
  else docker.
- **`run-dev.sh` / `stop-dev.sh` / `logs-dev.sh`** — all runtime calls now go through those
  variables. The duplicated `docker-compose`-vs-`docker compose` branches collapsed into one
  `$COMPOSE_CMD`.
- **`run-tests.sh`** (new) — runs the suite in a container, with an optional module argument.

**Design note.** Detection probes the *engine*, not the binary. This machine has a
`docker-compose` binary on PATH with no docker installed, and `docker-compose version` still
exits 0 — so the obvious `command -v docker-compose` check selects a runtime that fails on the
first real command. The shim runs `podman info` / `docker info` instead.

**Verified:** rootless podman accepts the compose file unchanged, including the numeric
`group_add` GIDs (tested with `podman run --group-add`), so `docker-compose.yml` needed no edits.
`podman-compose` supports the `exec -d`/`-T`/`-u`/`-w` flags the dev scripts use. Detection, both
override paths, and the bogus-value error path all exercised.

**Two further issues surfaced when actually running `run-dev.sh`:**

- **`podman-compose ps` rejects a service argument** — `docker compose ps devcontainer` is valid,
  podman-compose errors with `unrecognized arguments`. Three "is the container up?" checks were
  silently answering *not running*. Replaced with `compose_service_running`, which queries the
  runtime directly via `ps --filter name= --filter status=running`.
- **`--docker-only` never started anything** — a pre-existing bug unrelated to podman. The branch
  skipped `start_services` entirely and then printed "Docker services started in background". It
  now starts the services and backend, skipping only the frontend and the blocking log tail.

**Test suite now verified — 211 tests passing.** This closes the gap left open in the previous
entry: the 6 dashboard tests and 17 DSL tests had been written but never executed.
`test_recognized_plates_are_not_violations` and `test_no_camera_access_returns_nothing` now prove
fixes 1 and 2 through the real API stack rather than a scratch harness.

**Environment wrinkle found and handled:** the published image tracks upstream, whose
`peewee_migrate` is newer than this repo's `1.13.*` pin, so every migration-backed test errored
with `'Migrator' object has no attribute 'change_columns'`. Diagnosed as environmental by running
the *pre-existing* `test_http_event.py`, which failed identically; it passes once the pin is
restored. `run-tests.sh` applies the pin automatically.

---

## [2026-08-25] ingest | First live run of the stack

**Scope:** built the devcontainer image and ran the full environment under podman for the first
time. Every fix from the previous passes is now verified against a running system rather than
tests alone.

**Build:** all 16 Dockerfile stages succeeded on arm64, ~50 minutes, tagged
`localhost/rasid360_devcontainer:latest`. Upstream's install scripts detect `arm64` and fetch
`aarch64` artifacts correctly, so the architecture concern raised earlier was unfounded.

**Verified live:**

- **All ten dashboard endpoints return 200**, including `camera/fps` and `camera/offline`, which
  returned 500 unconditionally before the access-control fix.
- The violation clause appears in the live SQL:
  `WHERE sub_label IS NOT NULL AND CAST(json_extract(data,'$.type') AS text) IN
  ('dsl_violation_detector','wrong_way_detector','custom_action')`.
- `DELETE FROM timeline WHERE source_id NOT IN (SELECT id FROM event)` ran without
  `OperationalError`, confirming the "table not created by migrations" justification for
  disabling it was stale.
- Analytics aggregation completed in 0.12s; 386 historical violations aggregated for 2025.
- Cameras process video normally — `Road02` detecting `person` at 0.82. The MP4 fixtures are
  present on this machine, so the "fresh clone cannot run it" caveat applies to a new clone only.

**Bug found by running it:** the embeddings process crashed on every boot with
`AttributeError: 'ClassificationConfig' object has no attribute 'bird'` — an incomplete
`bird` → `object` rename that had left two live attribute accesses stale while updating only log
strings. Fixed; see [Known Issues](health/known-issues.md) 8b. This had silently disabled
semantic search, face recognition, and LPR.

**Two more podman gaps closed:** duplicate `/config` mount destination (docker last-wins, podman
rejects) and `podman-compose ps <service>` rejecting the service argument. Also fixed a
runtime-independent bug where `--docker-only` skipped `start_services` entirely and then reported
success.

**Not yet done:** Frigate needs a restart for the `bird` → `object` fix to take effect — the
running process still has the crashed embeddings child.

---

## [2026-08-25] ingest | Violation rules move into the Frigate config, with a UI

**Scope:** new config schema, cross-validation, worker rule source, a Settings page, migration of
all 11 rules. Verified end-to-end in a browser.

Hand-writing the rule YAML was error-prone, and the errors were silent -- a misspelled zone name
produced a rule that loaded fine and never fired. A UI that only generated YAML would have fixed
the typing but not the failure mode, so both were addressed together.

**The decision.** Rules moved from `frigate/extras/config.yml` into
`cameras.<name>.violations` in the Frigate config. That one change solved four problems at once:
the UI reuses the existing `config/set` write path; `config_set` already validates and rolls back
on failure; a rule and its zones are finally in the same object so they can be cross-checked; and
the worker already had `FrigateAPI.get_config()`.

**Built:**

- `frigate/config/camera/violation.py` -- `ViolationRuleConfig`, required-field checks per rule
  type, plus `referenced_zones()` / `referenced_labels()`
- `verify_violation_rules` in `frigate/config/config.py`, alongside the existing
  `verify_*` helpers so it runs after the global-to-camera merge
- `GET /api/config/violations` -- reads rules from the config *file*
- `DSLViolationDetector._resolve_camera_rules` -- prefers the Frigate config, falls back to the
  extras YAML with a warning
- `RulesView` + `RuleEditDialog` -- see [Rules Editor](components/web-rules-editor.md)
- 13 config tests, 4 speed tests, 11 browser checks

**Why a form is enough.** All 11 shipped rules are either `zone_sequence`, `fall_down`, or
`in_zone(X) AND (detected(a) OR detected(b))`. The editor asks for a zone and a set of objects
and builds the condition itself; free-text DSL stays behind an Advanced toggle.

**Bugs found by doing the migration:**

- **`speed_threshold` was accepted and silently ignored.** Rather than codify that in the schema,
  it is now implemented in `SustainedConditionRule` -- Frigate already puts
  `average_estimated_speed` on the event.
- **`Road05` had two rules both named `wrongway`.** Cooldowns key on `camera:rule_name`, so at
  `cooldown: 600` the right-lane rule suppressed the left-lane rule for ten minutes. Caught by
  the new duplicate-name check; renamed to `wrongway_right` / `wrongway_left`.
- **The editor would have silently dropped rules.** `/api/config` serves the *in-memory* config,
  which does not reflect `config/set` writes until restart. Saving a camera's whole list from
  that stale copy would discard anything saved since the last restart -- hence the file-truth
  endpoint.

**Corrections to earlier notes:** sustained conditions are timed on the **wall clock**
(`datetime.now()`), not the event's `frame_time`; tests that advance `frame_time` do not advance
the timer.

**Verified live:** config parses with all 11 rules cross-validated; a deliberately bad rule is
rejected and the file left byte-identical; the worker loads all 11 from the Frigate config; and
`red_zone_intrusion` fired on EmbassyGate from a rule the UI can now edit.

**Left alone:** `test_post_reviews_delete_many` fails when run after another http_api suite.
Confirmed pre-existing and unrelated -- `test_http_media` reproduces it with none of this fork's
code. See [Known Issues](health/known-issues.md) 8d.

## [2026-08-26] fix | Dev scripts: podman-compose `exec -d` is a no-op, and `stop-dev.sh` killed gvproxy

`./run-dev.sh` and `./stop-dev.sh` both failed on macOS + podman. Three independent causes, all
now fixed in `run-dev.sh`, `stop-dev.sh` and `container-runtime.sh`.

- **`podman-compose exec -d` is silently ignored.** The flag is parsed, but
  `compose_exec_args()` never forwards `--detach` to `podman exec` (podman-compose 1.5.0).
  Measured: `podman-compose exec -d -T devcontainer sleep 5` takes 5s, not 0s. `run-dev.sh`
  therefore blocked forever streaming Frigate's output, and **`frigate.extras.main` and the Vite
  dev server were never reached** — the backend was only ever half-up. New
  `compose_exec_detached()` in `container-runtime.sh` resolves the container name and uses the
  runtime's own `exec -d`. This **corrects an explicit claim** in
  [Dev Environment](operations/dev-environment.md), which stated the `exec` flags were compatible.
- **`stop-dev.sh` killed podman's port-forwarder.** It ran `lsof -ti:5173 | xargs kill -9`, but
  Vite runs *inside* the container — host 5173 is held by **gvproxy**, which also serves the
  podman API connection (`-ssh-port 64563`). Killing it took down all podman connectivity, so the
  `down` on the next line died with a Python traceback. The follow-on host-wide `pkill -f "vite"`
  / `pkill -f "npm.*dev"` would also have killed unrelated projects. Now kills Vite in the
  devcontainer.
- **`localhost:5000` never worked.** `docker-compose.yml` publishes container 5000 on **host
  5001** and nothing binds host 5000; on macOS that port is Control Center's AirPlay Receiver,
  which answers `403 Forbidden`. A wrong URL in `show_access_info` looked like a broken frontend.
  The Ports table was already correct — the script was not.

**Verified live:** full up/down cycle exits 0 both ways; both backend processes now show `Ssl`
with tty `?` (detached) where they previously showed `S+` on `pts/0`; `frigate.extras.main` runs
for the first time; podman stays reachable across `stop-dev.sh`; and 5001/5173/8123 return 200,
8971 returns 200 over TLS, with 9 cameras reporting frames.

**Left alone:** detached execs discard stdout, so neither `logs-dev.sh` nor
`docker compose logs` captures the manually-started Frigate process —
`/dev/shm/logs/frigate/current` is the s6 placeholder that only prints
`The fake Frigate service is running...`. Noted in
[Dev Environment](operations/dev-environment.md); no log redirection added yet.

## [2026-08-28] fix | Violations never created review items — 88% of violation clips did not exist

The evidence video for a violation usually was not there, and nothing said so.

**Root cause.** `TrackedObjectProcessor.create_manual_event` published a manual event onward to
the review pipeline only when `source_type == "api"`. The violation detectors pass their own
source_type so the event stays identifiable as a violation (`frigate/violations.py` —
`violation_events_clause()` matches on it, and every dashboard number depends on that), so they
fell through the gate. No review segment meant `RecordingMaintainer` had no reason to keep the
overlapping segments, so it dropped them — while the event row was written with
`has_clip = True` and the analytics row stored a `clip.mp4` URL.

**Measured before the fix**, on the dev deployment (51,014 events, 1,690 violations):

- review segments referencing a violation event: **0 of 1,324**
- violations with any overlapping recording: **206 of 1,690 (12.2%)** — 89% inside the 12h
  motion buffer, 9% outside it

Violation clips worked at all only because `record.motion.days` was `0.5`, a buffer whose
purpose the config file stated outright: *"This provides footage for manual events to
reference."* `alerts.retain.days: 30` was inert, because violations were not alerts. `Road03`,
whose rules are parking and stopping, held 612 recordings against ~1,700 on comparable cameras
— `retain.mode: motion` discards stationary vehicles, which is precisely what those rules
exist to catch.

**Why it went unnoticed:** `clip.mp4` returned **200, `video/mp4`, chunked, 0 bytes** rather
than a 404, because `recording_clip` wrote an empty ffmpeg concat playlist when nothing
overlapped. Snapshots, thumbnails and evidence images all returned normally, so the card looked
healthy and only the video was empty.

**Changed**

- `frigate/track/object_processing.py` — gate admits `VIOLATION_SOURCE_TYPES`; payload carries
  `source_type`
- `frigate/review/maintainer.py` — `PendingReviewSegment.is_violation`; violation segments are
  exempt from `review.alerts.enabled` so the Review settings page cannot silently switch off
  evidence retention. Also fixed `topic == X.value or Y.value` (always truthy) into a real
  membership test with an explicit `else: continue`.
- `frigate/api/media.py` — 404 instead of an empty 200 when no recording covers the range
- `frigate/util/builtin.py` — `update_yaml` delete path: walks without creating, is a no-op for
  a missing key, prunes maps it empties. It previously raised `KeyError` *after* creating the
  parents, which failed any "reset to the inherited value" save.
- `frigate/api/app.py` — new `GET /config/file` (the parsed config **file**, the general form of
  `/config/violations`); `update_topics` on `PUT /config/set` so one save can publish a global
  change to every affected camera instead of needing a restart
- `data/frigate-config/config.yml` — `motion.days: 0.5 → 0`, `alerts.retain.mode: motion → all`
- `web/src/views/settings/RecordingSettingsView.tsx` — new Settings → Cameras → **Recording**
  page: global defaults plus per-camera inherit/override, three presets, live apply. The master
  switch is labelled **Capture**, not Recording, because `enabled: false` deletes segments as
  they are written and makes violation clips impossible — "off" must not read as "not storing".

**Verified live.** With `continuous.days: 0` and `motion.days: 0` — no bulk retention at all —
4/4 new violations had overlapping recordings and all four clips downloaded real video
(2.0–39.7 MB); a violation with no recording now returns 404. Review segments referencing
violations went from 0 to 4 of 7 in the first sampled window. The Recording page round-trips an
override cleanly: add → save → remove → save leaves the config byte-identical.

**Tests:** `frigate/test/test_config_yaml_update.py` (13) and
`frigate/test/test_violation_review_items.py` (6), including an AST check that every
`source_type` the detectors pass is registered in `VIOLATION_SOURCE_TYPES` — the specific
omission that caused this.

**Also found:** Vite's watcher does not see host edits through the podman VM on macOS, and a
full page reload still serves the cached transform, so the dev server must be restarted after
frontend edits. Noted in [Dev Environment](operations/dev-environment.md).

**Not done:** per-rule retention. `ViolationRuleConfig.retention_days` exists and is still
unused; every violation is retained for `record.alerts.retain.days`. Also, the 1,484 violations
whose footage already expired are unrecoverable — the fix applies from now on.

## [2026-08-28] fix | Storage: open review segments were retaining 220 GB/day, 93% of it worthless

Follow-on from the violation-clip fix earlier the same day. Making violations retain their
footage worked, but the retention class they landed in turned out to be pinning nearly
everything, and the host disk was three hours from full (461 GB total, **29 GB free**).

**What was actually happening.** A recording segment is moved to permanent storage the moment
it overlaps *any* review item; the retention window only governs when it is later expired. So
write volume is set by review activity, not by the days value. And a review segment does not
close while activity continues — its `end_time` stays NULL, and `expire_review_segments`
filters on `end_time < cutoff`, which NULL never satisfies. **An open segment is immortal and
pins every recording it overlaps, forever.** These cameras run looping road footage with
traffic in frame at all times, so ordinary person/car segments never closed.

Measured: 21 open detection segments; **220 GB/day** growth; of 66 GB retained, only **4.7 GB
(7%)** overlapped a violation.

**What did not work**, recorded so it is not retried:

- `alerts.retain.days: 30 → 2` — shortens expiry, does nothing to write volume. Steady state
  would still have been ~440 GB.
- `review.alerts.enabled: false` alone — ordinary objects simply fall through to the
  *detections* bucket and keep creating review items. Rate was unchanged at 246 GB/day.

**What worked:** turning off ordinary review items entirely, both classes. Violations are
exempt via `PendingReviewSegment.is_violation`, which is exactly what that exemption was built
for, so violation review items and violation footage are untouched.

```yaml
review:
  alerts:     { enabled: false }
  detections: { enabled: false }
record:
  expire_interval: 10   # was 60; bounds write churn, which sits on disk until the next pass
  alerts: { retain: { days: 2, mode: all } }
```

**Result:** open segments 21 → 0; growth 220 GB/day → **flat** (22,275 → 22,280 MB over five
minutes); 8/8 violations still had footage and their clips played. A one-off purge of segments
overlapping no violation (60s margin) reclaimed **50.5 GB** — 66 GB → 18 GB, free space 29 GB →
78 GB.

**Cost of the trade:** the Review pane now shows violations only. For a violation-ticketing
product that is arguably correct, but it is a behavioural change, and it is reversible by
re-enabling either switch — at the storage cost documented in
[Recording Retention](components/recording-retention.md).

**Also found, not fixed:** `recording_clip` builds its ffconcat playlist with
`int(end_ts - clip.start_time)`, truncating a 1.9s outpoint to `1`. Roughly 1 in 12 sampled
violation clips came back near-empty (2.5 KB) despite all five overlapping segments being
present on disk. Upstream code, untouched by this work. Recent violations correctly return 404
until their segments leave the cache.

**Still open:** per-rule retention. `alerts.retain.days` is a single shared window, so 2 days
applies to every violation equally; `ViolationRuleConfig.retention_days` remains unused.

## [2026-08-28] ingest | Re-ingest after the recording-retention work; lint pass

Full ingest of the day's two fixes across the pages their `sources` touch, plus a lint sweep.
The earlier two entries recorded *what changed*; this pass reconciled the pages that asserted
things which are no longer true.

**Pages updated**

| Page | What was wrong |
|---|---|
| [Core Pipeline Patches](components/core-pipeline-patches.md) | listed four upstream patches; there are now six, across two newly-patched files |
| [Fork Relationship](concepts/fork-relationship.md) | "~30 modified lines across **five** files" — now seven |
| [Events & Observations API](components/api-events-observations.md) | documented `evidence.jpg` but not `clip.mp4`, the endpoint a ticket actually links to |
| [Rules Editor](components/web-rules-editor.md) | presented `/config/violations` as a one-off; it is now the special case of `/config/file` |
| [Navigation & Branding](components/web-navigation-branding.md) | no record of the Recording nav entry, its ~50 i18n keys, or the three-list sync Settings.tsx requires |
| [Configuration](operations/configuration.md) | said nothing about ordinary review items being off, which is this deployment's storage control |
| [Dev Environment](operations/dev-environment.md) | "211 tests passing" — 247 |
| [Known Issues](health/known-issues.md) | see below |
| [Recording Retention](components/recording-retention.md) | added the storage mechanism and the settings-page gap |
| [index](index.md) | three FAQ rows for the questions this work generated |

**Known Issues** gained #8h (fixed — the 220 GB/day retention blowout, including the two
attempted fixes that did *not* work) and three open items: **#16** clip truncation
(`int()` on a 1.9s outpoint, ~8% of clips near-empty), **#17** violation retention is a single
shared window (`retention_days` still unused), **#18** the Recording settings page omits
`review.*`, the setting that actually controls storage. The suggested order of work now leads
with #17 and #16 — both actively cost evidence, where the previously-top #15 costs only future
merge effort.

**Lint:** no dead sources, no dead internal links, no orphan pages. Remaining `motion.days: 0.5`
and `days: 30` references were checked and are historical narration, not stale claims.

**Deliberately not resolved:** #18 describes a gap in a page shipped the same day. It is
recorded rather than fixed because moving `review.*` onto the Recording page is a design
decision about what that page is for, not a correction.

## [2026-08-28] lint | Correct the test-suite claim: #8d is intermittent, not fixed

The two entries above both cite "247 tests passing". That was true when measured but is not a
safe claim: a later full-suite run on the same work reported 247 run, **1 failed** —
`test_post_reviews_delete_many`, the pre-existing isolation flake already filed as #8d.

Confirmed not caused by the recording-retention work: with the two new test files removed the
suite runs 228 tests and produces the *same* single failure. The module passes in isolation
(31 tests, green).

[Known Issues](health/known-issues.md) #8d and [Dev Environment](operations/dev-environment.md)
now say 246 passing with #8d flaking, and warn against reading one green run as proof.

## [2026-08-28] fix | Running the test suite alongside the stack takes the podman VM down

Observed twice while verifying the recording work. `./run-tests.sh` starts a second full-stack
container while nine camera decoders are running; on the default machine (5 CPUs, 7.45 GiB) that
is enough to kill it. Once the machine died mid-run; once `python3 -m frigate` was OOM-killed and
nginx served `500` with only the extras worker alive.

The VM misreports its own state — `podman machine list` says *Currently running* while the API
socket refuses connections, and `podman machine stop` says *stopped successfully* while leaving a
live `krunkit` process. Recovery needs an explicit `pkill -f krunkit` between stop and start.

Recorded in [Dev Environment](operations/dev-environment.md). No code change; this is an
environment constraint, not a bug in the fork.

## [2026-08-29] fix | Review switches move onto the Recording page; both default to on

Closes #18. `review.alerts.enabled` and `review.detections.enabled` were the dominant control
over storage but lived nowhere in the UI, so a user could zero every field on the Recording page
and still fill the disk.

They are now the **first** group on that page — *What creates a review item* — deliberately
above the retention windows, because the windows only matter for footage a review item has
already caused to be kept. Global plus per-camera inherit/override, same as every other field,
with a warning shown when ordinary review items are on alongside an alert window longer than a
week.

Both **default to on**, matching upstream, and the shipped config no longer sets them
explicitly — a fresh install and this deployment now get the same behaviour. This reverses the
2026-08-28 decision to ship them off: that was a deployment-specific workaround baked into the
product default, and the right shape is the upstream default plus a visible control.

**This deployment will therefore resume retaining ordinary person/car footage.** On its looping
road fixtures that measured 220 GB/day. The control is one toggle away, per camera, applied
without a restart.

Implementation notes: `FIELDS` gained a `section` (`record` | `review`) so paths resolve against
the right config block, and every field is now keyed `section.path` because `alerts.enabled` and
`alerts.retain.days` would otherwise collide. Saving publishes both
`config/cameras/<name>/record` and `.../review`, since `RecordingMaintainer` and
`ReviewSegmentMaintainer` subscribe separately. Presets set the switches explicitly rather than
leaving them implicit.

**Verified live:** an override written from the UI landed as
`cameras.Road01.review.detections.enabled: false` and took effect with no restart (Road01
detections off, Road02 still on); removing it pruned the key and returned the camera to the
default.

## [2026-08-29] fix | /dev/shm was holding 12 frames against the 50 Frigate wants

Frigate warned *"/dev/shm allocation (256 MB) should be increased to at least 370 MB"*. The
warning understates it: `shm_size` sizes a shared-memory frame ring, and undersizing shortens
the buffer silently rather than failing.

Measured with `calculate_shm_requirements()` on the current camera set (7 enabled, one 1080p,
16.0 MB of frame budget): 256mb held **12 frames**, 2.4 s at 5 fps, against a target of 50.

Raised to **512mb** — 28 frames, ~5.6 s, with headroom for another camera. Not 896mb, which is
what 50 frames would need: tmpfs occupies what it holds, so that is ~800 MB resident on a
7.45 GiB machine that has already OOM-killed Frigate once today.

Verified after recreating the container: `/dev/shm` 512M, `shm_frame_count` 28, warning gone,
all cameras back at ~5 fps. Note `shm_size` applies only on container **recreation** — a restart
keeps the old tmpfs.

**Not claimed:** this plausibly interacts with the fork's snapshot frame-time lookup
(`save_manual_event_image` falls back to the current frame when the timestamp has been evicted —
[Core Pipeline Patches](components/core-pipeline-patches.md) §1, and known issue #13). A deeper
ring makes eviction less likely. But the fallback logs to a stdout that detached processes
discard, so there is no evidence either way here and none is asserted.

## [2026-08-29] fix | Rules editor: camera picker, `any` zone wildcard, model-wide object list

Three changes to the violation rule dialog, plus the engine and config support two of them
needed.

**Camera picker.** The dialog inherited the camera from the settings page header. It now selects
its own, and saving onto a different camera moves the rule — appended to the destination's
`violations`, removed from the source, in one `config/set` write.

**`any` zone wildcard.** New `ANY_ZONE` sentinel in `frigate/config/camera/violation.py`,
accepted in both `from_zones` and `to_zone`. `referenced_zones()` skips it so
`verify_violation_rules` does not read it as a missing zone, while a real zone name alongside it
is still checked.

The semantics needed a correction found by the tests. The first implementation asked "has this
object been in any zone", which is *always* true: `StateTracker` appends an object's current
zones to its history **before** rules evaluate, so a wildcard rule fired on any detection with
no movement at all. It now requires a history entry the object has since left. Six DSL tests and
six config tests pin this, including that a named zone is unaffected and a typo is still a hard
error.

**Objects from the model, not the camera.** The picker lists every label in
`config.detectors.<name>.model.labelmap`, grouped into tracked / other. Two constraints made
this more than a list change:

- `verify_violation_rules` rejects a label not in the camera's `objects.track`, so choosing an
  untracked one now widens `objects.track` in the same write, and the dialog says so first.
- `objects.track` has to come from the config **file**. `verify_objects_track` strips labels the
  model cannot produce and runs *after* `verify_violation_rules`, so rules validate against the
  authored list while `/api/config` shows the stripped one. The first implementation read the
  runtime list and wrongly offered to re-add labels the config already had.

**Found while testing:** the shipped model has 90 labels and `truck` is not one of them, yet
five rules across four road cameras name it in `vehicle_types`. They parse, run, and are quietly
blind to lorries. Filed as [#19](health/known-issues.md), now top of the suggested order of work
because it is a config edit rather than a code change. The dialog flags such a label so new
rules cannot acquire the problem.

**Verified:** 259 tests, all passing except the known #8d flake. Dialog driven in a browser —
91 objects listed and grouped, `any` offered in both zone controls, and the six
accept/reject cases confirmed directly against `FrigateConfig.parse_yaml`.

## [2026-08-29] fix | Reject conditions that cannot mean what they look like

A rule sees one MQTT event describing one object, so `detected(label)` tests only that event's
own label. Two conditions were authorable and silently wrong:

- `detected(a) AND detected(b)` — always false
- `detected(a) AND NOT detected(b)` — **always true**, because `detected(b)` is always false and
  `NOT` of it is always true. It reads as "a without b" and fires on every a.

Verified by evaluating both against a real fire event: identical results whether or not an
extinguisher was present. The second is the one that matters — a fire-without-extinguisher rule
would have looked correct and alerted on every fire.

`unsatisfiable_condition()` in `frigate/config/camera/violation.py` now rejects both at parse
time, mirrored in `web/src/lib/violationRules.ts` so the editor disables Save and explains why
rather than failing on the round trip. Ten tests cover what stays legal: OR between labels, the
same label twice, `detected(label, zone)`, and `NOT in_zone(...)` — negating a zone is
meaningful because `in_zone` is about the current object.

The 11 shipped rules all still validate. 269 tests, all passing except the known #8d flake.

Co-presence remains unsupported and is the next thing to build — see
[DSL Rule Language](concepts/dsl-rule-language.md).

## [2026-08-29] ingest | New rule type: zone_occupancy (min/max objects in a zone)

The first rule type that counts rather than detects, and the first fed by something other than
`frigate/events`.

**Why it was cheap.** Frigate's `CameraActivityManager` already maintains per-zone object counts
and republishes them on every change, to `frigate/<zone>/<label>` and `frigate/<zone>/all` (plus
`/active` variants for non-stationary objects only). Confirmed on the live bus before building
anything. So a threshold breach *is* an event — this is the only counting requirement that does
not need the periodic tick the worker still lacks.

**What was built**

- `ViolationTypeEnum.zone_occupancy` with `zone`, `count_label`, `min_count`, `max_count`.
  At least one threshold required; a minimum above a maximum is rejected as unsatisfiable.
- `ZoneOccupancyRule`, which returns False for anything that is not a `zone_count` message.
  Without that guard every tracked object would be tested against the threshold.
- `MQTTClient.set_extra_topics()` — zone topics carry a **bare integer**, not event JSON, so
  `_on_message` routes non-`frigate/events` topics to a raw callback rather than parsing them.
- `EventDispatcher._zones_watched_for_occupancy()` subscribes only to zones a rule actually
  names, and attaches the camera, which the topic does not carry.
- Rule type, form and validation in the editor.

**The sharp edge, made a hard error.** The count topic is keyed by zone name with no camera in
it, so two cameras sharing a zone name have their counts summed. This deployment already has two
such pairs (`rightcomeend`, `rightcomestart` on Road04/Road05).
`verify_occupancy_zone_names_are_unique()` rejects an occupancy rule on a shared zone name and
says which camera it clashes with, rather than leaving it as documentation nobody reads.

**Verified live** before the check was cut short: the rule persisted, validated, and the worker
logged *"Watching occupancy of: zone01"* with the topic subscribed and 2 rules loaded. It
correctly did not fire at `max_count: 1`, because zone01 never exceeds one car. 39 config tests
and 34 engine tests pass.

**Note for authors:** occupancy rules need a full Frigate restart, not just an extras restart —
the worker reads rules from `/api/config`, the running config, like every other rule type.

## [2026-08-29] lint | Refresh test counts and complete the sources lists

Housekeeping pass after the rules work, no behaviour change.

**Test count corrected to 286 / 285 passing** (was 247 / 246) in
[Known Issues](health/known-issues.md) #12 and
[Dev Environment](operations/dev-environment.md). Roughly 40 tests were added across
2026-08-28/29: `test_config_yaml_update.py`, `test_violation_review_items.py`, and new classes in
`test_violation_config.py` and `test_dsl_rules.py` for the `any` wildcard, unsatisfiable
conditions, and `zone_occupancy`. #8d still flakes on discovery order.

**Also recorded:** a full run is normally about a minute but took **twelve** on a loaded machine
(nine camera decoders plus the test container), and `run-tests.sh` buffers its output — so a run
that looks hung usually is not. Worth knowing before killing one, which is what happened here.

**`sources:` completed** on four pages that had grown to describe files they did not list:
`frigate/config/camera/violation.py` now backs the rule-language, engine and editor pages, since
`ANY_ZONE`, `COUNT_ALL` and `unsatisfiable_condition()` all live there;
`frigate/camera/activity_manager.py` backs the extras page, since it is the source of the zone
counts; `web/src/lib/violationRules.ts` backs the editor page. Without these the staleness sweep
would not flag those pages when the code changes.

Lint clean: no dead sources, no dead links, no orphans.

## [2026-08-29] fix | Four UI defects found by driving the app, one of them a Radix trap

All four reported after using the new screens, all now fixed and covered by 56 Playwright checks.

**The multiselect could not select or deselect anything.** The list appeared and every click
closed it, changing nothing. Two wrong guesses first — component identity (`Row` declared inside
the render) and z-index — before measuring instead of theorising:

```
bodyPointerEvents: none     optionPE: none
elementFromPoint(over an option) -> the dialog behind it
```

A modal Radix `Dialog` sets `pointer-events: none` on `<body>` and re-enables it only on the
dialog content. `PopoverContent` portals to `<body>`, so it inherited `none`: clicks passed
through to the dialog, which read them as outside interactions and closed the popover. Fixed
with the `disablePortal` prop the component already had. **Raising the z-index does nothing** —
the element is not covered, it is not accepting pointer events at all. Documented in
[Rules Editor](components/web-rules-editor.md) so the next dropdown-in-a-dialog is not debugged
from scratch.

**Only one camera's rules were listed.** The page showed the camera picked in the settings
header. It now lists every rule on every camera, headed `Camera — Rule`. The control
`aria-label`s are camera-qualified too, since rule names are unique only within a camera —
`wrongway` exists on both Road01 and Road04.

**Disabling a camera made its rules vanish.** A direct consequence of making the camera toggle
persist earlier the same day: `enabled_in_config` went false and the camera dropped out of the
list. Rules on disabled cameras now stay listed and are marked, because they are still in the
config and fire the moment the camera returns.

**Rule headers now carry the camera**, as requested.

**Testing.** Five Playwright suites, 56 checks: the Recording page (fields, presets, per-camera
override round trip incl. pruning), the rules list, the rule dialog (camera picker, `any` zones,
multiselect select/deselect/reselect, unsupported-label warning), `zone_occupancy` create →
verify in config → delete, moving a rule between cameras, the condition guard disabling Save, and
camera enable/disable with a 250ms UI response and a persisted write. Config verified
byte-identical to a pre-test snapshot afterwards, so none of it leaked into the deployment.

Two testability additions while doing it: `data-testid="object-picker"`, and `id` on the
min/max count inputs, matching the `cooldown` and `duration` fields next to them.
