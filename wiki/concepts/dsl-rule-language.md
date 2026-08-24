---
type: concept
status: current
sources: [frigate/extras/config.yml, frigate/extras/dsl/rule_types.py, frigate/extras/dsl/operators.py, frigate/extras/dsl/temporal.py, frigate/extras/dsl/aspect_ratio_rules.py, frigate/extras/dsl/validator.py, frigate/extras/DSL_GUIDE.md]
updated: 2026-08-24
---

# DSL Rule Language

The declarative language for expressing violations. This is the design centrepiece of the fork:
**adding a violation type is a YAML edit, not a code change.**

Reference implementation: `frigate/extras/config.yml`.
Author's guide: `frigate/extras/DSL_GUIDE.md` (590 lines).

## Structure: templates + instances

Rules are defined twice over. A **template** under `violation_templates` describes the shape of
a violation with `{placeholder}` parameters. A per-camera **instance** under `cameras.<name>.violations`
fills them in.

```yaml
actions:
  dsl_violations:
    enabled: true
    violation_templates:
      wrong_way:
        type: zone_sequence
        vehicle_types: [car, bus, truck, motorcycle]
        from_zones: "{from}"
        to_zone: "{to}"
        duration: 30
        severity: high
        cooldown: 600
    cameras:
      Road01:
        violations:
          - name: wrongway
            enabled: true
            type: zone_sequence
            from_zones: [zone01, zone02]
            to_zone: wrongzone
```

Every instance carries its own `enabled` flag, so a noisy rule can be switched off per camera
without deleting its configuration.

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
in Frigate's own config, or speed estimation produces nothing. The template comment says so;
nothing enforces it at load time.

## Validation

`validator.py` (337 lines) checks rules at load. `DSLViolationDetector._validate_rules`
(`actions/dsl_violation_detector.py:95`) runs it during startup, so a malformed rule surfaces
as a log error rather than a runtime crash mid-stream.

## Limits worth knowing

- **Zones and labels are not checked against the live Frigate config.** A rule referencing a
  zone that does not exist parses fine and simply never fires. Silent no-ops are the dominant
  failure mode when authoring rules.
- **Rules are now unit tested** — `frigate/test/extras/test_dsl_rules.py` covers the parser,
  the rule factory, evaluation, and cooldown. See [DSL Engine](../components/dsl-engine.md).
- **Rule state is in-memory.** Restarting the extras process clears all zone sequences and
  sustained-condition timers, so in-flight violations are lost.
  [DSL Engine](../components/dsl-engine.md).
