"""Tests for violation rule config parsing and cross-validation.

The point of moving rules onto the camera is that a rule and the zones it
references can be validated together. These assert that a rule naming a
nonexistent zone or an untracked label is a hard config error rather than a
silent no-op.
"""

import copy
import unittest

from frigate.config import FrigateConfig

BASE_CONFIG = {
    "mqtt": {"host": "mqtt"},
    "cameras": {
        "road01": {
            "ffmpeg": {
                "inputs": [{"path": "rtsp://10.0.0.1:554/video", "roles": ["detect"]}]
            },
            "detect": {"height": 1080, "width": 1920, "fps": 5},
            "objects": {"track": ["car", "truck", "person"]},
            "zones": {
                "zone01": {"coordinates": "0,0,1,0,1,1"},
                "wrongzone": {"coordinates": "0,0,1,0,1,1"},
            },
        }
    },
}


def config_with(rules):
    cfg = copy.deepcopy(BASE_CONFIG)
    cfg["cameras"]["road01"]["violations"] = rules
    return FrigateConfig(**cfg)


class TestViolationRuleParsing(unittest.TestCase):
    def test_absent_violations_defaults_to_empty(self):
        cfg = FrigateConfig(**copy.deepcopy(BASE_CONFIG))
        self.assertEqual(cfg.cameras["road01"].violations, [])

    def test_zone_sequence_rule_parses(self):
        cfg = config_with(
            [
                {
                    "name": "wrongway",
                    "type": "zone_sequence",
                    "from_zones": ["zone01"],
                    "to_zone": "wrongzone",
                    "vehicle_types": ["car", "truck"],
                }
            ]
        )
        rule = cfg.cameras["road01"].violations[0]
        self.assertEqual(rule.name, "wrongway")
        self.assertEqual(rule.type.value, "zone_sequence")
        self.assertEqual(rule.cooldown, 30)
        self.assertTrue(rule.enabled)

    def test_condition_rule_parses(self):
        cfg = config_with(
            [
                {
                    "name": "no_parking",
                    "type": "sustained_condition",
                    "condition": "in_zone(zone01) AND (detected(car) OR detected(truck))",
                    "monitor_duration": 10,
                }
            ]
        )
        self.assertEqual(cfg.cameras["road01"].violations[0].monitor_duration, 10)


class TestRequiredFields(unittest.TestCase):
    def test_sustained_condition_needs_monitor_duration(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "sustained_condition",
                        "condition": "in_zone(zone01) AND detected(car)",
                    }
                ]
            )
        self.assertIn("monitor_duration", str(ctx.exception))

    def test_zone_sequence_needs_zones(self):
        with self.assertRaises(Exception) as ctx:
            config_with([{"name": "bad", "type": "zone_sequence", "to_zone": "wrongzone"}])
        self.assertIn("from_zones", str(ctx.exception))

    def test_zone_object_needs_condition(self):
        with self.assertRaises(Exception) as ctx:
            config_with([{"name": "bad", "type": "zone_object"}])
        self.assertIn("condition", str(ctx.exception))

    def test_unknown_type_rejected(self):
        with self.assertRaises(Exception):
            config_with([{"name": "bad", "type": "teleportation"}])


