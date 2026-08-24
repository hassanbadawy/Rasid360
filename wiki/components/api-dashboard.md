---
type: component
status: current
sources: [frigate/api/dashboard.py, frigate/api/fastapi_app.py, frigate/api/auth.py]
updated: 2026-08-24
---

# Dashboard API

`frigate/api/dashboard.py` (736 lines). Ten read-only endpoints backing the analytics dashboard.
Registered in `frigate/api/fastapi_app.py` alongside the upstream routers.

## Endpoints

| Route | Returns | Source table |
|---|---|---|
| `GET /api/dashboard/tickets/status` | counts by ticket status | `AnalyticsTicketStatus` |
| `GET /api/dashboard/violations/by-camera` | count + percentage per camera | `AnalyticsViolationsByCamera` |
| `GET /api/dashboard/violations/by-type` | count per violation type | `AnalyticsViolationsByType` |
| `GET /api/dashboard/violations/hourly-heatmap` | hour-of-day distribution | `AnalyticsViolationsHourly` |
| `GET /api/dashboard/violations/by-weekday` | day-of-week distribution | `AnalyticsViolationsByWeekday` |
| `GET /api/dashboard/violations/by-month` | monthly totals | `AnalyticsViolationsByMonth` |
| `GET /api/dashboard/violations/by-quarter` | quarterly totals | `AnalyticsViolationsByQuarter` |
| `GET /api/dashboard/violations/by-year` | yearly totals | `AnalyticsViolationsByYear` |
| `GET /api/dashboard/camera/fps` | per-camera fps metrics | `AnalyticsCameraFPS` |
| `GET /api/dashboard/camera/offline` | enabled-but-offline cameras | `AnalyticsCameraStatus` |

Common query parameters on the violation endpoints: `cameras` (comma-separated), `after`,
`before` (unix timestamps), `limit`.

## The dual-path design

Each violation endpoint branches on whether filters were supplied:

```python
if cameras or after or before:
    # live query against frigate.db (Event table)
else:
    # read the pre-aggregated analytics.db table
```

The **unfiltered** path is the fast one, reading a handful of pre-aggregated rows. The
**filtered** path bypasses the aggregates entirely and scans `frigate.db` directly, because the
aggregates have already collapsed the dimensions being filtered on.

This is a defensible design, but it means the two paths can disagree: the aggregate path is up
to 5 minutes stale while the filtered path is live. Applying a filter that selects *all*
cameras can therefore return different numbers than applying no filter at all.

## Response shape

Uniform envelope:

```json
{ "success": true, "data": [ ... ] }
```

Errors return `{"success": false, "message": "..."}` with HTTP 500.

## Access control

All ten endpoints are `async def` and resolve permissions through the shared
`resolve_camera_filter` helper, which always returns an explicit camera list so the filter
applies unconditionally and fails closed. See
[Camera Access Control](../concepts/camera-access-control.md) for the helper and the
arity/await bug fixed on 2026-08-24.

## Silent failure by construction

Every endpoint still wraps its body in `except Exception` and returns a 500 envelope. Combined
with a frontend that renders empty charts on error, backend faults present as "no data" rather
than as faults — which is why the access-control bug survived as long as it did.

Still open: narrow the exception handling to expected database errors, and have the frontend
distinguish *empty* from *errored*. Tracked in [Known Issues](../health/known-issues.md).

## Testing

`frigate/test/http_api/test_http_dashboard.py` covers every route in both branches — the
pre-aggregated path and the live-query path — plus camera scoping, empty-permission
fail-closed behaviour, and the requested-vs-allowed intersection. One status-code assertion per
endpoint is what catches the silent-500 class.

## Related

- [Camera Access Control](../concepts/camera-access-control.md)
- [Analytics Database](analytics-database.md)
- [Web Dashboard](web-dashboard.md) — the consumer
