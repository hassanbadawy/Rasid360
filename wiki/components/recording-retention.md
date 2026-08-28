---
type: component
status: current
sources: [frigate/config/camera/record.py, frigate/record/maintainer.py, frigate/record/cleanup.py, frigate/track/object_processing.py, frigate/review/maintainer.py, frigate/api/media.py, frigate/api/app.py, frigate/util/builtin.py, web/src/views/settings/RecordingSettingsView.tsx, data/frigate-config/config.yml]
updated: 2026-08-28
---

# Recording Retention

How violation footage survives on disk, and the settings page that controls it.

## Frigate never starts recording

There is no event-triggered capture anywhere in the codebase. When `record.enabled` is true,
ffmpeg writes ten-second segments to a cache directory **continuously, for every camera**.
`RecordingMaintainer.validate_and_move_segment` (`frigate/record/maintainer.py`) then walks
those segments and decides, one at a time, whether each is worth moving to permanent storage:

1. `continuous.days > 0` → keep everything
2. else `motion.days > 0` → keep segments containing motion
3. else → keep only segments overlapping a **review item**, padded by pre/post capture
4. else → `drop_segment()`

So "record on detection" is not a recording mode, it is a **retention** mode. The cache is also
the only reason pre-capture works: the seconds before a violation are kept because they were
already written before anyone knew a violation was coming.

**Consequence:** a camera with `record.enabled: false` has its segments deleted the instant
they are written. No review item and no violation rule can recover them, so **that camera can
never produce a violation clip**. "Everything off" therefore means *capture on, every retention
window at zero* — not the master switch off. The settings page calls the switch **Capture** for
exactly this reason.

## Violations are review items

Violations are created through Frigate's manual-event API, and reach retention via step 3
above. `TrackedObjectProcessor.create_manual_event` publishes the event onward to the review
pipeline when the source type is `"api"` **or** one of `VIOLATION_SOURCE_TYPES`
(`frigate/violations.py`). The review maintainer's `DetectionTypeEnum.api` branch turns that
into an alert-severity `PendingReviewSegment`, so violation footage is retained by
`record.alerts.retain`.

Two Rasid360-specific behaviours around that:

- The published `manual_info` payload carries `source_type`, which the review maintainer uses
  to set `PendingReviewSegment.is_violation`.
- A segment with `is_violation` set is **exempt from `review.alerts.enabled`**. Switching Alerts
  off on the Review settings page must not silently stop violation evidence being retained,
  since that page is about what appears in the Review pane, not about ticketing.

Before 2026-08-28 the publish was gated on `source_type == "api"` alone, so violations never
created review items at all — see [Known Issues](../health/known-issues.md).

### `alerts.retain.mode` must be `all` for violations

`motion` mode discards sub-segments with no motion. A `no_parking_violation` is a stationary
car and a `no_stop_violation` is a car that has stopped, so motion mode throws away precisely
the footage those rules exist to capture. This was visible in the data: `Road03`, whose rules
are parking and stopping, held 612 recordings where comparable cameras held ~1,700.

## The settings page

