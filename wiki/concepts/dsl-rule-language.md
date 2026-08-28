---
type: concept
status: current
sources: [frigate/extras/config.yml, frigate/extras/dsl/rule_types.py, frigate/extras/dsl/operators.py, frigate/extras/dsl/temporal.py, frigate/extras/dsl/aspect_ratio_rules.py, frigate/extras/dsl/validator.py, frigate/extras/DSL_GUIDE.md]
updated: 2026-08-29
---

# DSL Rule Language

The declarative language for expressing violations. This is the design centrepiece of the fork:
**adding a violation type is a YAML edit, not a code change.**

Reference implementation: `frigate/extras/config.yml`.
Author's guide: `frigate/extras/DSL_GUIDE.md` (590 lines).

## Where rules live

**Rules live in the Frigate config, under `cameras.<name>.violations`** (moved there
2026-08-25). They are edited from Settings → Cameras → Violation Rules
([Rules Editor](../components/web-rules-editor.md)) and modelled by `ViolationRuleConfig` in
`frigate/config/camera/violation.py`.

That placement is what makes validation possible: a rule and the zones it references are parsed
as one object, so `verify_violation_rules` (`frigate/config/config.py`) can reject a rule naming
a zone or label that does not exist on that camera. Previously rules sat in
`frigate/extras/config.yml`, read by a separate process with no view of the camera config, and a
bad zone name was a silent no-op.

`frigate/extras/config.yml` is still read as a **fallback** for cameras with no rules in the
Frigate config, so an unmigrated deployment keeps working. The worker logs a warning naming any
camera still using it.

```yaml
cameras:
  Road01:
    zones:
      zone01: { coordinates: ... }
      wrongzone: { coordinates: ... }
    objects:
      track: [car, bus, truck, motorcycle]
    violations:
      - name: wrongway
        enabled: true
        type: zone_sequence
        vehicle_types: [car, bus, truck, motorcycle]
        from_zones: [zone01, zone02]
        to_zone: wrongzone
        duration: 30
        severity: high
        cooldown: 600
```

Every rule carries its own `enabled` flag, so a noisy rule can be switched off without deleting
its configuration.

## Conditions cannot express co-presence

A rule is evaluated against **one MQTT event, which describes one object**, and
`detected(label)` tests only that event's own label. Two conditions that read as co-presence are
therefore rejected at config-parse time, because both are worse than an error:

| Condition | What it actually does |
|---|---|
| `detected(a) AND detected(b)` | **always false** — an event carries one label |
| `detected(a) AND NOT detected(b)` | **always true** — `detected(b)` is always false, so `NOT` of it is always true. Reads as "a without b", fires on every a |

The second is the dangerous one and was authorable until 2026-08-29. `unsatisfiable_condition()`
in `frigate/config/camera/violation.py` now rejects both, with the same check mirrored in the
rules editor (`web/src/lib/violationRules.ts`) so it fails before the round trip.

What stays legal: `OR` between labels, the same label twice, a zone-scoped
`detected(label, zone)`, and `NOT in_zone(...)` — negating a zone is meaningful because
`in_zone` is about the current object.

Genuine co-presence ("heavy equipment without a flagman") needs a rule type that keeps state
across events. `ProximityRule` is the existing primitive — it asks whether two labels were seen
on a camera within N seconds — but it is camera-wide rather than zone-scoped, has no negated
form, and is not exposed in the editor.

## `any` — the zone wildcard

`any` is accepted wherever a zone name is, in both `from_zones` and `to_zone`, and means "any
zone on this camera". It exists so a rule does not have to enumerate every zone, and does not
silently stop covering a zone added to the camera later.

```yaml
from_zones: [any]     # came from anywhere it has since left
to_zone: any          # entered any zone
```

The semantics are movement-based, not presence-based, because `StateTracker` appends an
object's *current* zones to its history before rules evaluate — so "has it been in a zone" is
always true and would make the wildcard fire on any detection:

| Rule | Fires when |
|---|---|
| `from_zones: [any]` | history holds a zone the object is **no longer** in |
| `to_zone: any` | the object is in **some** zone now |
| both `any` | both of the above — i.e. it actually moved between zones |

A named zone is unaffected: `from_zones: [zone01]` still requires `zone01` specifically.

`referenced_zones()` skips the wildcard, so `verify_violation_rules` does not treat `any` as a
missing zone — but a real zone name alongside it is still checked, and a typo is still a hard
config error.

`ANY_ZONE` is defined once in `frigate/config/camera/violation.py` and imported by the engine.

## Legacy: templates

The old `frigate/extras/config.yml` also defined `violation_templates` with `{placeholder}`
parameters. No shipped camera rule actually referenced a template by name — each spelled its
fields out in full — and the config model does not implement templating.

## Rule types

