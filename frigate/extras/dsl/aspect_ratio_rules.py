"""Aspect ratio based rule types

Provides detection based on object bounding box dimensions:
- FallDownRule: Detects when person's width/height ratio exceeds threshold (person lying down)
"""

from typing import Dict, Any, Optional
from .rule_types import Rule
import logging


class FallDownRule(Rule):
    """
    Rule that detects when a person falls down based on bounding box aspect ratio

    When a person is standing, height > width (ratio < 1.0)
    When a person falls down, width > height (ratio > 1.0)

    Example:
        object_type: person
        width_height_ratio: 1.2  # Width must be 1.2x height to trigger
        min_duration: 3  # Must maintain ratio for 3 seconds
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)

        self.object_type = config.get("object_type", "person")
        self.width_height_ratio = config.get("width_height_ratio", 1.0)
        self.min_duration = config.get("min_duration", 0)  # Sustained duration in seconds

        self.logger = logging.getLogger(self.__class__.__name__)

        if self.width_height_ratio <= 0:
            raise ValueError(f"FallDownRule '{name}' must have width_height_ratio > 0")

    def evaluate(self, event_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluate fall down condition

        Returns True if object's width/height ratio exceeds threshold.
        """
        after = event_data.get("after", {})

        # Check object type
        label = after.get("label", "")
        if label != self.object_type:
            return False

        # Get bounding box [x1, y1, x2, y2]
        box = after.get("box")
        if not box or len(box) != 4:
            return False

        x1, y1, x2, y2 = box
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        if height == 0:
            return False

        # Calculate width/height ratio
        current_ratio = width / height

        # Debug logging: always log bbox dimensions for troubleshooting
        object_id = after.get("id", "unknown")
        self.logger.debug(
            f"{self.name} - Object {object_id[-8:]}: "
            f"bbox=({x1},{y1},{x2},{y2}), w={width:.0f}, h={height:.0f}, "
            f"ratio={current_ratio:.2f} (threshold={self.width_height_ratio:.2f})"
        )

        # Check if ratio exceeds threshold
        is_fallen = current_ratio >= self.width_height_ratio

        # If min_duration is set, check sustained condition
        if self.min_duration > 0 and is_fallen:
            object_id = after.get("id", "")
            condition_key = f"{object_id}:{self.name}:ratio"

            state_tracker = context.get("state_tracker")
            if not state_tracker:
                return False

            # Start/update condition tracking
            state_tracker.start_condition(condition_key)

            # Check if sustained for required duration
            sustained = state_tracker.check_sustained_condition(
                condition_key, self.min_duration
            )

            if sustained:
                self.logger.debug(
                    f"Fall detected: {self.name} - ratio={current_ratio:.2f} "
                    f"(threshold={self.width_height_ratio:.2f}) - "
                    f"sustained for {self.min_duration}s"
                )

            return sustained
        else:
            # No duration requirement, trigger immediately
            if is_fallen:
                self.logger.debug(
                    f"Fall detected: {self.name} - ratio={current_ratio:.2f} "
                    f"(threshold={self.width_height_ratio:.2f})"
                )
            return is_fallen

    def get_violation_label(self, event_data: Dict[str, Any]) -> str:
        """Get label from event data"""
        return event_data.get("after", {}).get("label", self.object_type)

    def get_description(self) -> str:
        """Get rule description"""
        if self.description:
            return self.description
        return (
            f"Fall down detection: {self.object_type} with "
            f"width/height ratio >= {self.width_height_ratio:.2f}"
        )
