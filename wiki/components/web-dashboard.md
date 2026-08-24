---
type: component
status: current
sources: [web/src/pages/Dashboard.tsx, web/src/hooks/use-dashboard-data.ts, web/src/hooks/use-violations.ts, web/src/components/overlay/detail/SearchDetailDialog.tsx, web/src/components/filter/ReviewFilterGroup.tsx]
updated: 2026-08-24
---

# Web Dashboard

The operator-facing analytics and ticketing UI.

## Dashboard page

`web/src/pages/Dashboard.tsx` (574 lines). Mounted at `/` — it replaced Live as the app's
landing page ([Navigation & Branding](web-navigation-branding.md)).

Charts, all ECharts:

| Visual | Data |
|---|---|
| Ticket status cards | counts per status, colour-coded |
| Violations by camera | pie |
| Top incidences | bar, violations by type |
| Hourly heatmap | hour-of-day distribution |
| Weekday / Month / Quarter | bar |
| Year | line |

Chart colours are derived from a theme block in the component so they track light/dark mode
([Navigation & Branding](web-navigation-branding.md)).

Camera filtering is **stubbed**: `handleCameraFilter` is commented out with a
`TODO: Add camera filter component once groups are available`. The backend endpoints accept a
`cameras` parameter, but the UI never sends one. Given that the filtered code path is the one
broken by the access-control bug ([Camera Access Control](../concepts/camera-access-control.md)),
this stub is currently what keeps the dashboard working at all.

## Data hooks

`web/src/hooks/use-dashboard-data.ts` (368 lines). One SWR hook per endpoint:

`useTicketStatusData`, `useViolationsByCameraData`, `useViolationsByTypeData`,
`useHourlyHeatmapData`, `useViolationsByWeekdayData`, `useViolationsByMonthData`,
`useViolationsByQuarterData`, `useViolationsByYearData`, `useCameraFPSData`,
`useOfflineCamerasData`.

Each builds `${baseUrl}api/dashboard/...` with an optional query string from a shared
`DashboardFilters` type, and returns `{ data, error, isLoading, mutate }`.

`useCameraFPSData` and `useOfflineCamerasData` back onto `/dashboard/camera/fps` and
`/dashboard/camera/offline`, which returned 500 unconditionally until the access-control fix on
2026-08-24.

## Violation type filter

`web/src/hooks/use-violations.ts` populates the violation-type filter used by
`ReviewFilterGroup`, `SearchFilterGroup`, and `MobileReviewSettingsDrawer`.

**Fixed 2026-08-24.** It now reads a dedicated endpoint:

```ts
useSWR<string[]>("events/violation_types", { dedupingInterval: 60000 })
```

backed by `GET /events/violation_types` in `frigate/api/event.py`, which returns distinct
`sub_label` values for events matching `violation_events_clause()`, scoped to the caller's
cameras.

It previously fetched **1,000 events to the client** and derived distinct `sub_label` values in
JavaScript. That was wasteful, and incorrect at scale: violation types older than the most recent
1,000 events silently vanished from the filter, so the available filters shifted with recent
traffic. It also listed recognised plate numbers as violation types, since it keyed on
`sub_label` alone.

The new route is registered **above** `/events/{event_id}` — FastAPI matches in registration
order, so a static path declared after the parameterised one would never be reached.

## Detail dialog: evidence and tickets

`web/src/components/overlay/detail/SearchDetailDialog.tsx` (+396 lines). The tab set is extended
to:

```ts
const SEARCH_TABS = ["snapshot", "evidence", "video_clip", "tracking_details", "ticket"]
```

**`EvidenceTab`** renders `${baseUrl}api/events/${search?.id}/evidence.jpg`, with an explicit
error state — *"The violation evidence image could not be loaded. This may indicate the evidence
image was not generated for this event."* That is the visible symptom of the 5-second snapshot
polling race in [Violation Lifecycle](../concepts/violation-lifecycle.md) step 6.

**`VideoClipTab`** builds an HLS source from the event window plus `REVIEW_PADDING`:
`${baseUrl}vod/${camera}/${start-pad}:${end+pad}/index.m3u8`.

**`TicketManagementTab`** edits `status` / `assigned_to` / `comments`, with
`TicketStatus = "new" | "in_progress" | "solved" | "closed" | "fake"`. It posts to
`/events/{id}/ticket` — the surface the dashboard actually aggregates from
([Events & Observations API](api-events-observations.md)).

## Related

- [Dashboard API](api-dashboard.md)
- [Navigation & Branding](web-navigation-branding.md)
- [Known Issues](../health/known-issues.md)
