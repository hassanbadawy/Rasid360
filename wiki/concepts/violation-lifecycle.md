---
type: concept
status: current
sources: [frigate/extras/main.py, frigate/extras/actions/dsl_violation_detector.py, frigate/extras/dsl/evaluator.py, frigate/extras/utils/frigate_api.py, frigate/track/object_processing.py, frigate/camera/state.py, frigate/analytics_db.py, frigate/api/media.py]
updated: 2026-08-24
---

# Violation Lifecycle

The end-to-end path from a camera frame to a closed ticket. This is the spine of the system —
almost every other page is a detail of one of these steps.

```
camera frame
  → Frigate detection
  → MQTT frigate/events
  → EventDispatcher
  → DSLViolationDetector
  → RuleEvaluator (+ StateTracker)
  → POST /api/events/{camera}/{label}/create
  → Frigate snapshot (frame-time synchronised)
  → evidence image with bbox
  → AnalyticsObservation row
  → AnalyticsScheduler aggregation
  → dashboard charts + ticket UI
```

## 1. Detection and publish

Standard upstream Frigate. Objects are tracked and each state change is published to MQTT under
`frigate/events` with `before` / `after` payloads.

One local deviation: for the camera literally named `LPR_Camera`, detection is forced on the
full frame even when no motion region exists — see
[Core Pipeline Patches](../components/core-pipeline-patches.md).

## 2. Dispatch

`frigate/extras/main.py` — `EventDispatcher` subscribes to `frigate/events` via
`MQTTClient` and fans each event out to every enabled action handler. Handlers are
independent; one throwing does not stop the others.

Details: [Extras Service](../components/extras-service.md).

## 3. Rule evaluation

`DSLViolationDetector.process_event` (`frigate/extras/actions/dsl_violation_detector.py:106`)
filters by camera, then hands the event to `RuleEvaluator.evaluate_event`
(`frigate/extras/dsl/evaluator.py:27`).

The evaluator:

1. Updates `StateTracker` with the object's current zones, box, and frame time.
2. Builds an evaluation context (zone sequence so far, sustained-condition durations,
   detection counts).
3. Tests each rule configured for that camera.

`StateTracker` is what makes temporal rules possible — it remembers zone sequences per object
id, when a condition started, how many consecutive frames it has held, and the `frame_time` of
the *first* qualifying detection. That last one matters in step 5.

Details: [DSL Engine](../components/dsl-engine.md), [DSL Rule Language](dsl-rule-language.md).

## 4. Violation record

`_create_violation` (`evaluator.py:122`) builds a dict carrying `rule_name`, `type`, `camera`,
`label`, `sub_label`, `object_id`, `box`, `frame_time`, `duration`, `severity`,
`retention_days`, `zone_sequence`, and `description`.

**`sub_label` carries the violation type**, and `Event.data["type"]` marks the source. Frigate has
no concept of a "violation" — Rasid360 represents one as a manual event with a `sub_label` set and
a detector marker in `data["type"]`, populated from the `source_type` passed to the create API and
stored by `TrackedObjectProcessor.create_manual_event` (`frigate/track/object_processing.py:545`).

Both halves are required, because **`sub_label` alone is not specific to violations.** Upstream
Frigate writes it for enrichment results — face recognition
(`frigate/data_processing/real_time/face.py:182`) and licence-plate recognition both publish it
via `EventMetadataTypeEnum.sub_label` — and this deployment has LPR configured.

The shared predicate lives in `frigate/violations.py`:

```python
def violation_events_clause():
    return Event.sub_label.is_null(False) & (
        Event.data["type"].cast("text").in_(list(VIOLATION_SOURCE_TYPES))
    )
```

with `VIOLATION_SOURCE_TYPES = ("dsl_violation_detector", "wrong_way_detector", "custom_action")`
— the `source_type` values used by the handlers in `frigate/extras/actions/`.

Everything downstream uses it: the scheduler's aggregations, the dashboard's live-query paths,
and `GET /events/violation_types`. Until 2026-08-24 those all filtered on
`sub_label IS NOT NULL` alone, so **every recognised face and plate was counted as a
violation**.

## 5. Event creation and the frame-time handshake

`FrigateAPI.create_event` (`frigate/extras/utils/frigate_api.py:21`) POSTs to
`/api/events/{camera}/{label}/create` with:

```json
{ "sub_label": "...", "score": 1.0, "source_type": "dsl_violation_detector",
  "include_recording": true, "duration": 30,
  "draw": { "box": [x1,y1,x2,y2], "frame_time": 1740000000.123 } }
```

The `draw.frame_time` field is a Rasid360 addition and the reason for the "fix thumbnails"
work. On the Frigate side:

- `TrackedObjectProcessor` pulls `draw["frame_time"]` and forwards it
  (`frigate/track/object_processing.py:519`)
- `CameraState.save_manual_event_image` looks that timestamp up in `frame_cache` and converts
  YUV→BGR, falling back to the current frame with a warning if it has already been evicted
  (`frigate/camera/state.py:528`)

Without this, the snapshot showed whatever was in front of the camera when the *rule fired*,
not when the *violation happened* — which for a rule requiring 30s of sustained condition is a
completely different scene.

## 6. Evidence image

Back in `_handle_violation` (`dsl_violation_detector.py:136`), the detector polls `CLIPS_DIR`
for `{camera}-{event_id}.jpg` — **10 attempts, 0.5s apart, 5 seconds total** — because Frigate
writes the snapshot asynchronously. On success it decodes the JPEG, draws bounding boxes with
`frigate.util.image.draw_box_with_label`, and writes `{camera}-{event_id}-viol.jpg`.

That file is served by `GET /api/events/{event_id}/evidence.jpg`
(`frigate/api/media.py`), which 404s cleanly if the file never appeared.

This polling handshake is the most fragile link in the chain: if the snapshot takes longer than
5 seconds, the evidence image is silently never created and the UI shows "Evidence image not
available".

## 7. Observation row

`AnalyticsObservation.create` writes into `analytics.db` with `status="new"`, media URLs
(`cleanshot` → `snapshot-clean.webp`, `bboxshot` → `evidence.jpg`), the bounding box split into
`box_x/y/width/height`, and a `metadata` JSON blob carrying the DSL rule that fired.

This row is both the analytics record and the ticket.
[Analytics Database](../components/analytics-database.md).

## 8. Aggregation

`AnalyticsScheduler` wakes every 300s and recomputes every aggregate table from scratch —
delete-all, insert-all, over the full history of `frigate.db`.
[Analytics Scheduler](../components/analytics-scheduler.md).

## 9. Presentation and ticketing

- Charts read `/api/dashboard/*` → [Dashboard API](../components/api-dashboard.md),
  [Web Dashboard](../components/web-dashboard.md)
- Ticket state is edited through `POST /api/events/{id}/ticket` and the `/api/observations`
  CRUD → [Events & Observations API](../components/api-events-observations.md)
- Statuses: `new → in_progress → solved | closed | fake`

`fake` is the false-positive escape hatch, which matters given the rules are heuristic.

## Latency

Roughly: detection is real-time, rule evaluation is immediate on MQTT arrival, evidence appears
within ~5s, but **charts lag by up to 5 minutes** because of the scheduler interval. An operator
watching the dashboard will not see a violation appear the moment it happens.