| `type` | Fires when | Implemented in |
|---|---|---|
| `object_logic` | A boolean expression over detected labels holds | `rule_types.py` — `ObjectLogicRule` |
| `zone_object` | A given object is present in a given zone | `rule_types.py` — `ZoneObjectRule` |
| `zone_sequence` | An object moves from one of `from_zones` into `to_zone` | `rule_types.py` — `ZoneSequenceRule` |
| `sustained_condition` | A condition holds continuously for `monitor_duration` | `temporal.py` — `SustainedConditionRule` |
| `fall_down` | A person's bbox width/height ratio exceeds a threshold for a duration | `aspect_ratio_rules.py` |
| `proximity` | Two objects are within a distance of each other | `temporal.py` — `ProximityRule` |

All descend from the `Rule` ABC in `rule_types.py`; `create_rule()` is the factory that maps
the `type` string to a class.

Note `proximity` is implemented but is not used by any template in the shipped `config.yml`.

## Condition expressions

The `condition` field takes a small boolean expression, parsed by `ConditionParser` in
`operators.py`:

```
detected(person) AND NOT detected(helmet)
in_zone(no_parking) AND (detected(car) OR detected(truck))
```

Two primitives, three connectives:

| Primitive | Meaning | Class |
|---|---|---|
| `detected(label)` | An object with this label is present | `DetectedOperator` |
| `in_zone(zone)` | The object is currently inside this zone | `InZoneOperator` |

`AND`, `OR`, `NOT` are handled by `BooleanOperator`. Parenthesised grouping is supported.

This is deliberately small. It is not a general expression language — there is no arithmetic,
no comparison operators, no attribute access. Numeric thresholds are expressed as dedicated
fields (`speed_threshold`, `width_height_ratio`) rather than inside the condition string.

## Common fields

| Field | Meaning |
|---|---|
| `name` | Instance identifier; becomes part of the event's `sub_label` |
| `type` | Selects the rule class |
| `description` | Human-readable; carried into the violation record |
| `duration` | Length of the synthetic Frigate event created, in seconds |
| `severity` | `low` / `medium` / `high` / `critical` — metadata only, no behaviour attached |
| `cooldown` | Seconds before the same rule can fire again for the same object |
| `monitor_duration` | For `sustained_condition` — how long the condition must hold |
| `retention_days` | Passed into the violation record |

**`cooldown` is the main tuning knob against duplicate alerts.** The shipped config sets it to
600s with an explicit comment that this is a testing value: *"for real camera feed make it
number less than 60 sec we made it high to avoid duplicate alerts in testing"*. Anyone
deploying this for real needs to revisit every cooldown.

## The shipped templates

`config.yml` ships six, all parameterised:

- **`wrong_way`** — `zone_sequence`, vehicle moves from valid zones into a prohibited one
- **`missing_safety_equipment`** — `object_logic`, `detected({hazard}) AND NOT detected({safety})`
- **`restricted_zone`** — `zone_object`, objects present in a zone they should not be
- **`fall_detection`** — `fall_down`, person bbox ratio exceeds `{ratio}` for `{duration}`
- **`stationary_vehicle`** — `sustained_condition`, vehicle in a no-parking zone for `{duration}`
- **`speed_limit`** — `sustained_condition` plus `speed_threshold`, riding on Frigate's built-in
  speed estimation

`speed_limit` has a hard prerequisite: **the zone must be configured with a `distances` field**
in the camera config, or Frigate's speed estimation reports 0 and the rule can never fire.
`Road03.speed_estimation` has it set.

`speed_threshold` was accepted but **ignored** by the engine until 2026-08-25 — a speed rule
silently degraded to "vehicle present in zone for `monitor_duration`", firing at any speed. It is
now implemented in `SustainedConditionRule`: the condition only accumulates while
`average_estimated_speed` exceeds the threshold.

## Validation

`validator.py` (337 lines) checks rules at load. `DSLViolationDetector._validate_rules`
(`actions/dsl_violation_detector.py:95`) runs it during startup, so a malformed rule surfaces
as a log error rather than a runtime crash mid-stream.

## Limits worth knowing

- **Zones and labels are now validated.** A rule referencing a zone or object that does not
  exist on its camera is a config error naming the available zones, not a silent no-op. This was
  the dominant authoring failure mode.
- **Sustained conditions are timed on the wall clock**, not on the event's `frame_time`
  (`StateTracker.start_condition` uses `datetime.now()`), so `monitor_duration` measures real
  seconds between MQTT updates.
- **Rules are now unit tested** — `frigate/test/extras/test_dsl_rules.py` covers the parser,
  the rule factory, evaluation, and cooldown. See [DSL Engine](../components/dsl-engine.md).
- **Rule state is in-memory.** Restarting the extras process clears all zone sequences and
  sustained-condition timers, so in-flight violations are lost.
  [DSL Engine](../components/dsl-engine.md).