class TestCrossValidation(unittest.TestCase):
    """The silent no-op this whole change exists to prevent."""

    def test_unknown_zone_in_structured_field(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "zone_sequence",
                        "from_zones": ["does_not_exist"],
                        "to_zone": "wrongzone",
                    }
                ]
            )
        self.assertIn("does_not_exist", str(ctx.exception))

    def test_unknown_zone_inside_condition(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "zone_object",
                        "condition": "in_zone(ghost_zone) AND detected(car)",
                    }
                ]
            )
        self.assertIn("ghost_zone", str(ctx.exception))

    def test_untracked_label_in_condition(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "zone_object",
                        "condition": "in_zone(zone01) AND detected(giraffe)",
                    }
                ]
            )
        self.assertIn("giraffe", str(ctx.exception))

    def test_untracked_vehicle_type(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "zone_sequence",
                        "from_zones": ["zone01"],
                        "to_zone": "wrongzone",
                        "vehicle_types": ["spaceship"],
                    }
                ]
            )
        self.assertIn("spaceship", str(ctx.exception))

    def test_duplicate_rule_names_rejected(self):
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "dup",
                        "type": "zone_object",
                        "condition": "in_zone(zone01) AND detected(car)",
                    },
                    {
                        "name": "dup",
                        "type": "zone_object",
                        "condition": "in_zone(zone01) AND detected(person)",
                    },
                ]
            )
        self.assertIn("dup", str(ctx.exception))

    def test_error_names_the_available_zones(self):
        """The message should tell the author what they could have used."""
        with self.assertRaises(Exception) as ctx:
            config_with(
                [
                    {
                        "name": "bad",
                        "type": "zone_object",
                        "condition": "in_zone(typo) AND detected(car)",
                    }
                ]
            )
        message = str(ctx.exception)
        self.assertIn("zone01", message)
        self.assertIn("wrongzone", message)


if __name__ == "__main__":
    unittest.main()


class TestAnyZoneWildcard(unittest.TestCase):
    """`any` is accepted wherever a zone name is, and must not weaken the
    cross-validation that makes a mistyped zone a hard error."""

    def rule(self, from_zones, to_zone):
        return {
            "name": "wrongway",
            "type": "zone_sequence",
            "from_zones": from_zones,
            "to_zone": to_zone,
            "vehicle_types": ["car"],
        }

    def test_any_origin_is_accepted(self):
        cfg = config_with([self.rule(["any"], "wrongzone")])
        self.assertEqual(cfg.cameras["road01"].violations[0].from_zones, ["any"])

    def test_any_destination_is_accepted(self):
        cfg = config_with([self.rule(["zone01"], "any")])
        self.assertEqual(cfg.cameras["road01"].violations[0].to_zone, "any")

    def test_any_on_both_ends_is_accepted(self):
        config_with([self.rule(["any"], "any")])

    def test_any_is_not_reported_as_a_referenced_zone(self):
        """referenced_zones() feeds verify_violation_rules, which would reject
        the rule outright if the wildcard were treated as a zone name."""
        cfg = config_with([self.rule(["any"], "any")])
        self.assertEqual(cfg.cameras["road01"].violations[0].referenced_zones(), set())

    def test_a_real_zone_alongside_any_is_still_checked(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(["any", "nosuchzone"], "wrongzone")])
        self.assertIn("nosuchzone", str(ctx.exception))

    def test_untracked_label_is_still_rejected_with_any(self):
        """The wildcard covers zones only -- the object check is unaffected."""
        rule = self.rule(["any"], "any")
        rule["vehicle_types"] = ["bicycle"]
        with self.assertRaises(ValueError) as ctx:
            config_with([rule])
        self.assertIn("bicycle", str(ctx.exception))


class TestUnsatisfiableConditions(unittest.TestCase):
    """A rule sees one MQTT event, which describes one object, so
    `detected(label)` tests that event's own label. Conditions that read as
    co-presence are therefore either always false or always true, and both are
    worse than an error because nothing complains at runtime."""

    def rule(self, condition):
        return {
            "name": "probe",
            "type": "zone_object",
            "condition": condition,
        }

    def assert_rejected(self, condition, *expected_fragments):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(condition)])
        for fragment in expected_fragments:
            self.assertIn(fragment, str(ctx.exception))

    def test_two_labels_anded_is_rejected(self):
        """Always false -- an event carries one label."""
        self.assert_rejected("detected(car) AND detected(person)", "car, person")

    def test_two_labels_anded_with_zones_is_rejected(self):
        """The zone argument narrows where, it does not add a second object."""
        self.assert_rejected(
            "detected(car, zone01) AND detected(person, zone01)", "car, person"
        )

    def test_negated_detected_is_rejected(self):
        """Always true -- this is the one that silently fires on everything."""
        self.assert_rejected(
            "detected(car) AND NOT detected(person)", "would fire every time"
        )

    def test_rejected_inside_a_deeper_and(self):
        self.assert_rejected("in_zone(z) AND detected(a) AND detected(b)", "a, b")

    def test_rejected_in_one_branch_of_an_or(self):
        self.assert_rejected("(detected(a) AND detected(b)) OR detected(c)", "a, b")

    def test_or_of_two_labels_is_fine(self):
        config_with([self.rule("detected(car) OR detected(person)")])

    def test_or_inside_parentheses_is_fine(self):
        config_with([self.rule("in_zone(zone01) AND (detected(car) OR detected(person))")])

    def test_the_normal_shape_is_fine(self):
        config_with([self.rule("in_zone(zone01) AND detected(car)")])

    def test_same_label_twice_is_fine(self):
        config_with([self.rule("detected(car, zone01) AND detected(car, wrongzone)")])

    def test_not_on_in_zone_is_fine(self):
        """in_zone() is about the current object, so negating it is meaningful."""
        config_with([self.rule("detected(car) AND NOT in_zone(zone01)")])


