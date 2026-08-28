---
type: component
status: current
sources: [frigate/video.py, frigate/camera/state.py, frigate/track/object_processing.py, frigate/app.py, frigate/review/maintainer.py, frigate/util/builtin.py]
updated: 2026-08-28
---

# Core Pipeline Patches

Every modification to upstream Frigate's own code. There are only four files and roughly 30
lines — deliberately small, which is what keeps upstream merges viable
([Fork Relationship](../concepts/fork-relationship.md)).

Two of these are legitimate features. Two are development hacks that should not be on `main`.

## 1. Snapshot frame-time synchronisation — legitimate

**`frigate/camera/state.py`** — `save_manual_event_image` gains a
`snapshot_frame_time: float | None` parameter. When a frame is not supplied but a timestamp is,
it resolves the frame from `frame_cache` and converts YUV→BGR:

```python
if frame is None and snapshot_frame_time is not None:
    cached = self.frame_cache.get(snapshot_frame_time)
    if cached:
        frame = cv2.cvtColor(cached["frame"], cv2.COLOR_YUV2BGR_I420)
    else:
        logger.warning(f"{self.name}: Frame {snapshot_frame_time} not in cache ...")
        frame = self.get_current_frame()
```

**`frigate/track/object_processing.py`** — extracts the timestamp from the manual event's `draw`
payload and forwards it:

```python
snapshot_frame_time = draw.get("frame_time") if draw else None
self.camera_states[camera_name].save_manual_event_image(
    None, event_id, label, draw, snapshot_frame_time
)
```

**Why it exists.** A DSL rule may only conclude a violation occurred after 30 seconds of
sustained condition. Without this, the snapshot captured whatever was in frame at *conclusion*
time — often an empty road. This is the "fix thumbnails" commit and it is a genuine correctness
fix for the violation use case.

**Caveat.** The fallback is silent to the user: if the frame has already been evicted from
`frame_cache`, the snapshot quietly reverts to the current frame with only a log warning. There
is no signal in the UI that the evidence image is not the moment of violation.

## 2. Full-frame detection — now a config option

**`frigate/video.py`**, inside `process_frames`:

```python
# Cameras with detect.always_full_frame run detection even when motion
# found nothing, for targets that are stationary or move too little to
# trigger motion (license plates in particular).
if len(regions) == 0 and camera_config.detect.always_full_frame:
    regions.append([0, 0, frame_shape[1], frame_shape[0]])
```

**Fixed 2026-08-24.** `always_full_frame: bool = False` was added to `DetectConfig`
(`frigate/config/camera/detect.py`), and enabled on `LPR_Camera` in
`data/frigate-config/config.yml` so behaviour is unchanged.

Previously this read `camera_config.name == "LPR_Camera"` — a hardcoded camera name in the
per-frame hot path, labelled `DEVELOPMENT HACK`, which broke silently if the camera was renamed.

The underlying need is real: plates on stationary or slow vehicles may never trigger motion. The
cost is also real — a detection pass on every frame for that camera removes the motion-gating
premise Frigate is built on, and on an accelerator-constrained deployment can starve other
cameras. Which is why it is opt-in per camera and documented in the field description.

Note the log line inside that branch interpolates `camera_config.name`; `camera_name` is not in
scope in `process_frames`, and f-strings evaluate eagerly, so referencing it would raise
`NameError` every time the branch was taken.

## 3. Timeline cleanup — re-enabled with a guard

**`frigate/app.py`**, in `init_database`:

```python
if not os.path.exists(f"{CONFIG_DIR}/.timeline"):
    cleanup_timeline_db(migrate_db)
```

**Fixed 2026-08-24.** The call was commented out as `TEMPORARILY DISABLED FOR DEVELOPMENT`, the
stated reason being "timeline table not created by migrations".

That reason does not hold: the cleanup runs *after* `router.run()`, which applies
`migrations/013_create_timeline_table.py`. A missing table therefore indicated a local database
in an unexpected migration state, not an ordering problem in the code.

Rather than leave upstream behaviour disabled, `cleanup_timeline_db` now catches
`peewee.OperationalError` around the `DELETE`, logs a warning, and returns — so a database
genuinely missing the table skips the cleanup instead of refusing to start.

