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
