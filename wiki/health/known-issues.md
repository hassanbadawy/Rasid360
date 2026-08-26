---
type: health
status: current
sources: [frigate/api/dashboard.py, frigate/analytics_scheduler.py, frigate/violations.py, frigate/video.py, frigate/app.py, web/src/hooks/use-violations.ts, frigate/api/event.py, frigate/extras/main.py, docker/main/rootfs/etc/s6-overlay/s6-rc.d]
updated: 2026-08-25
---

# Known Issues

Severity-ordered, with the evidence for each so it can be re-checked rather than re-litigated.

**Status as of 2026-08-25:** items 1-8 and 8b fixed; 9-11 and 13-15 open. Verified by 211
passing tests **and** a live run of the stack. See [log](../log.md) for the passes.

---

## Fixed

### 1. Dashboard access control — arity/await bug ✅

Eight call sites invoked the `async` `get_allowed_cameras_for_filter` with two arguments (it
takes one) and without awaiting. `camera/fps` and `camera/offline` returned 500 unconditionally;
six chart endpoints returned 500 whenever a `cameras` filter was applied. Access control never
ran on those paths, and the obvious fix would have converted the outage into a silent
cross-camera leak.

**Fixed:** all ten endpoints are `async def` and route through one `resolve_camera_filter`
helper that always returns an explicit list, so the filter applies unconditionally and fails
closed. Covered by `frigate/test/http_api/test_http_dashboard.py`.
Detail: [Camera Access Control](../concepts/camera-access-control.md).

### 2. Face and plate recognitions counted as violations ✅

Aggregations defined a violation as `sub_label IS NOT NULL`, but upstream Frigate writes
`sub_label` for enrichment results too, and this deployment has LPR configured.

**Fixed:** `frigate/violations.py` defines `violation_events_clause()`, requiring both a
`sub_label` and a detector marker in `Event.data["type"]`. Applied across
`analytics_scheduler.py`, `api/dashboard.py`, and `api/event.py`. Verified against SQLite: the
old clause matched 7 of 7 seeded rows where only 4 were violations.
Detail: [Violation Lifecycle](../concepts/violation-lifecycle.md).

### 3. Extras worker unsupervised ✅

Started only by `run-dev.sh` via a detached `exec`. If it died, Frigate kept running and
violation detection stopped silently.

**Fixed:** completed the `frigate-extras` and `frigate-extras-log` s6 services (empty
scaffolding directories existed but held no `run`/`type` files, so git never tracked them).
Deliberately omits `s6-svc -O` so s6 restarts it, and its `finish` does not halt the container.
The devcontainer keeps the manual workflow via `fake_frigate_extras_run`.
Detail: [Extras Service](../components/extras-service.md).

### 4. No tests over the new backend ✅ (partially)

**Fixed:** `frigate/test/extras/test_dsl_rules.py` (17 tests, passing) covers the DSL parser,
rule factory, evaluation, cooldown, and the frame-time handshake.
`frigate/test/http_api/test_http_dashboard.py` covers every dashboard route in both branches,
camera scoping, and fail-closed behaviour.

All 23 run green in a container — see item 12 and
[Dev Environment](../operations/dev-environment.md).

**Still uncovered:** the analytics scheduler's aggregation methods, the observations CRUD, and
the evidence-image path. See item 12.

### 5. Ticket state split across two stores ✅

`POST /events/{id}/ticket` wrote `Event.data`; `PUT /observations/{id}` wrote
`AnalyticsObservation`; the scheduler read only the former, so observations-API updates never
reached a chart. `ticket_updated_by` was hardcoded to `"admin"`.

**Fixed:** `Event.data` is the system of record, with best-effort write-through in both
directions (`_sync_observation_ticket`, `_sync_event_ticket`), and real attribution from
`Depends(get_current_user)`.
Detail: [Events & Observations API](../components/api-events-observations.md).

### 6. Development hacks on `main` ✅

