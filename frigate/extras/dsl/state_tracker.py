"""Generic state tracker for temporal conditions

Provides reusable state management for tracking:
- Object paths through zones
- Condition duration tracking (FOR operator)
- Time proximity tracking (WITHIN operator)
- Object co-occurrence detection
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging


class StateTracker:
    """Generic state tracker for temporal violation detection"""

    def __init__(self, cleanup_timeout: int = 60):
        """
        Initialize state tracker

        Args:
            cleanup_timeout: Seconds before cleaning up inactive objects
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cleanup_timeout = cleanup_timeout

        # Zone sequence tracking
        self.zone_sequences: Dict[str, List[str]] = defaultdict(list)

        # Object data storage
        self.object_data: Dict[str, Dict[str, Any]] = {}

        # Last seen timestamps
        self.last_seen: Dict[str, datetime] = {}

        # Condition start times (for duration tracking)
        self.condition_start: Dict[str, datetime] = {}

        # Detection times (for proximity tracking)
        self.detection_times: Dict[str, List[datetime]] = defaultdict(list)

    def update(self, event_data: Dict[str, Any]):
        """
        Update state with new event data

        Args:
            event_data: Event data from Frigate
        """
        after = event_data.get("after", {})
        object_id = after.get("id")

        if not object_id:
            return

        # Update last seen
        now = datetime.now()
        self.last_seen[object_id] = now

        # Store full object data
        self.object_data[object_id] = after

        # Update zone sequence
        current_zones = after.get("current_zones", [])
        for zone in current_zones:
            if zone not in self.zone_sequences[object_id]:
                self.zone_sequences[object_id].append(zone)
                self.logger.debug(f"Object {object_id} entered zone {zone}")

        # Record detection time
        label = after.get("label")
        camera = after.get("camera")
        key = f"{camera}:{label}"
        self.detection_times[key].append(now)

        # Limit detection times to last 10 entries per label
        if len(self.detection_times[key]) > 10:
            self.detection_times[key] = self.detection_times[key][-10:]

    def get_zone_sequence(self, object_id: str) -> List[str]:
        """Get zone sequence for an object"""
        return self.zone_sequences.get(object_id, [])

    def get_object_data(self, object_id: str) -> Optional[Dict[str, Any]]:
        """Get full object data"""
        return self.object_data.get(object_id)

    def start_condition(self, condition_key: str):
        """
        Mark the start of a condition for duration tracking

        Args:
            condition_key: Unique key for this condition
        """
        if condition_key not in self.condition_start:
            self.condition_start[condition_key] = datetime.now()
            self.logger.debug(f"Condition started: {condition_key}")

    def end_condition(self, condition_key: str):
        """
        Mark the end of a condition

        Args:
            condition_key: Unique key for this condition
        """
        if condition_key in self.condition_start:
            del self.condition_start[condition_key]
            self.logger.debug(f"Condition ended: {condition_key}")

    def get_condition_duration(self, condition_key: str) -> float:
        """
        Get how long a condition has been true

        Args:
            condition_key: Unique key for this condition

        Returns:
            Duration in seconds, or 0 if condition not active
        """
        if condition_key not in self.condition_start:
            return 0.0

        elapsed = datetime.now() - self.condition_start[condition_key]
        return elapsed.total_seconds()

    def check_sustained_condition(
        self, condition_key: str, required_duration: float
    ) -> bool:
        """
        Check if a condition has been sustained for required duration

        Args:
            condition_key: Unique key for this condition
            required_duration: Required duration in seconds

        Returns:
            True if condition sustained for required duration
        """
        duration = self.get_condition_duration(condition_key)
        return duration >= required_duration

    def check_proximity(
        self, label1: str, label2: str, camera: str, within_seconds: float
    ) -> bool:
        """
        Check if two object types were detected within a time window

        Args:
            label1: First object label
            label2: Second object label
            camera: Camera name
            within_seconds: Time window in seconds

        Returns:
            True if both detected within time window
        """
        key1 = f"{camera}:{label1}"
        key2 = f"{camera}:{label2}"

        times1 = self.detection_times.get(key1, [])
        times2 = self.detection_times.get(key2, [])

        if not times1 or not times2:
            return False

        # Check if any two detection times are within the window
        for t1 in times1:
            for t2 in times2:
                if abs((t1 - t2).total_seconds()) <= within_seconds:
                    return True

        return False

    def cleanup(self):
        """Remove old state to prevent memory buildup"""
        cutoff_time = datetime.now() - timedelta(seconds=self.cleanup_timeout)

        # Find objects to remove
        to_remove = [
            obj_id
            for obj_id, last_time in self.last_seen.items()
            if last_time < cutoff_time
        ]

        # Remove from all tracking dicts
        for obj_id in to_remove:
            if obj_id in self.zone_sequences:
                del self.zone_sequences[obj_id]
            if obj_id in self.object_data:
                del self.object_data[obj_id]
            if obj_id in self.last_seen:
                del self.last_seen[obj_id]

            self.logger.debug(
                f"Cleaned up object {obj_id} (not seen for {self.cleanup_timeout}s)"
            )

        # Clean up old condition starts
        for key in list(self.condition_start.keys()):
            if ":" in key:
                obj_id = key.split(":")[0]
                if obj_id in to_remove:
                    del self.condition_start[key]

    def get_statistics(self) -> Dict[str, Any]:
        """Get state tracker statistics"""
        return {
            "active_objects": len(self.last_seen),
            "tracked_sequences": len(self.zone_sequences),
            "active_conditions": len(self.condition_start),
            "tracked_detections": len(self.detection_times),
        }
