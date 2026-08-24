---
type: component
status: current
sources: [web/src/views/settings/RulesView.tsx, web/src/components/settings/RuleEditDialog.tsx, web/src/types/violation.ts, web/src/pages/Settings.tsx, frigate/api/app.py]
updated: 2026-08-25
---

# Rules Editor

Settings → Cameras → **Violation Rules**. Camera-scoped UI for authoring violation rules without
hand-editing YAML.

Added 2026-08-25, together with moving rules into the Frigate config
([DSL Rule Language](../concepts/dsl-rule-language.md)).

## Why a form works here

The DSL is expressive, but real usage is narrow. All eleven shipped rules are one of:

- `zone_sequence` — from-zones → to-zone
- `fall_down` — bbox ratio
- `in_zone(X) AND (detected(a) OR detected(b) ...)`

So the editor asks for **a zone and a set of objects** and builds the condition string itself.
Free-text DSL remains behind an *Advanced* toggle for anything the form cannot express.

`RuleEditDialog` builds and parses that shape symmetrically: `buildCondition(zone, objects)`
generates it, `parseCondition()` recovers `{zone, objects}` from an existing rule, and only
treats it as simple if rebuilding reproduces the original string. A hand-written condition
therefore opens in Advanced mode rather than being silently rewritten.

## Where the rules come from

**`GET /api/config/violations`**, not `GET /api/config`.

This matters. `/api/config` serves the *running in-memory* config, which does not reflect
`config/set` writes until Frigate restarts. Since the editor saves a camera's whole `violations`
list at once, reading the in-memory copy would write back a stale list and **silently drop any
rule saved since the last restart**. The endpoint (`frigate/api/app.py`) reads the config file
directly and returns `{camera: [rules]}`.

## Saving

`PUT /api/config/set` with a body rather than a query string:

```json
{ "requires_restart": 1,
  "config_data": { "cameras": { "Road01": { "violations": [ ... ] } } } }
```

`flatten_config_data` treats a list as a terminal value, so the whole array lands at
`cameras.Road01.violations` in one write.

The safety property this buys: **`config_set` validates the resulting file with
`FrigateConfig.parse()` and restores the previous contents on failure.** A rule referencing a
zone that does not exist is rejected and the config is left byte-identical. Verified directly —
a deliberately bad rule returns `success: false` and leaves the file unchanged.

Saved changes need a Frigate restart to take effect, so the view raises a persistent status-bar
message via `addMessage("rules_restart", ...)`, matching `EnrichmentsSettingsView`. Local state
is updated immediately so the list reflects the save without waiting for that restart.

## Validation, three layers deep

| Layer | Catches |
|---|---|
| Dialog | empty/duplicate/malformed names, missing zone or objects — Save stays disabled |
| Pydantic model | fields required by the chosen rule type |
| `verify_violation_rules` | zones and labels that do not exist on that camera |

The third layer is the one that matters most: it is what turned "rule silently never fires" into
a save-time error naming the available zones.

## Wiring

- `web/src/views/settings/RulesView.tsx` — list, toggle, delete, persistence
- `web/src/components/settings/RuleEditDialog.tsx` — type-driven form
- `web/src/types/violation.ts` — mirrors `ViolationRuleConfig`
- Registered in `web/src/pages/Settings.tsx` under the `cameras` group and added to
  `CAMERA_SELECT_BUTTON_PAGES` so the camera picker appears

## Tested

End-to-end in a real browser (Playwright, 11 checks): the view renders, existing rules list with
readable summaries, Save is blocked until valid, the condition is built from zone + object, a
rule created through the UI persists to the config file, survives a reload, and can be deleted
again through the UI.

Two behaviours worth knowing when writing further tests:

- The app strips `?page=` from the URL after load, so `reload()` returns to the default settings
  view — re-navigate explicitly.
- Rule names render through `smart-capitalize`, so `innerText` gives `Wrongway`, not `wrongway`.

## Related

- [DSL Rule Language](../concepts/dsl-rule-language.md) — the fields the form writes
- [Extras Service](extras-service.md) — what consumes the saved rules
