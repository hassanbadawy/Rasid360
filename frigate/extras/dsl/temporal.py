"""Temporal operators and rule types

Provides advanced temporal violation detection:
- SustainedConditionRule: Condition must be true FOR N seconds
- ProximityRule: Two events must occur WITHIN N seconds
- SequenceRule: Events must occur in order with timing constraints
"""

from typing import Dict, Any, Optional
from .rule_types import Rule
from .operators import ConditionParser


class SustainedConditionRule(Rule):
    """
    Rule that triggers when a condition is sustained for a duration

    Example:
        condition: "detected(heavy_equipment) AND NOT detected(flagman)"
        monitor_duration: 30  # Must be true for 30 seconds
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        condition_str = config.get("condition", "")
        if not condition_str:
            raise ValueError(f"SustainedConditionRule '{name}' missing 'condition'")

        # Parse condition
        parser = ConditionParser()
        self.condition = parser.parse(condition_str)

        # Monitor duration (how long condition must be true)
        self.monitor_duration = config.get("monitor_duration", 0)
        if self.monitor_duration <= 0:
            raise ValueError(
                f"SustainedConditionRule '{name}' must have monitor_duration > 0"
            )

        # Extract labels
        self.detected_labels = self._extract_labels(condition_str)

    def _extract_labels(self, condition_str: str) -> list:
        """Extract all object labels from condition"""
        import re

        matches = re.findall(r"detected\(([^,)]+)", condition_str)
        return [m.strip() for m in matches]

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate sustained condition

        Returns True if condition has been sustained for required duration.
        """
        # Check if condition is currently true
        is_true = self.condition.evaluate(event_data, context)

        object_id = event_data.get("after", {}).get("id", "")
        condition_key = f"{object_id}:{self.name}"

        # Get state tracker from context
        state_tracker = context.get("state_tracker")
        if not state_tracker:
            return False

        if is_true:
            # Start tracking if not already
            state_tracker.start_condition(condition_key)

            # Check if sustained for required duration
            return state_tracker.check_sustained_condition(
                condition_key, self.monitor_duration
            )
        else:
            # Condition is false, reset tracking
            state_tracker.end_condition(condition_key)
            return False

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        label = event_data.get("after", {}).get("label", "")

        if label in self.detected_labels:
            return label

        return self.detected_labels[0] if self.detected_labels else "object"


class ProximityRule(Rule):
    """
    Rule that triggers when two objects are detected within a time window

    Example:
        first_object: heavy_equipment
        second_object: person
        within: 5  # Must occur within 5 seconds
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        self.first_object = config.get("first_object")
        self.second_object = config.get("second_object")
        self.within = config.get("within", 10)

        if not self.first_object:
            raise ValueError(f"ProximityRule '{name}' missing 'first_object'")
        if not self.second_object:
            raise ValueError(f"ProximityRule '{name}' missing 'second_object'")

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate proximity condition

        Returns True if both objects detected within time window.
        """
        camera = event_data.get("after", {}).get("camera", "")

        # Get state tracker from context
        state_tracker = context.get("state_tracker")
        if not state_tracker:
            return False

        # Check proximity
        return state_tracker.check_proximity(
            self.first_object, self.second_object, camera, self.within
        )

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        label = event_data.get("after", {}).get("label", "")

        # Prefer current event label if it matches one of our objects
        if label in [self.first_object, self.second_object]:
            return label

        # Otherwise use first object
        return self.first_object
