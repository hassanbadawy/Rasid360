"""Unit tests for the DSL violation rule engine.

The engine is pure logic over plain dicts -- no I/O, camera, or database on the
evaluation path -- so rules can be exercised directly by feeding it MQTT-shaped
event payloads.
"""

import time
import unittest

from frigate.extras.dsl.evaluator import RuleEvaluator
from frigate.extras.dsl.operators import ConditionParser
from frigate.extras.dsl.rule_types import (
    ObjectLogicRule,
    ZoneObjectRule,
    ZoneSequenceRule,
    create_rule,
)


def event(
    label="car",
    object_id="obj1",
    camera="Road01",
    current_zones=None,
    entered_zones=None,
    frame_time=1000.0,
    box=None,
    **extra,
):
    """Build an MQTT event payload of the shape Frigate publishes."""
    after = {
        "id": object_id,
        "label": label,
        "camera": camera,
        "current_zones": current_zones or [],
        "entered_zones": entered_zones or (current_zones or []),
        "frame_time": frame_time,
        "box": box or [0, 0, 100, 100],
        **extra,
    }
    return {"before": dict(after), "after": after, "type": "update"}


class TestConditionParser(unittest.TestCase):
    def setUp(self):
        self.parser = ConditionParser()

    def test_detected_matches_label(self):
        op = self.parser.parse("detected(person)")
        self.assertTrue(op.evaluate(event(label="person"), {}))
        self.assertFalse(op.evaluate(event(label="car"), {}))

    def test_in_zone(self):
        op = self.parser.parse("in_zone(no_parking)")
        self.assertTrue(op.evaluate(event(current_zones=["no_parking"]), {}))
        self.assertFalse(op.evaluate(event(current_zones=["street"]), {}))

    def test_and_requires_both(self):
        op = self.parser.parse("detected(car) AND in_zone(no_parking)")
        self.assertTrue(
            op.evaluate(event(label="car", current_zones=["no_parking"]), {})
        )
        self.assertFalse(op.evaluate(event(label="car", current_zones=["street"]), {}))

    def test_or_requires_either(self):
        op = self.parser.parse("detected(car) OR detected(truck)")
        self.assertTrue(op.evaluate(event(label="truck"), {}))
        self.assertFalse(op.evaluate(event(label="person"), {}))

    def test_not_negates(self):
        op = self.parser.parse("NOT detected(helmet)")
        self.assertTrue(op.evaluate(event(label="person"), {}))
        self.assertFalse(op.evaluate(event(label="helmet"), {}))

    def test_parenthesised_grouping(self):
        # The zone must hold regardless of which vehicle type matched.
        op = self.parser.parse(
            "in_zone(no_parking) AND (detected(car) OR detected(truck))"
        )
        self.assertTrue(
            op.evaluate(event(label="truck", current_zones=["no_parking"]), {})
        )
        self.assertFalse(
            op.evaluate(event(label="truck", current_zones=["street"]), {})
        )
        self.assertFalse(
            op.evaluate(event(label="person", current_zones=["no_parking"]), {})
        )

    def test_invalid_syntax_raises(self):
        with self.assertRaises(ValueError):
            self.parser.parse("detected(")


class TestRuleFactory(unittest.TestCase):
    def test_creates_each_type(self):
        cases = {
            "object_logic": {
                "type": "object_logic",
                "condition": "detected(person)",
            },
            "zone_object": {
                "type": "zone_object",
                "condition": "in_zone(z) AND detected(person)",
            },
            "zone_sequence": {
                "type": "zone_sequence",
                "from_zones": ["a"],
                "to_zone": "b",
            },
        }
        expected = {
            "object_logic": ObjectLogicRule,
            "zone_object": ZoneObjectRule,
            "zone_sequence": ZoneSequenceRule,
        }
        for name, cfg in cases.items():
            rule = create_rule(name, cfg)
            self.assertIsInstance(rule, expected[name], name)

    def test_zone_sequence_requires_zones(self):
        with self.assertRaises(ValueError):
            create_rule("bad", {"type": "zone_sequence", "to_zone": "b"})
        with self.assertRaises(ValueError):
            create_rule("bad", {"type": "zone_sequence", "from_zones": ["a"]})


class TestObjectLogicRule(unittest.TestCase):
    def setUp(self):
        self.evaluator = RuleEvaluator()
        self.rule = create_rule(
            "missing_helmet",
            {
                "type": "object_logic",
                "condition": "detected(person) AND NOT detected(helmet)",
                "duration": 30,
                "severity": "critical",
                "cooldown": 0,
            },
        )

    def test_fires_when_condition_holds(self):
        found = self.evaluator.evaluate_event(event(label="person"), [self.rule])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["rule_name"], "missing_helmet")
        self.assertEqual(found[0]["severity"], "critical")

    def test_silent_when_condition_fails(self):
        found = self.evaluator.evaluate_event(event(label="helmet"), [self.rule])
        self.assertEqual(found, [])