## 4. Analytics wiring — legitimate

**`frigate/app.py`** also gains the analytics lifecycle, which is ordinary integration rather
than a patch:

- `init_analytics_database()` added to the startup sequence after `init_database()`
- `init_analytics_scheduler(interval_seconds=300, frigate_db=self.db)` at the end of
  `init_database`, deliberately after `self.db.bind(models)`
- `stop_analytics_scheduler()` and `close_analytics_db()` in the stop path

Some debug logging was also added to `FrigateApp.__init__`, including a defensive
`if not self.metrics_manager` check.

See [Analytics Scheduler](analytics-scheduler.md).

## 5. Violations reach the review pipeline

**`frigate/track/object_processing.py`** — `create_manual_event` published its event onward
only for `source_type == "api"`. Rasid360's detectors pass their own source_type so the event
stays identifiable as a violation, so they fell through:

```python
if source_type == "api" or source_type in VIOLATION_SOURCE_TYPES:
```

The published payload also gained `source_type`, so the review maintainer can tell a violation
from a generic manual event without a database round trip.

**`frigate/review/maintainer.py`** — a file the fork had not previously touched.
`PendingReviewSegment` gains an `is_violation` flag, and the three places that gate on
`review.alerts.enabled` now read `is_violation or ...enabled`. A violation must not be
silenceable from the Review settings page, because that switch would otherwise stop the
retention that keeps violation footage on disk.

One upstream bug fixed in passing, in the same dispatch block:

```python
# before -- `or DetectionTypeEnum.lpr.value` is a non-empty string, always truthy
elif topic == DetectionTypeEnum.api.value or DetectionTypeEnum.lpr.value:
# after
elif topic in (DetectionTypeEnum.api.value, DetectionTypeEnum.lpr.value):
    ...
else:
    continue
```

It was harmless only because no other topic reaches that loop.

**Why it exists.** Without it a violation never became a review item, the recording maintainer
had no reason to keep the overlapping segments, and `clip.mp4` returned an empty body while the
event row claimed `has_clip = True`.
Full mechanism: [Recording Retention](recording-retention.md).

## 6. Config writes can clear a key that was never set

**`frigate/util/builtin.py`** — also previously untouched. `update_yaml` treats an empty-string
value as "delete this key", but the delete shared the *creating* walk, so clearing a key the
config had never set built the parent maps on the way down and then raised `KeyError`. The
delete path now walks without creating, is a no-op for a missing key, and prunes maps it
empties.

**Why it exists.** Any per-camera override editor removes a key the moment the user picks "use
the global value" — including on a field the camera never set. Before this, that failed the
whole save. Covered by `frigate/test/test_config_yaml_update.py`.

## Merge checklist

When merging upstream, these four files need manual review. Everything else in the fork is
additive.

| File | Action |
|---|---|
| `camera/state.py` | Keep — re-apply the parameter and cache lookup |
| `track/object_processing.py` | Keep — re-apply the `frame_time` forward |
| `video.py` | Keep — re-apply the `always_full_frame` branch |
| `config/camera/detect.py` | Keep — re-apply the `always_full_frame` field |
| `app.py` | Keep the analytics wiring; the timeline cleanup is upstream's own code and upstream intends to remove it — take upstream's version |
| `review/maintainer.py` | Keep — re-apply `is_violation` and the three `is_violation or ...enabled` gates. Re-check the topic dispatch fix; upstream may have corrected it independently |
| `util/builtin.py` | Keep — re-apply the `update_yaml` delete path. Purely additive to upstream behaviour: it only changes what happens when the key is absent |
| `api/media.py` | Keep — re-apply the empty-recordings 404 in `recording_clip` |

Expect conflicts in each; all have upstream changes since the fork point.

**This work widened the merge surface.** `review/maintainer.py` and `util/builtin.py` were
untouched upstream files before 2026-08-28 and are now patched, taking the count of modified
upstream files from five to seven. Both patches are small and defensive, but they are two more
files to reconcile on an upstream merge — see [Fork Relationship](../concepts/fork-relationship.md).
