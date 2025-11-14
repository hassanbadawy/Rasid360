"""Rule type classes for different violation patterns

Each rule type represents a different pattern of violation detection:
- ObjectLogicRule: Boolean logic on object detection
- ZoneObjectRule: Objects in specific zones with conditions
- ZoneSequenceRule: Vehicle moving through zone sequences
- ActionRule: Invoke predefined Python action
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from .operators import Operator, ConditionParser


class Rule(ABC):
    """Base class for all rule types"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize rule

        Args:
            name: Rule name (unique identifier)
            config: Rule configuration from YAML
        """
        self.name = name
        self.config = config
        self.duration = config.get("duration", 30)
        self.severity = config.get("severity", "medium")
        self.retention_days = config.get("retention_days", 30)
        self.cooldown = config.get("cooldown", 30)
        self.monitor_duration = config.get("monitor_duration", 0)
        self.description = config.get("description", "")

    @abstractmethod
    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate rule against event

        Args:
            event_data: Event data from Frigate
            context: Additional context (state, camera config, etc.)

        Returns:
            True if violation detected, False otherwise
        """
        pass

    @abstractmethod
    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """
        Get the object label for the violation event

        Args:
            event_data: Event data from Frigate

        Returns:
            Object label (e.g., "car", "person")
        """
        pass

    def get_sub_label(self) -> str:
        """Get sub-label for violation event"""
        return self.name

    def get_description(self) -> str:
        """Get human-readable description of rule"""
        return self.config.get("description", self.name)

    def should_create_event(self, object_id: str, context: Dict[str, Any]) -> bool:
        """
        Check if event should be created (cooldown check)

        Args:
            object_id: ID of the object
            context: Context containing violation history

        Returns:
            True if event should be created
        """
        from datetime import datetime, timedelta

        violations_logged = context.get("violations_logged", {})
        key = f"{self.name}:{object_id}"

        if key in violations_logged:
            last_time = violations_logged[key]
            elapsed = (datetime.now() - last_time).total_seconds()
            return elapsed > self.cooldown

        return True


class ObjectLogicRule(Rule):
    """
    Rule based on boolean logic of object detection

    Example:
        condition: "detected(transformer) AND NOT detected(fire_extinguisher)"
        condition: "detected(person, danger_zone) OR detected(vehicle, danger_zone)"
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        condition_str = config.get("condition", "")
        if not condition_str:
            raise ValueError(f"ObjectLogicRule '{name}' missing 'condition'")

        # Parse condition string into operator tree
        parser = ConditionParser()
        self.condition = parser.parse(condition_str)

        # Extract all detected labels for event creation
        self.detected_labels = self._extract_labels(condition_str)

    def _extract_labels(self, condition_str: str) -> List[str]:
        """Extract all object labels from condition"""
        import re
        # Find all detected(...) calls
        matches = re.findall(r"detected\(([^,)]+)", condition_str)
        return [m.strip() for m in matches]

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate condition against event data"""
        return self.condition.evaluate(event_data, context)

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        label = event_data.get("after", {}).get("label", "")

        # If current event label is in our detected labels, use it
        if label in self.detected_labels:
            return label

        # Otherwise use first detected label
        return self.detected_labels[0] if self.detected_labels else "object"


class ZoneObjectRule(Rule):
    """
    Rule for objects in zones with conditions

    Example:
        condition: "in_zone(danger_zone) AND detected(person)"
        condition: "in_zone(zone1) AND (detected(person) OR detected(vehicle))"
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        condition_str = config.get("condition", "")
        if not condition_str:
            raise ValueError(f"ZoneObjectRule '{name}' missing 'condition'")

        # Parse condition
        parser = ConditionParser()
        self.condition = parser.parse(condition_str)

        # Extract labels
        self.detected_labels = self._extract_labels(condition_str)

    def _extract_labels(self, condition_str: str) -> List[str]:
        """Extract all object labels from condition"""
        import re
        matches = re.findall(r"detected\(([^,)]+)", condition_str)
        return [m.strip() for m in matches]

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate condition against event data"""
        return self.condition.evaluate(event_data, context)

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        label = event_data.get("after", {}).get("label", "")

        if label in self.detected_labels:
            return label

        return self.detected_labels[0] if self.detected_labels else "object"


class ZoneSequenceRule(Rule):
    """
    Rule for tracking objects moving through zone sequences

    Example:
        vehicle_types: [car, bus, truck]
        from_zones: [zone1, zone2]
        to_zone: wrongzone
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        self.vehicle_types = config.get("vehicle_types", ["car", "bus", "truck", "motorcycle"])
        self.from_zones = config.get("from_zones", [])
        self.to_zone = config.get("to_zone", "")

        if not self.from_zones:
            raise ValueError(f"ZoneSequenceRule '{name}' missing 'from_zones'")
        if not self.to_zone:
            raise ValueError(f"ZoneSequenceRule '{name}' missing 'to_zone'")

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate zone sequence violation

        Note: This requires state tracking across events, which is handled
        by the DSLViolationDetector action class.
        """
        after = event_data.get("after", {})
        label = after.get("label")

        # Only process configured vehicle types
        if label not in self.vehicle_types:
            return False

        # Get zone sequence history from context
        object_id = after.get("id")
        zone_history = context.get("zone_sequences", {}).get(object_id, [])

        # Check if object came from valid zone and is now in violation zone
        came_from_valid = any(zone in self.from_zones for zone in zone_history)
        in_violation_zone = self.to_zone in zone_history

        return came_from_valid and in_violation_zone

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        return event_data.get("after", {}).get("label", "vehicle")


class ActionRule(Rule):
    """
    Rule that invokes a predefined Python action

    Example:
        action_class: FallDetection
        parameters:
          target_object: person
          floor_zones: [floor_area]
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        self.action_class = config.get("action_class", "")
        self.parameters = config.get("parameters", {})

        if not self.action_class:
            raise ValueError(f"ActionRule '{name}' missing 'action_class'")

        # Action instance will be set by the detector
        self.action_instance = None

    def set_action_instance(self, instance):
        """Set the instantiated action"""
        self.action_instance = instance

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Delegate evaluation to action instance

        Returns:
            True if action detected a violation
        """
        if self.action_instance is None:
            return False

        # Action should have a detect_violation method
        if hasattr(self.action_instance, "detect_violation"):
            return self.action_instance.detect_violation(event_data, context)

        return False

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from action or event data"""
        if self.action_instance and hasattr(self.action_instance, "get_label"):
            return self.action_instance.get_label(event_data)

        return event_data.get("after", {}).get("label", "object")


def create_rule(name: str, rule_config: Dict[str, Any]) -> Rule:
    """
    Factory function to create appropriate rule type

    Args:
        name: Rule name
        rule_config: Rule configuration from YAML

    Returns:
        Rule instance

    Raises:
        ValueError: If rule type is unknown or invalid
    """
    rule_type = rule_config.get("type", "object_logic")

    # Import temporal rules here to avoid circular imports
    from .temporal import SustainedConditionRule, ProximityRule
    from .aspect_ratio_rules import FallDownRule

    rule_classes = {
        "object_logic": ObjectLogicRule,
        "zone_object": ZoneObjectRule,
        "zone_sequence": ZoneSequenceRule,
        "action": ActionRule,
        "sustained_condition": SustainedConditionRule,
        "proximity": ProximityRule,
        "fall_down": FallDownRule,
    }

    rule_class = rule_classes.get(rule_type)
    if not rule_class:
        raise ValueError(f"Unknown rule type: {rule_type}")

    return rule_class(name, rule_config)