class TestZoneSequenceRule(unittest.TestCase):
    """Wrong-way detection: a vehicle entering the violation zone having come
    from a legitimate one."""

    def setUp(self):
        self.evaluator = RuleEvaluator()
        self.rule = create_rule(
            "wrongway",
            {
                "type": "zone_sequence",
                "vehicle_types": ["car", "truck"],
                "from_zones": ["zone01", "zone02"],
                "to_zone": "wrongzone",
                "duration": 30,
                "severity": "high",
                "cooldown": 0,
            },
        )

    def test_fires_on_valid_then_violation_zone(self):
        # Establish history in a legitimate zone first.
        self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1000.0), [self.rule]
        )
        found = self.evaluator.evaluate_event(
            event(current_zones=["wrongzone"], frame_time=1001.0), [self.rule]
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["rule_name"], "wrongway")

    def test_silent_without_valid_origin(self):
        # Straight into the violation zone -- no prior legitimate zone, so this
        # is not a wrong-way movement.
        found = self.evaluator.evaluate_event(
            event(current_zones=["wrongzone"]), [self.rule]
        )
        self.assertEqual(found, [])

    def test_ignores_unconfigured_label(self):
        self.evaluator.evaluate_event(
            event(label="person", current_zones=["zone01"]), [self.rule]
        )
        found = self.evaluator.evaluate_event(
            event(label="person", current_zones=["wrongzone"]), [self.rule]
        )
        self.assertEqual(found, [])

    def test_uses_first_frame_time_not_latest(self):
        """The snapshot must show the moment the violation began.

        Regression guard for the frame-time handshake: the stored frame_time from
        the first qualifying detection is what reaches the event, not the frame
        time of the event that crossed the threshold.
        """
        rule = create_rule(
            "wrongway_threshold",
            {
                "type": "zone_sequence",
                "vehicle_types": ["car"],
                "from_zones": ["zone01"],
                "to_zone": "wrongzone",
                "min_detections": 3,
                "cooldown": 0,
            },
        )
        self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1000.0), [rule]
        )
        for i, ft in enumerate([1001.0, 1002.0, 1003.0]):
            found = self.evaluator.evaluate_event(
                event(current_zones=["wrongzone"], frame_time=ft), [rule]
            )
        self.assertEqual(len(found), 1, "threshold should be reached on 3rd detection")
        self.assertEqual(
            found[0]["frame_time"],
            1001.0,
            "violation should carry the first wrong-zone frame, not the last",
        )


class TestZoneSequenceAnyZone(unittest.TestCase):
    """`any` is a wildcard meaning "any zone on this camera".

    Added so the rules editor can offer an Any option without the author having
    to tick every zone, and without a rule silently never firing because a zone
    was added to the camera later and not to the rule.
    """

    def setUp(self):
        self.evaluator = RuleEvaluator()

    def rule(self, from_zones, to_zone):
        return create_rule(
            "anyrule",
            {
                "type": "zone_sequence",
                "vehicle_types": ["car"],
                "from_zones": from_zones,
                "to_zone": to_zone,
                "duration": 30,
                "severity": "high",
                "cooldown": 0,
            },
        )

    def test_any_origin_accepts_a_zone_the_rule_never_named(self):
        r = self.rule(["any"], "wrongzone")
        self.evaluator.evaluate_event(
            event(current_zones=["some_new_zone"], frame_time=1000.0), [r]
        )
        found = self.evaluator.evaluate_event(
            event(current_zones=["wrongzone"], frame_time=1001.0), [r]
        )
        self.assertEqual(len(found), 1)

    def test_any_origin_still_requires_having_been_somewhere(self):
        """Otherwise `from_zones: [any]` would fire on an object that appeared
        directly in the destination, which is not a movement."""
        r = self.rule(["any"], "wrongzone")
        found = self.evaluator.evaluate_event(
            event(current_zones=["wrongzone"], frame_time=1000.0), [r]
        )
        self.assertEqual(found, [])

    def test_any_destination_fires_on_entering_any_zone(self):
        r = self.rule(["zone01"], "any")
        self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1000.0), [r]
        )
        found = self.evaluator.evaluate_event(
            event(current_zones=["zone09"], frame_time=1001.0), [r]
        )
        self.assertEqual(len(found), 1)

    def test_any_destination_needs_a_zone(self):
        r = self.rule(["zone01"], "any")
        self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1000.0), [r]
        )
        found = self.evaluator.evaluate_event(
            event(current_zones=[], frame_time=1001.0), [r]
        )
        self.assertEqual(found, [])

    def test_any_to_any_requires_actual_movement(self):
        """With both ends wildcarded the rule would otherwise fire on any object
        sitting in any zone."""
        r = self.rule(["any"], "any")
        self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1000.0), [r]
        )
        stationary = self.evaluator.evaluate_event(
            event(current_zones=["zone01"], frame_time=1001.0), [r]
        )
        self.assertEqual(stationary, [])

        moved = self.evaluator.evaluate_event(
            event(current_zones=["zone02"], frame_time=1002.0), [r]
        )
        self.assertEqual(len(moved), 1)

    def test_named_zones_are_unaffected(self):
        """The wildcard must not loosen an explicit rule."""
        r = self.rule(["zone01"], "wrongzone")
        self.evaluator.evaluate_event(
            event(current_zones=["zone02"], frame_time=1000.0), [r]
        )
        found = self.evaluator.evaluate_event(
            event(current_zones=["wrongzone"], frame_time=1001.0), [r]
        )
        self.assertEqual(found, [])


