"""Validate violation rules at startup

The validator checks that:
- Required fields are present
- Zone names exist in Frigate configuration
- Object labels are valid
- Condition syntax is correct
- Templates are properly defined
"""

from typing import Dict, Any, List, Set, Optional
import logging
from .rule_types import Rule
from .operators import ConditionParser


class RuleValidator:
    """Validator for violation rules"""

    def __init__(self, frigate_api=None):
        """
        Initialize validator

        Args:
            frigate_api: FrigateAPI instance for fetching config (optional)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.frigate_api = frigate_api
        self.frigate_cameras: Set[str] = set()
        self.enabled_cameras: Set[str] = set()
        self.disabled_cameras: Set[str] = set()
        self.frigate_zones: Dict[str, Set[str]] = {}  # camera -> zones
        self.frigate_labels: Set[str] = set()

    def load_frigate_config(self):
        """
        Load Frigate configuration to validate against

        Fetches cameras, zones, and tracked objects from Frigate.
        Also tracks which cameras are enabled/disabled.
        """
        if not self.frigate_api:
            self.logger.warning("No Frigate API provided, skipping config validation")
            return

        try:
            # Get Frigate configuration
            config = self.frigate_api.get_config()
            if not config:
                self.logger.warning("Could not fetch Frigate config")
                return

            # Extract cameras and their enabled status
            cameras = config.get("cameras", {})
            self.frigate_cameras = set()

            # Track enabled and disabled cameras separately
            self.enabled_cameras = set()
            self.disabled_cameras = set()

            for camera_name, camera_config in cameras.items():
                self.frigate_cameras.add(camera_name)

                # Check if camera is enabled (defaults to True if not specified)
                is_enabled = camera_config.get("enabled", True)
                if is_enabled:
                    self.enabled_cameras.add(camera_name)
                else:
                    self.disabled_cameras.add(camera_name)

            # Extract zones per camera (only for enabled cameras)
            for camera, camera_config in cameras.items():
                zones = camera_config.get("zones", {})
                self.frigate_zones[camera] = set(zones.keys())

            # Extract tracked objects
            objects_config = config.get("objects", {})
            tracked_objects = objects_config.get("track", [])
            self.frigate_labels = set(tracked_objects) if tracked_objects else set()

            self.logger.info(
                f"Loaded Frigate config: {len(self.frigate_cameras)} cameras "
                f"({len(self.enabled_cameras)} enabled, {len(self.disabled_cameras)} disabled), "
                f"{sum(len(z) for z in self.frigate_zones.values())} zones, "
                f"{len(self.frigate_labels)} tracked objects"
            )

        except Exception as e:
            self.logger.error(f"Error loading Frigate config: {e}")

    def validate_templates(self, templates: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Validate violation templates

        Args:
            templates: violation_templates from config

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        for template_name, template_config in templates.items():
            # Check type is specified
            rule_type = template_config.get("type")
            if not rule_type:
                errors.append(f"Template '{template_name}' missing 'type'")
                continue

            # Validate based on type
            if rule_type == "object_logic":
                condition = template_config.get("condition")
                if not condition:
                    errors.append(
                        f"Template '{template_name}' (object_logic) missing 'condition'"
                    )
                else:
                    # Validate condition syntax
                    err = self._validate_condition(condition, template_name)
                    if err:
                        errors.append(err)

            elif rule_type == "zone_object":
                condition = template_config.get("condition")
                if not condition:
                    errors.append(
                        f"Template '{template_name}' (zone_object) missing 'condition'"
                    )
                else:
                    err = self._validate_condition(condition, template_name)
                    if err:
                        errors.append(err)

            elif rule_type == "zone_sequence":
                if "from_zones" not in template_config and "{from}" not in str(
                    template_config
                ):
                    errors.append(
                        f"Template '{template_name}' (zone_sequence) missing 'from_zones' or placeholder"
                    )
                if "to_zone" not in template_config and "{to}" not in str(
                    template_config
                ):
                    errors.append(
                        f"Template '{template_name}' (zone_sequence) missing 'to_zone' or placeholder"
                    )

            elif rule_type == "action":
                if "action_class" not in template_config:
                    errors.append(
                        f"Template '{template_name}' (action) missing 'action_class'"
                    )

            elif rule_type == "sustained_condition":
                condition = template_config.get("condition")
                if not condition:
                    errors.append(
                        f"Template '{template_name}' (sustained_condition) missing 'condition'"
                    )
                if "monitor_duration" not in template_config:
                    errors.append(
                        f"Template '{template_name}' (sustained_condition) missing 'monitor_duration'"
                    )

            elif rule_type == "proximity":
                if "first_object" not in template_config:
                    errors.append(
                        f"Template '{template_name}' (proximity) missing 'first_object'"
                    )
                if "second_object" not in template_config:
                    errors.append(
                        f"Template '{template_name}' (proximity) missing 'second_object'"
                    )

            elif rule_type == "fall_down":
                if "object_type" not in template_config:
                    errors.append(
                        f"Template '{template_name}' (fall_down) missing 'object_type'"
                    )
                if "width_height_ratio" not in template_config and "{ratio}" not in str(template_config):
                    errors.append(
                        f"Template '{template_name}' (fall_down) missing 'width_height_ratio'"
                    )

            else:
                errors.append(f"Template '{template_name}' has unknown type: {rule_type}")

        return errors

    def validate_camera_rules(
        self, camera: str, rules: List[Rule]
    ) -> List[str]:
        """
        Validate rules for a specific camera

        Args:
            camera: Camera name
            rules: List of rules for this camera

        Returns:
            List of validation errors (empty if valid)
            Returns special marker ["SKIP_CAMERA"] if camera should be skipped
        """
        errors = []

        # Check if camera exists in Frigate
        if self.frigate_cameras and camera not in self.frigate_cameras:
            # Camera not found - skip validation but don't fail
            self.logger.warning(
                f"Camera '{camera}' not found in Frigate configuration - "
                f"skipping {len(rules)} rule(s)"
            )
            return ["SKIP_CAMERA"]

        # Check if camera is disabled in Frigate
        if self.disabled_cameras and camera in self.disabled_cameras:
            # Camera is disabled - skip validation but don't fail
            self.logger.info(
                f"Camera '{camera}' is disabled in Frigate configuration - "
                f"skipping {len(rules)} rule(s)"
            )
            return ["SKIP_CAMERA"]

        # Get zones for this camera
        camera_zones = self.frigate_zones.get(camera, set())

        # Validate each rule
        for rule in rules:
            # Validate zones in ZoneSequenceRule
            if hasattr(rule, "from_zones") and hasattr(rule, "to_zone"):
                # Zone sequence rule
                for zone in rule.from_zones:
                    if camera_zones and zone not in camera_zones:
                        errors.append(
                            f"Rule '{rule.name}' references unknown zone '{zone}' "
                            f"for camera '{camera}'"
                        )

                if camera_zones and rule.to_zone not in camera_zones:
                    errors.append(
                        f"Rule '{rule.name}' references unknown zone '{rule.to_zone}' "
                        f"for camera '{camera}'"
                    )

            # Validate object labels
            if hasattr(rule, "detected_labels"):
                for label in rule.detected_labels:
                    if self.frigate_labels and label not in self.frigate_labels:
                        self.logger.warning(
                            f"Rule '{rule.name}' references label '{label}' "
                            f"which is not in Frigate's tracked objects"
                        )

            if hasattr(rule, "vehicle_types"):
                for vtype in rule.vehicle_types:
                    if self.frigate_labels and vtype not in self.frigate_labels:
                        self.logger.warning(
                            f"Rule '{rule.name}' references vehicle type '{vtype}' "
                            f"which is not in Frigate's tracked objects"
                        )

        return errors

    def _validate_condition(self, condition: str, context: str) -> Optional[str]:
        """
        Validate condition syntax

        Args:
            condition: Condition string
            context: Context for error message (template name, etc.)

        Returns:
            Error message if invalid, None if valid
        """
        # Skip validation if condition contains placeholders
        if "{" in condition:
            return None

        try:
            parser = ConditionParser()
            parser.parse(condition)
            return None
        except Exception as e:
            return f"Invalid condition syntax in '{context}': {e}"

    def validate_all(
        self,
        templates: Dict[str, Dict[str, Any]],
        camera_rules: Dict[str, List[Rule]],
    ) -> bool:
        """
        Validate all templates and rules

        Args:
            templates: violation_templates from config
            camera_rules: Parsed rules per camera

        Returns:
            True if valid, False if errors found
        """
        all_errors = []
        skipped_cameras = []

        # Load Frigate config
        self.load_frigate_config()

        # Validate templates
        template_errors = self.validate_templates(templates)
        all_errors.extend(template_errors)

        # Validate camera rules
        for camera, rules in camera_rules.items():
            rule_errors = self.validate_camera_rules(camera, rules)

            # Check if camera should be skipped
            if rule_errors == ["SKIP_CAMERA"]:
                skipped_cameras.append(camera)
                continue

            all_errors.extend(rule_errors)

        # Log skipped cameras summary
        if skipped_cameras:
            self.logger.info(
                f"Skipped validation for {len(skipped_cameras)} camera(s): "
                f"{', '.join(skipped_cameras)}"
            )

        # Log errors
        if all_errors:
            self.logger.error("Validation errors found:")
            for error in all_errors:
                self.logger.error(f"  - {error}")
            return False
        else:
            self.logger.info("All violation rules validated successfully")
            return True