class TestZoneOccupancy(unittest.TestCase):
    """Occupancy rules read Frigate's own per-zone counts, published to
    `frigate/<zone>/<label>`. That topic is keyed by zone name with no camera in
    it, so a shared zone name would silently sum two cameras."""

    def rule(self, **overrides):
        base = {
            "name": "crowding",
            "type": "zone_occupancy",
            "zone": "zone01",
            "count_label": "car",
            "max_count": 3,
        }
        base.update(overrides)
        return base

    def test_max_count_rule_parses(self):
        cfg = config_with([self.rule()])
        rule = cfg.cameras["road01"].violations[0]
        self.assertEqual(rule.zone, "zone01")
        self.assertEqual(rule.max_count, 3)

    def test_min_count_rule_parses(self):
        cfg = config_with([self.rule(max_count=None, min_count=1)])
        self.assertEqual(cfg.cameras["road01"].violations[0].min_count, 1)

    def test_zone_is_required(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(zone=None)])
        self.assertIn("zone", str(ctx.exception))

    def test_a_threshold_is_required(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(max_count=None)])
        self.assertIn("min_count or max_count", str(ctx.exception))

    def test_impossible_range_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(min_count=5, max_count=2)])
        self.assertIn("can never be satisfied", str(ctx.exception))

    def test_zone_must_exist_on_the_camera(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(zone="nosuchzone")])
        self.assertIn("nosuchzone", str(ctx.exception))

    def test_counted_label_must_be_tracked(self):
        with self.assertRaises(ValueError) as ctx:
            config_with([self.rule(count_label="bicycle")])
        self.assertIn("bicycle", str(ctx.exception))

    def test_all_is_a_wildcard_not_a_label(self):
        """`all` matches Frigate's frigate/<zone>/all topic and must not be
        validated as an object label."""
        config_with([self.rule(count_label="all")])

    def test_shared_zone_name_is_rejected(self):
        """The count topic has no camera in it, so two cameras sharing a zone
        name would have their counts combined."""
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["cameras"]["road02"] = copy.deepcopy(cfg["cameras"]["road01"])
        cfg["cameras"]["road01"]["violations"] = [self.rule()]

        with self.assertRaises(ValueError) as ctx:
            FrigateConfig(**cfg)

        message = str(ctx.exception)
        self.assertIn("zone01", message)
        self.assertIn("road02", message)

    def test_shared_zone_name_is_fine_without_an_occupancy_rule(self):
        """Only occupancy rules read the ambiguous topic; sharing a zone name is
        otherwise legitimate."""
        cfg = copy.deepcopy(BASE_CONFIG)
        cfg["cameras"]["road02"] = copy.deepcopy(cfg["cameras"]["road01"])
        cfg["cameras"]["road01"]["violations"] = [
            {
                "name": "wrongway",
                "type": "zone_sequence",
                "from_zones": ["zone01"],
                "to_zone": "wrongzone",
                "vehicle_types": ["car"],
            }
        ]
        FrigateConfig(**cfg)
