"""Wrong-way vehicle detection action"""

from typing import Dict, Any, List
from collections import defaultdict
from datetime import datetime, timedelta
from .base_action import BaseAction


class WrongWayDetection(BaseAction):
    """
    Detect vehicles moving from valid zones into violation zone

    Example: Vehicle moves from zone01 or zone02 → wrongzone = violation
    """

    def __init__(self, config: Dict[str, Any], frigate_api: Any):
        super().__init__(config, frigate_api)

        # Configuration
        self.valid_zones: List[str] = config.get("valid_zones", [])
        self.violation_zone: str = config.get("violation_zone", "")
        self.vehicle_types: List[str] = config.get(
            "vehicle_types", ["car", "bus", "truck", "motorcycle"]
        )
        self.cleanup_timeout: int = config.get("cleanup_timeout", 60)

        # State tracking
        self.vehicle_zones: Dict[str, List[str]] = defaultdict(list)
        self.vehicle_data: Dict[str, Dict[str, Any]] = {}  # Store full vehicle data
        self.last_seen: Dict[str, datetime] = {}
        self.violations_logged: Dict[str, datetime] = {}

        self.log_info(
            f"Initialized: valid_zones={self.valid_zones}, "
            f"violation_zone={self.violation_zone}, "
            f"vehicle_types={self.vehicle_types}"
        )

    def process_event(self, event_data: Dict[str, Any]) -> None:
        """Process event and detect wrong-way violations"""

        if not self.should_process_event(event_data):
            return

        after = event_data.get("after", {})

        # Only process vehicle types we're tracking
        label = after.get("label")
        if label not in self.vehicle_types:
            return

        vehicle_id = after.get("id")
        current_zones = after.get("current_zones", [])
        camera = after.get("camera")

        # Store vehicle data (including bounding box)
        self.vehicle_data[vehicle_id] = after

        # Update vehicle tracking
        self._update_vehicle_tracking(vehicle_id, current_zones)

        # Check for violations
        self._check_for_violation(vehicle_id, label, camera)

        # Cleanup old tracking data
        self._cleanup_old_vehicles()

    def _update_vehicle_tracking(self, vehicle_id: str, current_zones: List[str]) -> None:
        """Track which zones vehicle has entered"""

        # Record timestamp
        self.last_seen[vehicle_id] = datetime.now()

        # Add new zones to vehicle's path
        for zone in current_zones:
            if zone not in self.vehicle_zones[vehicle_id]:
                self.vehicle_zones[vehicle_id].append(zone)
                self.log_debug(f"Vehicle {vehicle_id} entered {zone}")

    def _check_for_violation(self, vehicle_id: str, label: str, camera: str) -> None:
        """Check if vehicle has moved from valid zone to violation zone"""

        zone_sequence = self.vehicle_zones[vehicle_id]

        if len(zone_sequence) < 2:
            return  # Need at least 2 zones for violation

        # Check if vehicle came from valid zone
        came_from_valid_zone = any(zone in self.valid_zones for zone in zone_sequence)

        # Check if vehicle is now in violation zone
        in_violation_zone = self.violation_zone in zone_sequence

        # Violation detected!
        if came_from_valid_zone and in_violation_zone:
            # Prevent duplicate violation alerts (cooldown)
            if self._should_alert_violation(vehicle_id):
                self._handle_violation(vehicle_id, label, camera, zone_sequence)

    def _should_alert_violation(self, vehicle_id: str, cooldown_seconds: int = 30) -> bool:
        """Check if enough time has passed since last violation alert for this vehicle"""

        if vehicle_id not in self.violations_logged:
            return True

        time_since_last = datetime.now() - self.violations_logged[vehicle_id]
        return time_since_last.total_seconds() > cooldown_seconds

    def _handle_violation(
        self, vehicle_id: str, label: str, camera: str, zone_sequence: List[str]
    ) -> None:
        """Handle detected violation"""

        path = " → ".join(zone_sequence)

        # Get vehicle data (including bounding box)
        vehicle_info = self.vehicle_data.get(vehicle_id, {})
        box = vehicle_info.get("box")  # [x1, y1, x2, y2]

        self.log_warning(
            f"🚨 WRONG-WAY VIOLATION DETECTED!\n"
            f"   Vehicle ID: {vehicle_id}\n"
            f"   Type: {label}\n"
            f"   Camera: {camera}\n"
            f"   Path: {path}\n"
            f"   Valid zones: {', '.join(self.valid_zones)}\n"
            f"   Violation zone: {self.violation_zone}\n"
            f"   Bounding box: {box}"
        )

        # Create manual event in Frigate with bounding box
        event_id = self.create_event(
            camera=camera,
            label=label,
            sub_label=f"wrong_way_violation",
            duration=30,
            score=1.0,
            source_type="wrong_way_detector",
            box=box,  # Pass bounding box coordinates
        )

        if event_id:
            self.log_info(f"Created violation event: {event_id}")
            self.violations_logged[vehicle_id] = datetime.now()
        else:
            self.log_error("Failed to create violation event")

    def _cleanup_old_vehicles(self) -> None:
        """Remove vehicles not seen recently to prevent memory buildup"""

        cutoff_time = datetime.now() - timedelta(seconds=self.cleanup_timeout)

        # Find vehicles to remove
        to_remove = [
            vid for vid, last_time in self.last_seen.items()
            if last_time < cutoff_time
        ]

        # Remove from tracking
        for vid in to_remove:
            if vid in self.vehicle_zones:
                del self.vehicle_zones[vid]
            if vid in self.vehicle_data:
                del self.vehicle_data[vid]
            if vid in self.last_seen:
                del self.last_seen[vid]
            if vid in self.violations_logged:
                del self.violations_logged[vid]

            self.log_debug(f"Cleaned up vehicle {vid} (not seen for {self.cleanup_timeout}s)")

    def get_statistics(self) -> Dict[str, Any]:
        """Get action statistics"""
        return {
            "active_vehicles": len(self.vehicle_zones),
            "total_violations": len(self.violations_logged),
            "valid_zones": self.valid_zones,
            "violation_zone": self.violation_zone,
        }
