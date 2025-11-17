"""Parse YAML violation rules into Rule objects

The parser reads violation templates and camera-specific violations from
the configuration and creates Rule instances.
"""

from typing import Dict, Any, List
import logging
from .rule_types import create_rule, Rule


class RuleParser:
    """Parser for violation rules from YAML configuration"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.templates: Dict[str, Dict[str, Any]] = {}
        self.camera_rules: Dict[str, List[Rule]] = {}

    def load_templates(self, templates_config: Dict[str, Dict[str, Any]]):
        """
        Load global violation templates

        Args:
            templates_config: violation_templates section from config
        """
        self.templates = templates_config or {}
        self.logger.info(f"Loaded {len(self.templates)} violation templates")

    def parse_camera_violations(
        self, camera: str, violations_config: List[Dict[str, Any]]
    ) -> List[Rule]:
        """
        Parse violations for a specific camera

        Args:
            camera: Camera name
            violations_config: List of violation configs for this camera

        Returns:
            List of Rule instances

        Raises:
            ValueError: If violation config is invalid
        """
        rules = []

        for violation in violations_config:
            # Check if violation is enabled (defaults to True if not specified)
            enabled = violation.get("enabled", True)
            if not enabled:
                self.logger.info(
                    f"Skipping disabled violation '{violation.get('name', 'unknown')}' for camera '{camera}'"
                )
                continue

            try:
                rule = self._parse_single_violation(camera, violation)
                rules.append(rule)
                self.logger.debug(f"Parsed rule '{rule.name}' for camera '{camera}'")
            except Exception as e:
                self.logger.error(
                    f"Failed to parse violation for camera '{camera}': {e}"
                )
                raise

        self.camera_rules[camera] = rules
        return rules

    def _parse_single_violation(
        self, camera: str, violation_config: Dict[str, Any]
    ) -> Rule:
        """
        Parse a single violation configuration

        Args:
            camera: Camera name
            violation_config: Single violation config

        Returns:
            Rule instance

        Raises:
            ValueError: If config is invalid
        """
        name = violation_config.get("name")
        if not name:
            raise ValueError(f"Violation missing 'name' for camera '{camera}'")

        # Check if using a template
        template_name = violation_config.get("template")
        if template_name:
            return self._create_from_template(name, template_name, violation_config)
        else:
            return self._create_inline_rule(name, violation_config)

    def _create_from_template(
        self, name: str, template_name: str, violation_config: Dict[str, Any]
    ) -> Rule:
        """
        Create rule from a template with parameter substitution

        Args:
            name: Rule name
            template_name: Template name
            violation_config: Violation config with params

        Returns:
            Rule instance

        Raises:
            ValueError: If template not found or invalid
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")

        # Get template config
        template = self.templates[template_name].copy()

        # Get parameters for substitution
        params = violation_config.get("params", {})

        # Perform parameter substitution
        rule_config = self._substitute_parameters(template, params)

        # Override with violation-specific settings
        if "duration" in violation_config:
            rule_config["duration"] = violation_config["duration"]
        if "severity" in violation_config:
            rule_config["severity"] = violation_config["severity"]
        if "retention_days" in violation_config:
            rule_config["retention_days"] = violation_config["retention_days"]

        # Create rule
        return create_rule(name, rule_config)

    def _create_inline_rule(
        self, name: str, violation_config: Dict[str, Any]
    ) -> Rule:
        """
        Create rule from inline configuration (no template)

        Args:
            name: Rule name
            violation_config: Violation config

        Returns:
            Rule instance
        """
        return create_rule(name, violation_config)

    def _substitute_parameters(
        self, template: Dict[str, Any], params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Substitute parameters in template

        Replaces placeholders like {from}, {to}, {obj} with actual values.

        Args:
            template: Template configuration
            params: Parameters to substitute

        Returns:
            Configuration with parameters substituted
        """
        import copy
        import re

        config = copy.deepcopy(template)

        def substitute_value(value):
            """Recursively substitute parameters in values"""
            if isinstance(value, str):
                # Replace {param} with param value
                for param_name, param_value in params.items():
                    placeholder = "{" + param_name + "}"
                    if placeholder in value:
                        # If entire string is placeholder, replace with actual type
                        if value == placeholder:
                            value = param_value
                        else:
                            # String substitution
                            value = value.replace(placeholder, str(param_value))
                return value
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            else:
                return value

        return substitute_value(config)

    def get_all_rules(self) -> Dict[str, List[Rule]]:
        """Get all parsed rules organized by camera"""
        return self.camera_rules

    def get_camera_rules(self, camera: str) -> List[Rule]:
        """Get rules for a specific camera"""
        return self.camera_rules.get(camera, [])
