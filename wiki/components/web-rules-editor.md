---
type: component
status: current
sources: [web/src/views/settings/RulesView.tsx, web/src/components/settings/RuleEditDialog.tsx, web/src/types/violation.ts, web/src/pages/Settings.tsx, frigate/api/app.py, web/src/lib/violationRules.ts, frigate/config/camera/violation.py, web/src/components/ui/popover.tsx]
updated: 2026-08-29
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

## Choosing the camera

The dialog carries its own camera selector rather than inheriting the page's. Zones and objects
follow the selection, and saving a rule onto a different camera moves it — the rule is appended
to the destination camera's `violations` and removed from the source in the same `config/set`
write, so there is no window where it exists on both or neither.

The duplicate-name check follows the selected camera too, since rule names only have to be
unique within a camera.

## Objects: the model's labels, not the camera's

The objects control is a multiselect over **every label the detection model can produce**, read
from `config.detectors.<name>.model.labelmap`, grouped into *tracked on this camera* and *other
model objects*. Restricting it to `objects.track` meant a rule could only ever name what the
camera already happened to detect.

Two constraints make that work, both from the config validators:

- `verify_violation_rules` rejects a label not in the camera's `objects.track`. Choosing an
  untracked label therefore **also widens `objects.track`** for that camera in the same write.
  The dialog says so before you save.
- `objects.track` must be read from the config **file**, not `/api/config`. `verify_objects_track`
  strips labels the model cannot produce, and it runs *after* `verify_violation_rules` — so
  rules are validated against the authored list while the runtime view shows the stripped one.
  Reading the runtime list made the dialog offer to re-add labels the config already had.

A selected label the model cannot produce is shown in its own group and flagged: it parses
cleanly and then never fires. See [Known Issues](../health/known-issues.md) #19.

## Rule types in the dialog

Five of the engine's seven types are reachable: `zone_object`, `sustained_condition`,
`zone_sequence`, `fall_down`, and `zone_occupancy` (added 2026-08-29). `object_logic` and
`proximity` remain engine-only.

`zone_occupancy` asks for a zone, what to count (`all`, or one model label), and a minimum
and/or maximum. The form rejects a minimum above a maximum before saving, and the note under it
explains that a counted zone needs a name no other camera uses — because Frigate's count topic
is keyed by zone name alone. The config validator enforces that too, so a clash fails the save
with the clashing camera named.

## The list shows every camera

The page used to show only the rules of the camera picked in the settings header, which meant
most rules were invisible and disabling a camera made its rules look deleted — they were still
in the config and would fire the moment the camera came back.

It now lists every rule on every camera, sorted by camera then name, headed `Camera — Rule`.
Rules on a disabled camera stay listed and are marked. Rule names are only unique *within* a
camera, so the accessible names on the toggle, edit and delete controls are camera-qualified
too; `wrongway` exists on both Road01 and Road04.

## Where the rules come from

**`GET /api/config/violations`**, not `GET /api/config`.

This matters. `/api/config` serves the *running in-memory* config, which does not reflect
`config/set` writes until Frigate restarts. Since the editor saves a camera's whole `violations`
list at once, reading the in-memory copy would write back a stale list and **silently drop any
rule saved since the last restart**. The endpoint (`frigate/api/app.py`) reads the config file
directly and returns `{camera: [rules]}`.

**This is now the special case of a general endpoint.** `GET /api/config/file` returns the
whole parsed config file and exists for exactly the same reason — the Recording settings page
needs file state to tell a per-camera override from an inherited value, which the merged
runtime view cannot express. `/config/violations` is kept because it is what this editor
already calls; new settings pages should use `/config/file`.
See [Recording Retention](recording-retention.md) § The settings page.

## Saving

`PUT /api/config/set` with a body rather than a query string:

```json
{ "requires_restart": 1,
  "config_data": { "cameras": { "Road01": { "violations": [ ... ] } } } }
```

`flatten_config_data` treats a list as a terminal value, so the whole array lands at
`cameras.Road01.violations` in one write.

`requires_restart: 1` means rules take effect only after a restart, and the editor raises a
status-bar message saying so. That is a genuine limitation rather than caution: nothing
subscribes to a violation-rules config topic the way `RecordingMaintainer` subscribes to
`record`. `PUT /config/set` also accepts `update_topics` (plural) now, for a change that has to
reach every camera at once — the Recording page uses it to apply a global change live.

The safety property this buys: **`config_set` validates the resulting file with
`FrigateConfig.parse()` and restores the previous contents on failure.** A rule referencing a
zone that does not exist is rejected and the config is left byte-identical. Verified directly —
a deliberately bad rule returns `success: false` and leaves the file unchanged.

Saved changes need a Frigate restart to take effect, so the view raises a persistent status-bar
message via `addMessage("rules_restart", ...)`, matching `EnrichmentsSettingsView`. Local state
is updated immediately so the list reflects the save without waiting for that restart.

## A dropdown inside a dialog needs `disablePortal`

The object multiselect could not select or deselect anything: the list appeared, but every click
closed it and changed nothing.

A modal Radix `Dialog` sets `pointer-events: none` on `<body>` and re-enables it only on the
dialog content. `PopoverContent` portals to `<body>` by default, so it inherited
`pointer-events: none` — measured directly, the option's computed `pointer-events` was `none`
and `document.elementFromPoint` over an option returned the dialog behind it. Clicks passed
through to the dialog, which Radix read as an outside interaction and closed the popover.

`PopoverContent` takes a `disablePortal` prop, which renders it inside the dialog where pointer
events are live. Any dropdown added inside a dialog needs it.

It is not a z-index problem, which is the obvious first guess — raising the popover above the
dialog changes nothing, because the element is not being covered, it is not accepting pointer
events at all.

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