class TestSpeedThreshold(unittest.TestCase):
    """speed_threshold narrows a sustained condition to over-limit objects.

    Frigate reports average_estimated_speed as 0 unless the zone sets
    `distances`, so an unconfigured zone can never trip a speed rule.

    Note sustained conditions are timed on the wall clock
    (StateTracker.start_condition uses datetime.now()), not on the event's
    frame_time -- so these tests use a short real duration rather than advancing
    frame_time, which has no effect on the timer.
    """

    SUSTAIN = 0.05

    def rule(self, **overrides):
        config = {
            "type": "sustained_condition",
            "condition": "in_zone(speed_zone) AND detected(car)",
            "monitor_duration": self.SUSTAIN,
            "speed_threshold": 80,
            "cooldown": 0,
        }
        config.update(overrides)
        return create_rule("speeding", config)

    def sustain(self, evaluator, rule, **event_kwargs):
        """Feed the rule until the sustain window has really elapsed."""
        found = evaluator.evaluate_event(
            event(current_zones=["speed_zone"], **event_kwargs), [rule]
        )
        time.sleep(self.SUSTAIN * 2)
        return evaluator.evaluate_event(
            event(current_zones=["speed_zone"], **event_kwargs), [rule]
        )

    def test_over_threshold_fires(self):
        found = self.sustain(
            RuleEvaluator(), self.rule(), average_estimated_speed=95
        )
        self.assertEqual(len(found), 1)

    def test_under_threshold_never_fires(self):
        found = self.sustain(
            RuleEvaluator(), self.rule(), average_estimated_speed=40
        )
        self.assertEqual(found, [])

    def test_missing_speed_treated_as_zero(self):
        """A zone without `distances` reports no speed -- must not fire."""
        found = self.sustain(RuleEvaluator(), self.rule())
        self.assertEqual(found, [])

    def test_without_threshold_speed_is_ignored(self):
        rule = self.rule(speed_threshold=None)
        rule.speed_threshold = None
        found = self.sustain(RuleEvaluator(), rule)
        self.assertEqual(len(found), 1)


class TestCooldown(unittest.TestCase):
    def test_cooldown_suppresses_repeat(self):
        evaluator = RuleEvaluator()
        rule = create_rule(
            "restricted",
            {
                "type": "zone_object",
                "condition": "in_zone(vault) AND detected(person)",
                "cooldown": 600,
            },
        )
        payload = event(label="person", current_zones=["vault"])

        first = evaluator.evaluate_event(payload, [rule])
        self.assertEqual(len(first), 1, "first occurrence should fire")

        second = evaluator.evaluate_event(payload, [rule])
        self.assertEqual(second, [], "repeat within cooldown should be suppressed")


class TestEvaluatorIsolatesRuleFailures(unittest.TestCase):
    def test_one_bad_rule_does_not_stop_the_others(self):
        class Exploding:
            name = "boom"
            type = "object_logic"

            def evaluate(self, event_data, context):
                raise RuntimeError("rule blew up")

        evaluator = RuleEvaluator()
        good = create_rule(
            "ok",
            {"type": "object_logic", "condition": "detected(person)", "cooldown": 0},
        )
        found = evaluator.evaluate_event(event(label="person"), [Exploding(), good])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["rule_name"], "ok")


if __name__ == "__main__":
    unittest.main()
