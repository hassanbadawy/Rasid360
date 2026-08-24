---
type: concept
status: current
sources: [frigate/api/auth.py, frigate/api/dashboard.py, frigate/api/event.py, frigate/api/media.py]
updated: 2026-08-24
---

# Camera Access Control

How the new endpoints enforce per-camera permissions — and where that enforcement is currently
broken.

## The upstream model

Frigate scopes access by camera. A user has a role; roles map to allowed camera sets. Two
helpers in `frigate/api/auth.py` express this:

```python
async def get_allowed_cameras_for_filter(request: Request)   # -> list[str], for filtering lists
async def require_camera_access(camera, request)             # -> raises/denies for a single camera
```

`get_allowed_cameras_for_filter` (`frigate/api/auth.py:678`) resolves the current user, reads
`request.app.frigate_config.auth.roles`, and returns the permitted camera names. It returns an
empty list for unauthenticated callers, so a correct call **fails closed**.

Reusing these rather than inventing a parallel permission model was the right call — new
endpoints inherit the existing security model for free.

## Where it is applied correctly

- `GET /api/events/{id}/evidence.jpg` — `await require_camera_access(event.camera, request=request)`
  before reading any file (`frigate/api/media.py`)
- `/api/observations` CRUD — checks `observation.camera not in allowed_cameras` before
  returning or mutating (`frigate/api/event.py`)
- `/api/dashboard/tickets/status` and `/api/dashboard/violations/by-camera` — correctly
  `await` the helper (`dashboard.py:59`, `:155`, `:174`)

## How dashboard endpoints resolve it

**Fixed 2026-08-24.** All ten dashboard endpoints are now `async def` and route through one
shared helper in `frigate/api/dashboard.py`:

```python
async def resolve_camera_filter(
    request: Request, cameras: Optional[str] = None
) -> List[str]:
    allowed = await get_allowed_cameras_for_filter(request)
    if not cameras:
        return list(allowed)
    requested = [c for c in cameras.split(",") if c]
    return [c for c in requested if c in allowed]
```

Two properties make this safe:

**It always returns an explicit list.** Callers apply `Event.camera.in_(camera_list)`
unconditionally rather than guarding on `if camera_list:`. An empty list means "access to
nothing" and correctly yields no rows.

**A requested camera outside the caller's permissions is dropped** rather than widening the
filter.

### What was wrong before

Eight call sites invoked the `async` helper with **two** arguments (it takes one) and without
awaiting it — `dashboard.py` lines 220, 289, 366, 455, 541, 619, 666, 702. Each raised
`TypeError`, which the broad `except Exception` turned into an HTTP 500. `camera/fps` and
`camera/offline` were unconditionally broken; the six chart endpoints broke whenever a `cameras`
filter was applied.

Two traps were stacked there, both now closed:

1. **Access control never ran** on those paths. It failed closed only because the request
   errored out before returning data.

2. **The obvious fix was the dangerous one.** Dropping the second argument without adding
   `await` yields a *coroutine object* — truthy and non-empty — so `if camera_list:` would pass
   and the filter would silently stop restricting anything, turning a visible outage into a
   quiet cross-camera data leak.

The old guarded form was fail-open on an empty list too: with `allowed = []`, `if camera_list:`
skipped the filter and returned every camera's rows. Both behaviours are now covered by
`test_no_camera_access_returns_nothing` and `test_requested_cameras_intersected_with_allowed`
in `frigate/test/http_api/test_http_dashboard.py`.

## Note on the analytics tables

Aggregate tables in `analytics.db` are computed **without** any camera scoping — the scheduler
sees everything. Access control is applied at read time by filtering rows on `camera`. This is
fine for per-camera tables, but any aggregate that has already collapsed the camera dimension
(such as global percentages in `AnalyticsViolationsByCamera.percentage`) is computed over all
cameras and cannot be re-scoped at read time. A restricted user therefore sees percentages
derived from cameras they cannot access.
[Analytics Database](../components/analytics-database.md).
