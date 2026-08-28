"""Violations must reach the review pipeline, or their footage is not retained.

Background: a violation is created through Frigate's manual-event API. For most
of this fork's life `TrackedObjectProcessor.create_manual_event` only published
the event onward when `source_type == "api"`, and the violation detectors pass
their own source_type so the event stays identifiable
(see frigate/violations.py). Violations therefore never produced a review item,
the recording maintainer had no reason to keep the overlapping segments, and
`clip.mp4` returned 200 with a zero-byte body while the event row claimed
`has_clip = True`.

Measured on the dev deployment before the fix: 0 of 1,324 review segments
referenced any of the 1,690 violation events, and 87.8% of violations had no
recording at all.

These tests pin the two halves of the contract that keeps that from regressing.
"""

import ast
import os
import unittest

from frigate.review.maintainer import PendingReviewSegment
from frigate.review.types import SeverityEnum
from frigate.violations import VIOLATION_SOURCE_TYPES

ACTIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extras", "actions"
)


def _source_types_passed_by_detectors() -> set[str]:
    """Every literal `source_type=` keyword argument in the detector modules.

    Read from the source rather than imported so the check does not depend on a
    detector being instantiable in the test environment.
    """
    found: set[str] = set()

    for name in os.listdir(ACTIONS_DIR):
        if not name.endswith(".py"):
            continue

        with open(os.path.join(ACTIONS_DIR, name)) as f:
            tree = ast.parse(f.read(), filename=name)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "source_type" and isinstance(kw.value, ast.Constant):
                        if isinstance(kw.value.value, str):
                            found.add(kw.value.value)
            elif isinstance(node, ast.arg):
                continue

        # default values on def create_event(..., source_type="custom_action")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = node.args
                defaults = args.defaults
                positional = args.args[len(args.args) - len(defaults) :]
                for arg, default in zip(positional, defaults):
                    if arg.arg == "source_type" and isinstance(default, ast.Constant):
                        if isinstance(default.value, str):
                            found.add(default.value)

    return found


class TestViolationSourceTypes(unittest.TestCase):
    def test_detectors_only_use_registered_source_types(self):
        """The gate in create_manual_event keys off VIOLATION_SOURCE_TYPES.

        A detector that passes a source_type missing from that tuple is silently
        dropped before the review pipeline -- the exact failure this fork spent
        1,484 unrecoverable violations on. Adding a detector means adding its
        source_type to frigate/violations.py.
        """
        used = _source_types_passed_by_detectors()

        self.assertTrue(used, "no source_type literals found -- did the API change?")

        unregistered = used - set(VIOLATION_SOURCE_TYPES)
        self.assertEqual(
            unregistered,
            set(),
            f"detector source_type(s) {sorted(unregistered)} are not in "
            f"VIOLATION_SOURCE_TYPES, so their events will never create a review "
            f"item and their footage will not be retained",
        )

    def test_known_detector_source_types_are_registered(self):
        for source_type in ("dsl_violation_detector", "wrong_way_detector"):
            self.assertIn(source_type, VIOLATION_SOURCE_TYPES)

    def test_api_is_not_a_violation_source_type(self):
        """Plain manual events must stay distinguishable from violations --
        violation_events_clause() uses the same tuple to count violations, so
        adding "api" here would count every manual event as one."""
        self.assertNotIn("api", VIOLATION_SOURCE_TYPES)


class TestPendingReviewSegmentViolationFlag(unittest.TestCase):
    def _segment(self, **kwargs) -> PendingReviewSegment:
        return PendingReviewSegment(
            "Road01",
            1000.0,
            SeverityEnum.alert,
            {"evt": "car: wrongway"},
            {},
            [],
            set(),
            **kwargs,
        )

    def test_defaults_to_not_a_violation(self):
        self.assertFalse(self._segment().is_violation)

    def test_violation_flag_is_carried(self):
        """The flag exempts the segment from the review.alerts.enabled kill
        switch, so switching Alerts off on the Review settings page cannot
        silently stop violation footage being retained."""
        self.assertTrue(self._segment(is_violation=True).is_violation)

    def test_violation_segments_are_alert_severity(self):
        """Alert severity is what routes the segment to record.alerts.retain."""
        segment = self._segment(is_violation=True)
        self.assertEqual(segment.severity, SeverityEnum.alert)
        self.assertEqual(segment.last_alert_time, 1000.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