`video.py` matched a hardcoded `"LPR_Camera"` string in the per-frame hot path;
`app.py` had upstream's `cleanup_timeline_db` commented out.

**Fixed:** `detect.always_full_frame` config option (default `false`, enabled on `LPR_Camera`
so behaviour is unchanged); timeline cleanup re-enabled with an `OperationalError` guard so a
database missing the table skips it rather than refusing to start.
Detail: [Core Pipeline Patches](../components/core-pipeline-patches.md).

### 7. Aggregation re-executed lazy queries ✅ (partially)

Each aggregate query was iterated 2-3 times (`sum`, insert loop, `len(list(...))`), and
`aggregate_ticket_status` materialised every violation event to count in Python.

**Fixed:** queries are materialised once with `list(...)`; ticket status groups in SQL.

**Still open:** the scans remain unbounded by time — see item 9.

### 8. `analytics.db` had no WAL ✅

**Fixed:** `ANALYTICS_DB_PRAGMAS` sets `journal_mode=wal`, `busy_timeout=5000`,
`synchronous=normal`, and the extras worker now calls the same `init_analytics_db` instead of
opening the database itself, so both writers get identical pragmas.

**Still open:** the two processes still derive the database *path* independently — see item 11.

### 8b. Embeddings process crashed at boot — incomplete `bird` → `object` rename ✅

**Severity was: high — silently disabled semantic search, face recognition, and LPR**

Found by running the app, not by reading it. Every startup produced:

```
File "frigate/embeddings/maintainer.py", line 169, in __init__
    if self.config.classification.bird.enabled:
AttributeError: 'ClassificationConfig' object has no attribute 'bird'
```

Upstream commit `99a363c0` renamed `BirdClassificationConfig` → `ObjectClassificationConfig` and
the config field `bird` → `object` in `frigate/config/classification.py`, but updated only the
**log message strings** in `frigate/data_processing/real_time/bird.py` — leaving two live
attribute accesses pointing at a field that no longer exists:

- `frigate/embeddings/maintainer.py:169` — raised during `EmbeddingMaintainer.__init__`, killing
  the entire embeddings process
- `frigate/data_processing/real_time/bird.py:155` — would raise if that processor ran

**Fixed 2026-08-25**, both changed to `.object`.

Why it matters more than a stray attribute: the embeddings process owns semantic search, face
recognition, **and licence-plate recognition**. On this deployment — which has LPR configured —
LPR has not been running since that commit. This interacts with item 2: part of the reason
enrichment `sub_label` values may not have been visibly inflating violation counts is that the
process writing them was dead.

### 8c. Violation rules were unvalidated and YAML-only ✅

Rules lived in `frigate/extras/config.yml`, read by a separate process with no view of the camera
config, so a rule naming a nonexistent zone loaded cleanly and silently never fired.

**Fixed 2026-08-25.** Rules moved to `cameras.<name>.violations` in the Frigate config, modelled
by `ViolationRuleConfig` and cross-validated by `verify_violation_rules` against that camera's
zones and tracked objects. Editable from Settings → Cameras → Violation Rules
([Rules Editor](../components/web-rules-editor.md)). The extras config remains a fallback.

Two latent bugs surfaced during the migration:

- **`speed_threshold` was accepted and ignored** — `Road03`'s speed rule was firing on any
  vehicle in the zone at any speed. Now implemented in `SustainedConditionRule`.
- **`Road05` had two rules both named `wrongway`** (left and right lane). Cooldown keys on
  `camera:rule_name`, so with `cooldown: 600` a right-lane violation suppressed left-lane
  detection for ten minutes. Renamed to `wrongway_right` / `wrongway_left`.

---

## Open

### 8d. `test_post_reviews_delete_many` fails when run after another suite

**Severity: low — pre-existing, not caused by this work**

`frigate/test/http_api/test_http_review.py` passes in isolation but fails when any other http_api
suite runs first. Verified with `test_http_media` → `test_http_review`, which involves none of
this fork's code. Adding `frigate/test/test_violation_config.py` changed discovery order enough
to expose it.

