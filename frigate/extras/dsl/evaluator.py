"""Evaluate violation rules against Frigate events

The evaluator takes parsed rules and event data, evaluates each rule,
and returns violation details when rules are triggered.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from collections import defaultdict
from .rule_types import Rule
from .state_tracker import StateTracker


class RuleEvaluator:
    """Evaluator for violation rules"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        # Use StateTracker for temporal state management
        self.state_tracker = StateTracker(cleanup_timeout=60)

        # Violation logging (for cooldown)
        self.violations_logged: Dict[str, datetime] = {}

    def evaluate_event(
        self, event_data: Dict[str, Any], rules: List[Rule]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate event against all rules

        Args:
            event_data: Event data from Frigate MQTT
            rules: List of rules to evaluate

        Returns:
            List of violations detected (each violation is a dict with rule and event info)
        """
        violations = []

        # Update state tracking
        self._update_state(event_data)

        # Build evaluation context
        context = self._build_context(event_data)

        # Evaluate each rule
        for rule in rules:
            try:
                if self._should_evaluate_rule(rule, event_data):
                    if rule.evaluate(event_data, context):
                        # Check cooldown
                        object_id = event_data.get("after", {}).get("id", "")
                        if rule.should_create_event(object_id, context):
                            violation = self._create_violation(rule, event_data, context)
                            violations.append(violation)

                            # Log violation time for cooldown
                            key = f"{rule.name}:{object_id}"
                            self.violations_logged[key] = datetime.now()

            except Exception as e:
                self.logger.error(f"Error evaluating rule '{rule.name}': {e}")
                continue

        # Cleanup old state
        self._cleanup_old_state()

        return violations

    def _should_evaluate_rule(self, rule: Rule, event_data: Dict[str, Any]) -> bool:
        """
        Check if rule should be evaluated for this event

        Args:
            rule: Rule to check
            event_data: Event data

        Returns:
            True if rule should be evaluated
        """
        # For now, evaluate all rules
        # Can add filtering logic here later
        return True

    def _update_state(self, event_data: Dict[str, Any]):
        """
        Update state tracking for temporal rules

        Args:
            event_data: Event data from Frigate
        """
        # Delegate to state tracker
        self.state_tracker.update(event_data)

    def _build_context(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build evaluation context

        Args:
            event_data: Event data from Frigate

        Returns:
            Context dictionary with state and metadata
        """
        object_id = event_data.get("after", {}).get("id", "")

        return {
            "state_tracker": self.state_tracker,
            "zone_sequences": self.state_tracker.zone_sequences,
            "object_data": self.state_tracker.object_data,
            "last_seen": self.state_tracker.last_seen,
            "violations_logged": self.violations_logged,
            "current_object_id": object_id,
            "current_zone_sequence": self.state_tracker.get_zone_sequence(object_id),
        }

    def _create_violation(
        self, rule: Rule, event_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create violation record

        Args:
            rule: Rule that was violated
            event_data: Event data
            context: Evaluation context

        Returns:
            Violation dictionary
        """
        after = event_data.get("after", {})

        return {
            "rule": rule,
            "rule_name": rule.name,
            "camera": after.get("camera", ""),
            "label": rule.get_violation_label(event_data),
            "sub_label": rule.get_sub_label(),
            "object_id": after.get("id", ""),
            "box": after.get("box"),
            "duration": rule.duration,
            "severity": rule.severity,
            "retention_days": rule.retention_days,
            "timestamp": datetime.now(),
            "zone_sequence": context.get("current_zone_sequence", []),
            "description": rule.get_description(),
        }

    def _cleanup_old_state(self):
        """
        Remove old state to prevent memory buildup
        """
        # Delegate to state tracker
        self.state_tracker.cleanup()

    def get_statistics(self) -> Dict[str, Any]:
        """Get evaluator statistics"""
        stats = self.state_tracker.get_statistics()
        stats["total_violations_logged"] = len(self.violations_logged)
        return stats
