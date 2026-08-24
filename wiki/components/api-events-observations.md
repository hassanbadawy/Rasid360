---
type: component
status: current
sources: [frigate/api/event.py, frigate/api/defs/request/events_body.py, frigate/api/media.py, frigate/analytics_db.py]
updated: 2026-08-24
---

# Events & Observations API

The ticketing surface, added to `frigate/api/event.py` (+273 lines) and `frigate/api/media.py`
(+204 lines).

## Ticket update on an event

```
POST /api/events/{event_id}/ticket
```

Body — `EventsTicketBody` (`frigate/api/defs/request/events_body.py`):

| Field | Type | Constraint |
|---|---|---|
| `status` | `str` | required, max 50 |
| `assigned_to` | `str?` | max 100 |
| `comments` | `str?` | unbounded |

`status` is typed as a free-form string with no enum constraint, while the frontend
(`SearchDetailDialog.tsx`) restricts it to `new | in_progress | solved | closed | fake` and
`AnalyticsObservation.status` documents the same set. **The API will accept any string.** An
enum on the Pydantic model would move this validation to the boundary where it belongs.

## Observations CRUD

Operating directly on `AnalyticsObservation` in `analytics.db`:

| Route | Purpose |
|---|---|
| `GET /api/observations` | list observations |
| `GET /api/observations/{id}` | fetch one |
| `POST /api/observations` | create |
| `PUT /api/observations/{id}` | update `status`, `notes`, `metadata`; stamps `updated_at` |

Access control is applied correctly here: each handler checks
`observation.camera not in allowed_cameras` before returning or mutating — unlike the dashboard
endpoints ([Camera Access Control](../concepts/camera-access-control.md)).

Also added: a distinct-`sub_label` query over events, used to populate the violation-type filter.

## Evidence image

```
GET /api/events/{event_id}/evidence.jpg[?download=true]
```

In `frigate/api/media.py`. Serves the bbox-annotated image written by the DSL detector:

1. Look up the event; `await require_camera_access(event.camera, request=request)`
2. Resolve `{CLIPS_DIR}/{camera}-{event_id}-viol.jpg`
3. 404 with `{"success": false, "message": "Evidence image not available"}` if absent
4. Otherwise return the JPEG with `Cache-Control: private, max-age=31536000`

`download=true` adds a `Content-Disposition` attachment header.

The 404 path logs the directory listing filtered by event id to aid debugging — useful, though
it does mean a `listdir` of `CLIPS_DIR` on every miss.

Note the filename convention `{camera}-{event_id}-viol.jpg` is **duplicated** between the writer
(`frigate/extras/actions/dsl_violation_detector.py`) and the reader (`frigate/api/media.py`) as
independent f-strings. A shared constant would prevent the two drifting.

## Two records per violation — and only one of them counts

A violation exists twice: as an `Event` row in `frigate.db` and as an `AnalyticsObservation`
row in `analytics.db`. Ticket state can be written through either surface, and **they write to
different places**:

| Surface | Writes to |
|---|---|
| `POST /events/{id}/ticket` | `Event.data` JSON keys — `ticket_status`, `ticket_assigned_to`, `ticket_comments`, `ticket_updated_at`, `ticket_updated_by` |
| `PUT /observations/{id}` | `AnalyticsObservation.status`, `.notes`, `.metadata` |

**Fixed 2026-08-24.** `Event.data` is the system of record — it is what
`AnalyticsScheduler.aggregate_ticket_status` counts — and the two surfaces now write through to
each other:

- `POST /events/{id}/ticket` calls `_sync_observation_ticket(...)` to mirror status and comments
  onto the observation row
- `PUT /observations/{id}` calls `_sync_event_ticket(...)` to mirror status and notes back onto
  `Event.data`

Both are best-effort: failures are logged, never raised, so a successful ticket update is not
reported as a failure because the analytics database was briefly unavailable. An observation
shares its id with its event (`AnalyticsObservation.create(id=event_id, ...)`), so the two are
the same ticket seen through different APIs.

Previously nothing synchronised them, and `aggregate_ticket_status` read only `Event.data` — so
updates made through the observations API were invisible to every chart.

### Audit trail

**Fixed 2026-08-24.** `update_ticket` takes `current_user: dict = Depends(get_current_user)` and
records `current_data["ticket_updated_by"] = current_user["username"]`, matching the precedent in
`frigate/api/review.py`. It previously hardcoded `"admin"` with a `# TODO: Get from auth context`,
so every ticket change was attributed to the same name regardless of who made it.

## Related

- [Violation Lifecycle](../concepts/violation-lifecycle.md)
- [Analytics Database](analytics-database.md)
- [Web Dashboard](web-dashboard.md)
