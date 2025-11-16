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
        from frigate.analytics_db import AnalyticsObservation
        
        rule_name = violation["rule_name"]
        camera = violation["camera"]
        label = violation["label"]
        sub_label = violation["sub_label"]
        object_id = violation["object_id"]
        box = violation["box"]
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
        )

        if event_id:
            self.log_info(f"Created violation event: {event_id} ({rule_name})")
            
            # Save observation to analytics database
            try:
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
                    bboxshot=f"/api/events/{event_id}/snapshot.jpg?bbox=1",
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