It is an upstream test-isolation problem — recordings state leaking between suites — and fixing
it means changing an upstream test, which adds merge surface. Left alone deliberately.

Workaround: `./run-tests.sh frigate.test.http_api.test_http_review` passes.

### 9. Aggregation cost grows without bound

**Severity: medium — degrades over time**

`AnalyticsScheduler` recomputes every table from scratch every 300s (288×/day), scanning the
entire event history with no time window. Cost grows linearly with retention and never resets.

The fix is incremental aggregation — track a watermark and only process events since the last
pass — or at minimum bound the scan to the retention window.
[Analytics Scheduler](../components/analytics-scheduler.md).

### 10. Silent failure is the house style

**Severity: low individually, high as a pattern**

Broad `except Exception` returning `{"success": false}` throughout `dashboard.py`, combined with
a frontend that renders errors as empty charts. Backend faults present as "no data" — which is
precisely why item 1 survived undetected.

Two changes: narrow the exception handling to expected database errors, and distinguish *empty*
from *errored* in the UI.

### 11. `analytics.db` path derived two different ways

**Severity: low**

Frigate derives it from `config.database.path`; the extras worker reads `$ANALYTICS_DB_PATH`.
They normally agree, but nothing enforces it — customising `config.database.path` alone sends
the two processes to different files, and nothing errors.

Also: `create_tables(safe=True)` means schema changes need manual migration; `migrations/`
covers `frigate.db` only.
[Analytics Database](../components/analytics-database.md).

### 12. Remaining test gaps

**Severity: low-medium**

The suite now runs green in a container — **211 tests passing** as of 2026-08-24, via
`./run-tests.sh`. That includes the 17 DSL tests and the 6 dashboard tests, which were previously
written but unexecuted.

Still not covered: the analytics scheduler's aggregation methods (the highest-value remaining
target — they define every dashboard number), the observations CRUD and its write-through, and
the evidence-image path.

### 13. Evidence images depend on a 5-second race

**Severity: low — visible, self-reporting failure**

`_handle_violation` polls `CLIPS_DIR` 10 times at 0.5s intervals for Frigate's snapshot. Past
5 seconds no evidence image is written and the UI shows "Evidence image not available". Fails
visibly, which is why this ranks low. An event-driven hook would beat polling.

### 14. Repository hygiene

**Severity: low**

- `origin/HEAD` points at `dev`, **4 commits behind `main`** — GitHub visitors see the state
  before branding, dark theme, the thumbnail fix, and the playback routes
- Untracked 6.9 MB notebook in the repo root:
  `open_vocabulary_object_detection_with_qwen3_vl.ipynb`
- One dangling stash: `stash@{0}: WIP on dev`
- A fresh clone **cannot run the system** — the tracked config references MP4 fixtures excluded
  by `.gitignore`. They are present on the original dev machine, where the cameras run normally
  ([Configuration](../operations/configuration.md))
- ~~`docker-compose.yml` mounts `/config` twice~~ — **fixed 2026-08-25.** Docker silently let
  the last definition win; podman rejects it outright with
  `Error: /config: duplicate mount destination`, which blocked startup. The vestigial
  `./config:/config` was removed, leaving `./data/frigate-config`

### 15. Upstream divergence

**Severity: high strategically, no immediate symptom**

**1,056 commits behind** upstream as of 2026-08-24, with **511 files** changed on both sides and
all five core-patched files among them. The `upstream` remote now exists so the gap is at least
measurable, but nothing has been merged.

This compounds daily and is the largest long-term risk to the project.
[Fork Relationship](../concepts/fork-relationship.md).

---

## Suggested order of work

1. **#15** — attempt a trial merge on a scratch branch to size the real cost
2. **#9** — incremental aggregation, before history makes it painful
3. **#12** — cover the scheduler's aggregations; they define every dashboard number
4. **#10** — narrow the exception handling so the next bug of this class surfaces