`Settings → Cameras → Recording` (`web/src/views/settings/RecordingSettingsView.tsx`).
Global defaults on top, per-camera overrides below, mirroring the merge the config loader
already performs (`frigate/config/config.py` deep-merges the top-level `record:` block into
every camera, with the camera's explicitly-set values winning).

| Behaviour | How |
|---|---|
| Reads override state | `GET /config/file` — the parsed config **file** |
| Reads effective state | `GET /config` — the merged, running config |
| Writes | `PUT /config/set` with `requires_restart: 0` |
| Applies live | `update_topics: config/cameras/<name>/record` for every camera |
| Removes an override | writes `""`, which `update_yaml` treats as "delete this key" |

Three presets — *Violations only*, *Motion buffer*, *Everything* — write the same underlying
fields and leave them editable.

**Why `/config/file` exists.** `GET /config` serves the merged runtime config, so it cannot
answer "did the user set this on the camera, or is it inherited?", and it does not reflect
`config/set` writes until a restart. The rules editor hit the same problem and worked around it
with a single-purpose `/config/violations`; `/config/file` is the general version.
See [Rules Editor](web-rules-editor.md).

**Why `update_topics` exists.** A global `record:` change is merged into every camera, and
`RecordingMaintainer` subscribes per camera (`CameraConfigUpdateEnum.record`). One
`update_topic` cannot describe the change, so `AppConfigSetBody` accepts a list and publishes
to all affected cameras — otherwise a global change would need a restart.

**The page only writes what changed.** The config file is still hand-edited and carries
comments; ruamel re-flows comments around keys it inserts, so writing every field on every save
visibly mangles the file. The save diffs against `/config/file` first.

**Gap: the page does not expose the setting that matters most.** Every field on it lives under
`record:`, but the dominant control over storage is `review.alerts.enabled` /
`review.detections.enabled` — see the next section. A user can set every retention window to
zero on this page and still fill the disk, because review items, not retention windows, decide
what gets written. Either those two switches belong here, or the page needs to say where they
are. The *Violations only* preset has the same problem: it sets `alerts.retain.days: 30`, which
is only affordable once ordinary review items are off.

## What actually drives storage: open review segments

Retention *days* are not the lever people expect. A segment is moved to permanent storage the
moment it overlaps **any** review item; the retention window only decides when it is later
expired. So the volume written is set by how much review activity exists, not by the days
value.

And a review segment does not close while activity continues — `end_time` stays NULL.
`expire_review_segments` filters on `end_time < cutoff`, which NULL never satisfies, so an
**open segment is immortal and pins every recording it overlaps, indefinitely**. On
continuously busy footage — a road with traffic in frame at all times — ordinary person/car
review segments simply never close.

Measured on this deployment (2026-08-28): 21 open detection segments, disk growing at
**220 GB/day**, of which **93% of retained footage overlapped no violation at all**.

The fix is to stop creating ordinary review items, not to shorten retention:

```yaml
review:
  alerts:
    enabled: false
  detections:
    enabled: false
```

Violations are exempt from both switches (`PendingReviewSegment.is_violation`), so this leaves
violation review items and violation footage untouched. After the change: no open segments,
8/8 violations still had footage, and disk growth went flat (22,275 → 22,280 MB over 5 min).

`record.expire_interval` also matters more than it looks. Segments are written first and
deleted at the next expiry pass, so the interval — not the retention window — bounds how much
churn sits on disk. The default 60 minutes held roughly 10 GB here; this deployment uses 10.

## Shipped defaults

`data/frigate-config/config.yml`, as of 2026-08-28:

```yaml
record:
  enabled: true       # capture runs; storage is controlled by the windows below
  expire_interval: 10 # bounds the write churn; see above
  continuous:
    days: 0
  motion:
    days: 0           # was 0.5 -- see below
  alerts:
    retain:
      days: 2         # violations land here; 30 was unaffordable, see above
      mode: all       # `all`, not `motion` -- stationary violations
  detections:
    retain:
      days: 0
      mode: motion

review:               # ordinary review items off -- this is the storage control
  alerts:
    enabled: false
  detections:
    enabled: false
```

`alerts.retain.days` is 2, not 30, because it is still a shared class: every violation gets the
same window. Per-rule retention (`ViolationRuleConfig.retention_days`, currently unused) is what
would let a critical rule keep 30 days while the rest keep 2.

`motion.days` was `0.5` and load-bearing: a 12-hour buffer that existed purely so violation
clips had something to point at, because violations never created review items. The config file
said so in a comment. It is no longer needed.

Schema defaults differ from these — upstream ships `record.enabled: false` with
`continuous.days: 0`, `motion.days: 0`, and `alerts`/`detections` retention at **10** days
(`frigate/config/camera/record.py`).

## Missing footage fails loudly now

`recording_clip` used to write an empty ffmpeg concat playlist when no recordings overlapped
the requested range, producing **HTTP 200, `Content-Type: video/mp4`, zero bytes**. A player
showed a blank frame and nothing reported a failure — which is why 1,484 broken violation clips
went unnoticed. It now returns 404 with a message (`frigate/api/media.py`).

## Related

- [Violation Lifecycle](../concepts/violation-lifecycle.md)
- [Configuration](../operations/configuration.md)
- [Known Issues](../health/known-issues.md)
