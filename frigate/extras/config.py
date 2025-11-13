"""Configuration loader for Frigate Extras"""

import yaml
import os
from typing import Dict, Any, Optional
import logging


class ConfigLoader:
    """Load and validate configuration for action handlers"""

    def __init__(self, config_path: str):
        """
        Initialize config loader

        Args:
            config_path: Path to config.yml file
        """
        self.config_path = config_path
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config: Dict[str, Any] = {}

        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file"""
        if not os.path.exists(self.config_path):
            self.logger.error(f"Configuration file not found: {self.config_path}")
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with open(self.config_path, "r") as f:
                self.config = yaml.safe_load(f)
                self.logger.info(f"Loaded configuration from {self.config_path}")
        except yaml.YAMLError as e:
            self.logger.error(f"Failed to parse YAML config: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise

    def get_mqtt_config(self) -> Dict[str, Any]:
        """Get MQTT configuration"""
        return self.config.get("mqtt", {})

    def get_frigate_config(self) -> Dict[str, Any]:
        """Get Frigate API configuration"""
        return self.config.get("frigate", {})

    def get_actions_config(self) -> Dict[str, Any]:
        """Get all actions configuration"""
        return self.config.get("actions", {})

    def get_action_config(self, action_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for specific action

        Args:
            action_name: Name of the action

        Returns:
            Action configuration dict or None if not found
        """
        actions = self.get_actions_config()
        return actions.get(action_name)

    def is_action_enabled(self, action_name: str) -> bool:
        """
        Check if action is enabled

        Args:
            action_name: Name of the action

        Returns:
            True if enabled, False otherwise
        """
        action_config = self.get_action_config(action_name)
        if not action_config:
            return False

        return action_config.get("enabled", False)

    def get_all_enabled_actions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all enabled actions

        Returns:
            Dict of action_name -> config for all enabled actions
        """
        actions = self.get_actions_config()
        return {
            name: config
            for name, config in actions.items()
            if config.get("enabled", False)
        }

    def reload(self) -> None:
        """Reload configuration from file"""
        self.logger.info("Reloading configuration")
        self._load_config()
