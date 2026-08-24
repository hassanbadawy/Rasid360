---
type: component
status: current
sources: [frigate/analytics_scheduler.py, frigate/app.py, frigate/analytics_db.py]
updated: 2026-08-24
---

# Analytics Scheduler

`frigate/analytics_scheduler.py` (520 lines). A background thread inside the Frigate process
that recomputes every aggregate table on a fixed interval.

## Lifecycle

Started from `FrigateApp.init_database`, **after** the peewee models are bound — the ordering
matters because the scheduler reads `frigate.db` through the `Event` model:

```python
self.db.bind(models)
init_analytics_scheduler(interval_seconds=300, frigate_db=self.db)
```

Stopped in `FrigateApp.stop` via `stop_analytics_scheduler()`, before
`close_analytics_db()`.

Interval is **300 seconds, hardcoded at the call site** — not exposed in Frigate's config schema.

## What it does

`aggregate_all()` runs each pass, calling in sequence:

- `aggregate_ticket_status`
- `aggregate_violations_by_camera`
- `aggregate_violations_by_type`
- `aggregate_violations_hourly`
- `aggregate_violations_by_weekday`
- `aggregate_violations_by_month`
- `aggregate_violations_by_quarter`
- `aggregate_violations_by_year`

Plus two push-style methods called from elsewhere rather than on the timer:
`update_camera_fps(camera_name, fps_data)` and `update_camera_status(...)`.

`aggregate_ticket_status` used to select **every** violation event and count statuses in a
Python loop, materialising the full violation history as peewee model instances every 5 minutes.
**Fixed 2026-08-24**: it groups in SQL on `Event.data["ticket_status"]` and buckets
NULL/unrecognised values into `"new"` over the handful of returned groups.

It also means the ticket chart tracks `Event.data`, **not** `AnalyticsObservation.status` — see
[Events & Observations API](api-events-observations.md).

The fixed status rows it updates are seeded by `init_analytics_db` via `get_or_create`
(`frigate/analytics_db.py:289`), so its `UPDATE ... WHERE status = ?` pattern does match rows.

## The aggregation pattern

Every method follows the same shape. `aggregate_violations_by_camera` is representative:

```python
camera_counts = (Event
    .select(Event.camera, fn.COUNT(Event.id).alias("count"))
    .where(Event.sub_label.is_null(False))
    .group_by(Event.camera))

total_violations = sum(row.count for row in camera_counts)

AnalyticsViolationsByCamera.delete().execute()          # wipe

for row in camera_counts:                                # refill
    AnalyticsViolationsByCamera.create(...)
```

Three properties of this pattern are worth flagging.

**1. Unbounded scan.** `violation_events_clause()` carries no time window. Every pass scans the
entire event history, forever. Cost grows linearly with retention and never resets. At 5-minute
intervals that is 288 full-history scans per day. **Still open.**

**2. The lazy query was re-executed.** `camera_counts` was a peewee query object, iterated for
the `sum`, again in the insert loop, and a third time by `len(list(camera_counts))` — three
round trips per method. **Fixed 2026-08-24**: each aggregate query is materialised with
`list(...)` once.

**3. Delete-all/insert-all holds a write lock** for the duration. **Mitigated 2026-08-24** by
enabling WAL on the analytics database — see [Analytics Database](analytics-database.md).

## What counts as a violation

Every aggregation uses `violation_events_clause()` from `frigate/violations.py`, which requires
**both** a non-null `sub_label` and a Rasid360 marker in `Event.data["type"]`.

The test used to be `sub_label IS NOT NULL` alone. Upstream Frigate writes `sub_label` for
enrichment results too — face recognition and LPR — so **every recognised face and plate was
counted as a violation**, and this deployment has LPR configured. **Fixed 2026-08-24.**

See [Violation Lifecycle](../concepts/violation-lifecycle.md) for how the marker is set.

## Cross-database access

The scheduler reads `frigate.db` and writes `analytics.db` in the same method. It rebinds the
`Event` model per call:

```python
if self.frigate_db and not Event._meta.database.is_closed():
    Event._meta.set_database(self.frigate_db)
```

Mutating a global model's database binding from a background thread is fragile — any concurrent
request-handler use of `Event` shares that binding. It has not been observed to fail *(inferred
from the absence of any related issue or workaround in the code)*, but it is a latent
thread-safety hazard.

## Error handling

Each method wraps its body in `try/except` and logs. A failing aggregation leaves the previous
contents of its table intact — except that the `delete()` may already have run, in which case
the table is left **empty** until the next successful pass. A partial failure therefore shows as
an empty chart rather than a stale one.

## Related

- [Analytics Database](analytics-database.md)
- [Dashboard API](api-dashboard.md)
- [Violation Lifecycle](../concepts/violation-lifecycle.md)
