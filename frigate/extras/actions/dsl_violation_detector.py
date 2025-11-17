"""DSL-based Violation Detector

This action processes events through a configurable DSL system,
allowing users to define violation rules in YAML without code changes.
"""

from typing import Dict, Any, List
from .base_action import BaseAction
from ..dsl import RuleParser, RuleEvaluator, RuleValidator
from ..dsl.rule_types import Rule


class DSLViolationDetector(BaseAction):
    """
    Violation detector using DSL rules from configuration

    This action:
    1. Loads violation templates and camera-specific rules
    2. Validates all rules at startup
    3. Evaluates events against rules
    4. Creates Frigate events for detected violations
    """

    def __init__(self, config: Dict[str, Any], frigate_api: Any):
        super().__init__(config, frigate_api)

        # Get configuration sections
        self.templates_config = config.get("violation_templates", {})
        self.cameras_config = config.get("cameras", {})

        # Initialize DSL components
        self.parser = RuleParser()
        self.evaluator = RuleEvaluator()
        self.validator = RuleValidator(frigate_api)

        # Parse rules
        self._load_rules()

        # Validate rules
        self._validate_rules()

        self.log_info(
            f"Initialized DSL Violation Detector: "
            f"{len(self.templates_config)} templates, "
            f"{len(self.cameras_config)} cameras"
        )

    def _load_rules(self):
        """Load and parse all violation rules"""
        # Load templates
        self.parser.load_templates(self.templates_config)

        # Parse rules for each camera
        for camera, camera_config in self.cameras_config.items():
            violations_config = camera_config.get("violations", [])

            if violations_config:
                try:
                    rules = self.parser.parse_camera_violations(camera, violations_config)
                    self.log_info(f"Loaded {len(rules)} rules for camera '{camera}'")
                except Exception as e:
                    self.log_error(f"Error loading rules for camera '{camera}': {e}")
                    raise

    def _validate_rules(self):
        """Validate all loaded rules"""
        camera_rules = self.parser.get_all_rules()

        is_valid = self.validator.validate_all(self.templates_config, camera_rules)

        if not is_valid:
            raise ValueError("Violation rule validation failed. Check logs for details.")

        self.log_info("All violation rules validated successfully")

    def process_event(self, event_data: Dict[str, Any]) -> None:
        """
        Process event and evaluate violation rules

        Args:
            event_data: Event payload from MQTT
        """
        if not self.should_process_event(event_data):
            return

        after = event_data.get("after", {})
        camera = after.get("camera")

        if not camera:
            return

        # Get rules for this camera
        rules = self.parser.get_camera_rules(camera)

        if not rules:
            # No rules defined for this camera
            return

        # Evaluate rules
        violations = self.evaluator.evaluate_event(event_data, rules)

        # Create events for detected violations
        for violation in violations:
            self._handle_violation(violation, event_data)

    def _handle_violation(self, violation: Dict[str, Any], event_data: Dict[str, Any]):
        """
        Handle detected violation

        Args:
            violation: Violation record from evaluator
            event_data: Original event data
        """
        import datetime
        import os
        import cv2
        import numpy as np
        from frigate.analytics_db import AnalyticsObservation, analytics_db
        from frigate.const import CLIPS_DIR
        from frigate.util.image import draw_box_with_label
        
        rule_name = violation["rule_name"]
        camera = violation["camera"]
        label = violation["label"]
        sub_label = violation["sub_label"]
        object_id = violation["object_id"]
        box = violation["box"]
        frame_time = violation.get("frame_time")
        duration = violation["duration"]
        severity = violation["severity"]
        zone_sequence = violation.get("zone_sequence", [])
        score = violation.get("score", 1.0)

        # Log violation
        path = " → ".join(zone_sequence) if zone_sequence else "N/A"

        self.log_warning(
            f"🚨 VIOLATION DETECTED: {rule_name}\n"
            f"   Camera: {camera}\n"
            f"   Object: {label} (ID: {object_id})\n"
            f"   Sub-label: {sub_label}\n"
            f"   Severity: {severity}\n"
            f"   Path: {path}\n"
            f"   Description: {violation.get('description', 'N/A')}\n"
            f"   Box: {box}"
        )

        # Create manual event in Frigate
        event_id = self.create_event(
            camera=camera,
            label=label,
            sub_label=sub_label,
            duration=duration,
            score=score,
            source_type="dsl_violation_detector",
            box=box,
            frame_time=frame_time,
        )

        if event_id:
            self.log_info(f"Created violation event: {event_id} ({rule_name})")
            
            # Save violation evidence image with bbox
            try:
                snapshot_path = os.path.join(CLIPS_DIR, f"{camera}-{event_id}.jpg")
                self.log_debug(f"Looking for snapshot at: {snapshot_path}")

                # Retry logic: Wait for snapshot to be written by Frigate
                import time
                max_retries = 10  # Try for up to 5 seconds
                retry_delay = 0.5  # Wait 500ms between retries
                snapshot_found = False

                for attempt in range(max_retries):
                    if os.path.exists(snapshot_path):
                        snapshot_found = True
                        self.log_debug(f"Found snapshot on attempt {attempt + 1}")
                        break
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        time.sleep(retry_delay)

                if snapshot_found:
                    self.log_debug(f"Found snapshot, creating evidence image")
                    self.log_debug(f"Box data before processing: {box}")

                    # Read original snapshot
                    with open(snapshot_path, "rb") as f:
                        jpg_bytes = f.read()

                    # Decode image
                    img_as_np = np.frombuffer(jpg_bytes, dtype=np.uint8)
                    img = cv2.imdecode(img_as_np, flags=1)

                    self.log_debug(f"Image decoded: {img is not None}, Image shape: {img.shape if img is not None else 'None'}")
                    self.log_debug(f"Box is valid: {box is not None and len(box) == 4 if box else False}")

                    if img is not None and box:
                        # Draw bounding box on the image
                        thickness = 2
                        color = (0, 0, 255)  # Red color for violation

                        # Debug: Log box format
                        img_height, img_width = img.shape[:2]
                        self.log_debug(f"Image size: {img_width}x{img_height}, Box: {box}")

                        # Box coordinates are already in pixel format: [x, y, width, height]
                        # Convert to [x_min, y_min, x_max, y_max]
                        x_min = int(box[0])
                        y_min = int(box[1])
                        x_max = int(box[2])
                        y_max = int(box[3])

                        self.log_debug(f"Pixel coords: x_min={x_min}, y_min={y_min}, x_max={x_max}, y_max={y_max}")

                        draw_box_with_label(
                            img,
                            x_min,
                            y_min,
                            x_max,
                            y_max,
                            label,
                            f"{int(score * 100)}%",
                            thickness=thickness,
                            color=color,
                        )

                        # Save violation evidence image with -viol suffix
                        violation_evidence_path = os.path.join(CLIPS_DIR, f"{camera}-{event_id}-viol.jpg")
                        _, img_encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        with open(violation_evidence_path, "wb") as f:
                            f.write(img_encoded.tobytes())

                        self.log_info(f"Saved violation evidence image: {violation_evidence_path}")
                    else:
                        self.log_warning(f"Could not decode image or box is missing. img={img is not None}, box={box}")
                else:
                    self.log_warning(f"Snapshot not found at {snapshot_path} after {max_retries} retries ({max_retries * retry_delay}s)")
            except Exception as e:
                self.log_error(f"Failed to save violation evidence image: {e}")
                import traceback
                self.log_error(f"Traceback: {traceback.format_exc()}")
            
            # Save observation to analytics database
            try:
                # Check if analytics database is initialized
                if analytics_db.is_closed():
                    self.log_error("Analytics database is closed, cannot save observation")
                    return
                
                # Extract box coordinates
                box_x, box_y, box_width, box_height = box if box else (None, None, None, None)
                
                # Create observation record
                observation = AnalyticsObservation.create(
                    id=event_id,
                    camera=camera,
                    label=label,
                    sub_label=sub_label,
                    score=score,
                    timestamp=datetime.datetime.now().timestamp(),
                    cleanshot=f"/api/events/{event_id}/snapshot-clean.webp",
                    bboxshot=f"/api/events/{event_id}/evidence.jpg",
                    thumbnail=f"/api/events/{event_id}/thumbnail.jpg",
                    clip=f"/api/events/{event_id}/clip.mp4",
                    box_x=box_x,
                    box_y=box_y,
                    box_width=box_width,
                    box_height=box_height,
                    status="new",
                    notes=f"Rule: {rule_name}, Severity: {severity}, Path: {path}",
                    metadata={
                        "rule_name": rule_name,
                        "severity": severity,
                        "zone_sequence": zone_sequence,
                        "description": violation.get("description", ""),
                        "object_id": object_id,
                    },
                    created_at=datetime.datetime.now(),
                    updated_at=datetime.datetime.now(),
                )
                self.log_info(f"Saved observation to analytics database: {event_id}")
            except Exception as e:
                self.log_error(f"Failed to save observation to analytics database: {e}")
                import traceback
                self.log_error(f"Traceback: {traceback.format_exc()}")
        else:
            self.log_error(f"Failed to create violation event for rule: {rule_name}")

    def get_camera_filter(self) -> List[str]:
        """Get list of cameras this action should process"""
        # Process all cameras that have violations configured
        return list(self.cameras_config.keys()) if self.cameras_config else None

    def should_process_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Determine if this action should process the event

        Args:
            event_data: Event payload

        Returns:
            True if event should be processed
        """
        if not self.is_enabled():
            return False

        # Check camera filter
        camera = event_data.get("after", {}).get("camera")
        camera_filter = self.get_camera_filter()

        if camera_filter and camera not in camera_filter:
            return False

        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get action statistics"""
        return {
            "templates": len(self.templates_config),
            "cameras_configured": len(self.cameras_config),
            "total_rules": sum(
                len(rules) for rules in self.parser.get_all_rules().values()
            ),
            "evaluator_stats": self.evaluator.get_statistics(),
        }
