---
type: component
status: current
sources: [frigate/extras/dsl/evaluator.py, frigate/extras/dsl/state_tracker.py, frigate/extras/dsl/operators.py, frigate/extras/dsl/parser.py, frigate/extras/dsl/rule_types.py, frigate/extras/dsl/temporal.py, frigate/extras/dsl/aspect_ratio_rules.py, frigate/extras/dsl/validator.py]
updated: 2026-08-24
---

# DSL Engine

The implementation behind [DSL Rule Language](../concepts/dsl-rule-language.md). Lives in
`frigate/extras/dsl/`.

| Module | Lines | Responsibility |
|---|---|---|
| `rule_types.py` | 383 | `Rule` ABC, `ObjectLogicRule`, `ZoneObjectRule`, `ZoneSequenceRule`, `ActionRule`, `create_rule()` factory |
| `validator.py` | 337 | Load-time rule validation |
| `state_tracker.py` | 295 | Per-object temporal memory |
| `operators.py` | 265 | `detected()`, `in_zone()`, boolean connectives, `ConditionParser` |
| `parser.py` | 201 | Config → rule objects |
| `evaluator.py` | 179 | Orchestration: state update, context build, rule dispatch |
| `temporal.py` | 140 | `SustainedConditionRule`, `ProximityRule` |
| `aspect_ratio_rules.py` | 121 | Fall detection via bbox width/height |

## Evaluation flow

`RuleEvaluator.evaluate_event` (`evaluator.py:27`) per incoming MQTT event:

1. `_update_state` — feed the event into `StateTracker`
2. `_should_evaluate_rule` — cheap per-rule filtering (camera, label, enabled)
3. `_build_context` — assemble zone sequence, condition durations, detection counts, and a
   reference to the tracker itself
4. `rule.evaluate(event_data, context)` for each candidate rule
5. `_create_violation` on a match
6. `_cleanup_old_state` — delegate to the tracker's TTL sweep

## StateTracker

`state_tracker.py` is where the temporal semantics actually live. Default `cleanup_timeout` is
60 seconds.

| Capability | Methods |
|---|---|
| Zone history per object | `update`, `get_zone_sequence`, `get_object_data` |
| Condition timing | `start_condition`, `end_condition`, `get_condition_duration`, `check_sustained_condition` |
| Consecutive-frame thresholds | `increment_detection_count`, `get_detection_count`, `reset_detection_counter` |
| Frame-time capture | `store_frame_time`, `get_stored_frame_time` |
| Spatial | `check_proximity` |
| Housekeeping | `cleanup`, `get_statistics` |

### Condition keys

State is keyed by composite strings of the form `{object_id}:{rule_name}:{suffix}` — for example
`ZoneSequenceRule` uses `f"{object_id}:{rule.name}:wrong_zone"`. `_create_violation` rebuilds
this key by hand (`evaluator.py:145`) to retrieve the stored frame time:

```python
condition_key = f"{object_id}:{rule.name}:wrong_zone"
stored_frame_time = state_tracker.get_stored_frame_time(condition_key)
```

**The key format is duplicated between the rule class and the evaluator rather than shared.**
If a rule type changes its suffix, the evaluator silently retrieves nothing and falls back to
the current frame time — degrading snapshot accuracy with no error. A shared key-builder
function would remove the coupling.

### Why stored frame time matters

For rules requiring N consecutive detections, the *first* qualifying frame is the one that shows
the violation clearly. The tracker captures it at detection 1; the evaluator retrieves it at
detection N and passes it through to the snapshot handshake described in
[Violation Lifecycle](../concepts/violation-lifecycle.md) step 5.

### Memory behaviour

`cleanup()` evicts entries older than `cleanup_timeout`. Called from `_cleanup_old_state` on
each evaluation pass, so it runs only while events flow. A camera that goes quiet leaves its
state resident until the next event on *any* camera triggers a sweep. Bounded, but not promptly
reclaimed.

## Condition parsing

`ConditionParser` (`operators.py`) turns `"detected(person) AND NOT detected(helmet)"` into a
tree of `Operator` objects:

- `DetectedOperator` — label presence
- `InZoneOperator` — zone membership
- `BooleanOperator` — `AND` / `OR` / `NOT`, with parenthesised grouping

Evaluation is a straightforward recursive walk against the context.

## Validation

`validator.py` runs at load time, invoked from `DSLViolationDetector._validate_rules`. It checks
structural correctness — required fields per rule type, parseable conditions, sane numeric
ranges.

**It does not cross-check against the live Frigate config.** Zone names and object labels are
not verified to exist. A rule naming a nonexistent zone validates cleanly and then never fires.
Given that "silent no-op" is the dominant authoring error, wiring the validator to
`FrigateAPI.get_config()` at startup would be a high-value, low-cost addition.

## Testing

`frigate/test/extras/test_dsl_rules.py` — 17 tests covering the condition parser (each operator,
precedence, parenthesised grouping, invalid syntax), the rule factory and its required-field
validation, `object_logic` and `zone_sequence` evaluation, cooldown suppression, and the
evaluator's per-rule exception isolation.

One is a regression guard for the frame-time handshake: with `min_detections: 3`, the violation
must carry the frame time of the **first** wrong-zone detection, not the one that crossed the
threshold — that is what makes the snapshot show the moment the violation began.

The engine is pure logic over plain dicts, so these run without a camera, database, or container:

```bash
python3 -m pytest frigate/test/extras/test_dsl_rules.py
```

`frigate/extras/test_system.py` remains a manual smoke script, not part of the suite.

## Related

- [DSL Rule Language](../concepts/dsl-rule-language.md) — the authoring surface
- [Extras Service](extras-service.md) — the host process
- [Known Issues](../health/known-issues.md)
