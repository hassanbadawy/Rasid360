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
