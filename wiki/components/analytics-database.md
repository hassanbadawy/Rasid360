---
type: component
status: current
sources: [frigate/analytics_db.py, frigate/app.py, frigate/extras/main.py]
updated: 2026-08-24
---

# Analytics Database

`frigate/analytics_db.py` (301 lines). A **second** SQLite database, separate from `frigate.db`,
holding pre-aggregated analytics and the observation/ticket records.

```python
analytics_db = SqliteDatabase(None)   # bound at runtime
```

## Why separate

Dashboard queries would otherwise scan the events table on every chart render. Instead the
scheduler precomputes small tables and the API reads those. Two consequences: dashboard reads
are cheap and constant-ish, and analytics write load never touches Frigate's operational
database.

The cost is that analytics are **eventually consistent, lagging by up to 5 minutes**.

## Tables

Nine aggregate tables, all rewritten wholesale by the scheduler:

| Model | Grain |
|---|---|
| `AnalyticsTicketStatus` | count per ticket status |
| `AnalyticsViolationsByCamera` | count + percentage per camera |
| `AnalyticsViolationsByType` | count per `sub_label` |
| `AnalyticsViolationsHourly` | hour-of-day heatmap |
| `AnalyticsViolationsByWeekday` | day-of-week |
| `AnalyticsViolationsByMonth` | month |
| `AnalyticsViolationsByQuarter` | quarter |
| `AnalyticsViolationsByYear` | year |
| `AnalyticsCameraFPS` | fps, detection_fps, process_fps, skipped_fps per camera |
| `AnalyticsCameraStatus` | is_enabled / is_online per camera |

Plus the one table that is **not** an aggregate:

### AnalyticsObservation

The violation record and the ticket, in one row. Primary key is a string id.

| Group | Fields |
|---|---|
| Identity | `id`, `camera`, `label`, `sub_label`, `score`, `timestamp` |
| Media | `cleanshot`, `bboxshot`, `thumbnail`, `clip` — stored as API URL paths, not filesystem paths |
| Geometry | `box_x`, `box_y`, `box_width`, `box_height` |
| Ticket | `status` (default `"new"`), `notes` |
| Extra | `metadata` (JSON — carries the DSL rule that fired) |
| Audit | `created_at`, `updated_at` |

Table name: `analytics_observations`.

Media fields hold values like `/api/events/{event_id}/evidence.jpg` — API routes rather than
paths on disk. That keeps the frontend simple but means the rows are only meaningful while the
API is serving.

## Two processes, one file

The database is opened independently by **both** processes, at paths derived differently:

| Process | Path | Source |
|---|---|---|
| Frigate app | `config.database.path` with `frigate.db` → `analytics.db` | `frigate/app.py` — `init_analytics_database` |
| Extras worker | `$ANALYTICS_DB_PATH`, default `/config/analytics.db` | `frigate/extras/main.py` — `_init_analytics_database` |

Both now call the same `init_analytics_db`, so pragmas and seeded rows are identical either way
(**fixed 2026-08-24** — the worker previously called `analytics_db.init()` directly, bypassing
pragmas).

The **paths** are still derived independently and nothing enforces that they agree. If
`config.database.path` is customised without also setting `ANALYTICS_DB_PATH`, the two processes
write to different files, the observations vanish from the dashboard, and nothing errors.

### Concurrency

**Fixed 2026-08-24.** `init_analytics_db` now applies `ANALYTICS_DB_PRAGMAS`:

```python
ANALYTICS_DB_PRAGMAS = {"journal_mode": "wal", "busy_timeout": 5000, "synchronous": "normal"}
```

WAL lets readers proceed during a write, so the scheduler's delete-all/insert-all pass no longer
blocks dashboard reads for its duration; `busy_timeout` makes contending writers wait rather than
fail immediately with "database is locked".

There are at least three concurrent writers: the extras worker inserting observations, the
scheduler thread rewriting aggregates, and API handlers updating tickets. Previously the database
was opened with no pragmas at all, in SQLite's default rollback-journal mode.

## Lifecycle

- Created and bound in `FrigateApp.init_analytics_database`, called from the startup sequence
  after `init_database`
- Torn down by `close_analytics_db()` during `FrigateApp` stop
- `create_tables(..., safe=True)` means schema changes require manual migration — the repo's
  `migrations/` directory covers `frigate.db` only, and there is **no migration path for
  `analytics.db`**

## Related

- [Analytics Scheduler](analytics-scheduler.md) — the only writer of the aggregate tables
- [Dashboard API](api-dashboard.md) — the reader
- [Events & Observations API](api-events-observations.md) — the ticket CRUD
