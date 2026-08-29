---
type: component
status: current
sources: [web/src/views/settings/CameraManagementView.tsx, web/src/hooks/use-navigation.ts, web/src/types/rasid360Config.ts, web/themes/theme-rasid360.css, web/src/context/theme-provider.tsx, web/public/locales, web/src/pages/Settings.tsx]
updated: 2026-08-29
---

# Navigation & Branding

The largest change by file count and the smallest by substance. Roughly 500 files, almost
entirely mechanical.

## Route restructure

`web/src/hooks/use-navigation.ts` remaps the information architecture:

| Nav item | Upstream route | Rasid360 route |
|---|---|---|
| Dashboard | — | **`/`** (new, `LuLayoutDashboard`) |
| Live | `/` | `/live` |
| Tickets | `/explore` | `/tickets` |
| Playback | `/review` | `/playback` |
| Face Library | `/faces` | unchanged |
| Classification | `/classification` | unchanged |
| Export | `/export` | unchanged, moved down the order |
| UI Playground | `/playground` | `enabled: false` |

Nav IDs were renumbered to insert `ID_DASHBOARD = 4`, shifting `ID_EXPORT`, `ID_PLAYGROUND`,
`ID_FACE_LIBRARY`, and `ID_CLASSIFICATION` up by one.

The playground was previously gated on `ENV !== "production"`; it is now hard-disabled, and the
`ENV` import was dropped.

Two renames are cosmetic-only: "Review" → "Playback" and "Explore" → "Tickets" change the label
and URL, but the underlying views are still upstream's `EventView` and `SearchView`.

## Type rename

`web/src/types/frigateConfig.ts` → `web/src/types/rasid360Config.ts`, and `FrigateConfig` →
`Rasid360Config` at every use site. Similarly `FrigatePlusSettingsView` →
`Rasid360PlusSettingsView`.

This is the bulk of the 666-file diff. It is also the single largest source of future merge
conflict, because it lands in `web/src` where upstream is most active —
[Fork Relationship](../concepts/fork-relationship.md).

The rename is **incomplete by design boundary**: the Python package remains `frigate/`, the
API client class remains `FrigateAPI`, the database remains `frigate.db`, and the MQTT topic
remains `frigate/events`. Only the TypeScript type layer and user-visible strings were changed.

## Theme

`web/themes/theme-rasid360.css` (163 lines) defines the design tokens, following the shadcn/ui
convention of paired declarations — an `hsl()` form and a bare triplet for Tailwind's
`hsl(var(--token))` composition:

```css
--background: hsl(0, 0%, 100%);
--background: 0 0% 100%;
```

Dark mode support was added alongside, wired through
`web/src/context/theme-provider.tsx`. Logo assets were replaced with a PNG.

## Localisation

Arabic (`web/public/locales/ar/common.json`) gained 284 lines — by far the most substantive
locale work, consistent with the product's apparent deployment target. Every other locale's
`views/settings.json` shows ~50-60 changed lines, which is the mechanical consequence of the
Frigate+ → Rasid360+ settings rename rather than genuine translation work.

Note that new UI strings added by this fork are largely **hardcoded English** rather than routed
through i18n — for example the violation filter label `"Violations (All)"` in
`ReviewFilterGroup.tsx` and the evidence-tab error copy in `SearchDetailDialog.tsx`. For a
product with substantial Arabic localisation, this is an inconsistency worth resolving.

The Recording settings page (2026-08-28) does route everything through i18n: a `recording` block
of ~50 keys was added to `web/public/locales/en/views/settings.json`, plus `menu.recording`.
**English only** — the other locales do not carry the block yet, so those users see the English
fallback. That is the same gap as above, now with the keys already in place to close it.

## Camera enable/disable persists

`Settings → Cameras → Management` toggles `cameras.<name>.enabled` in the config, not just the
runtime state. It used to send only the websocket command, so a camera came back enabled after
any restart — the one thing that switch is used to prevent.

It is deliberately **not** driven by the websocket state. `Dispatcher._on_enabled_command`
refuses `"ON"` unless `enabled_in_config` is true and returns early *without* publishing
`<camera>/enabled/state`, so the websocket can only ever turn a camera off. Once the switch
persisted a camera off, a websocket-driven switch could never turn it back on and would sit
there refusing to move.

So it reads the config, holds an optimistic local value so it responds to the click rather than
to a round trip, and writes with `update_topic` so the change still applies without a restart.
A failed write sends the switch back.

## Settings navigation

`web/src/pages/Settings.tsx` holds the settings nav as three parallel lists that must stay in
sync: `allSettingsViews`, the `settingsGroups` entry that maps a key to a component, and
`CAMERA_SELECT_BUTTON_PAGES` if the page is camera-scoped. A key missing from any one of them
fails silently — the item simply does not render. `recording` was added to all three under the
`cameras` group, between Review and Masks / Zones.

## Related

- [Fork Relationship](../concepts/fork-relationship.md) — merge cost of this change
- [Web Dashboard](web-dashboard.md)
