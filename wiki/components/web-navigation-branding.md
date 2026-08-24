---
type: component
status: current
sources: [web/src/hooks/use-navigation.ts, web/src/types/rasid360Config.ts, web/themes/theme-rasid360.css, web/src/context/theme-provider.tsx, web/public/locales]
updated: 2026-08-24
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

## Related

- [Fork Relationship](../concepts/fork-relationship.md) — merge cost of this change
- [Web Dashboard](web-dashboard.md)
