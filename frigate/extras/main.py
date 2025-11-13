#!/usr/bin/env python3
"""
Frigate Extras - Custom Event Detection System
Main entry point for event dispatcher
"""

import sys
import os
import logging
import signal
from typing import Dict, Any, List
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from frigate.extras.config import ConfigLoader
from frigate.extras.utils.mqtt_client import MQTTClient
from frigate.extras.utils.frigate_api import FrigateAPI
from frigate.extras.actions.base_action import BaseAction
from frigate.extras.actions.wrong_way_detection import WrongWayDetection


class EventDispatcher:
    """Main event dispatcher for all action handlers"""

    def __init__(self, config_path: str):
        """
        Initialize event dispatcher

        Args:
            config_path: Path to config.yml
        """
        self.config_path = config_path
        self.running = False

        # Setup logging
        self._setup_logging()

        self.logger.info("=" * 60)
        self.logger.info("Frigate Extras - Custom Event Detection System")
        self.logger.info("=" * 60)

        # Load configuration
        self.config_loader = ConfigLoader(config_path)

        # Initialize Frigate API
        frigate_config = self.config_loader.get_frigate_config()
        api_url = frigate_config.get("api_url", "http://localhost:5000/api")
        self.frigate_api = FrigateAPI(api_url)

        # Check Frigate connectivity
        if not self.frigate_api.health_check():
            self.logger.warning(f"Cannot connect to Frigate API at {api_url}")
            self.logger.warning("Will continue, but event creation may fail")

        # Initialize MQTT client
        mqtt_config = self.config_loader.get_mqtt_config()
        self.mqtt_client = MQTTClient(
            host=mqtt_config.get("host", "localhost"),
            port=mqtt_config.get("port", 1883),
            username=mqtt_config.get("username"),
            password=mqtt_config.get("password"),
            client_id=mqtt_config.get("client_id", "frigate_extras"),
        )

        # Register event callback
        self.mqtt_client.set_event_callback(self._dispatch_event)

        # Initialize action handlers
        self.actions: List[BaseAction] = []
        self._load_actions()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logging(self) -> None:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("/tmp/frigate_extras.log"),
            ],
        )
        self.logger = logging.getLogger("EventDispatcher")

    def _load_actions(self) -> None:
        """Load and initialize all enabled action handlers"""
        self.logger.info("Loading action handlers...")

        enabled_actions = self.config_loader.get_all_enabled_actions()

        if not enabled_actions:
            self.logger.warning("No actions are enabled in configuration")
            return

        # Registry of available action classes
        action_registry = {
            "wrong_way_detection": WrongWayDetection,
            # Add more actions here as they are implemented:
            # "fall_detection": FallDetection,
            # "loitering_detection": LoiteringDetection,
        }

        for action_name, action_config in enabled_actions.items():
            if action_name not in action_registry:
                self.logger.warning(
                    f"Action '{action_name}' is enabled but not found in registry"
                )
                continue

            try:
                # Instantiate action handler
                action_class = action_registry[action_name]
                action_instance = action_class(action_config, self.frigate_api)

                self.actions.append(action_instance)
                self.logger.info(f"✓ Loaded action: {action_name}")

            except Exception as e:
                self.logger.error(f"✗ Failed to load action '{action_name}': {e}")

        self.logger.info(f"Loaded {len(self.actions)} action handler(s)")

    def _dispatch_event(self, event_data: Dict[str, Any]) -> None:
        """
        Dispatch event to all action handlers

        Args:
            event_data: Event payload from MQTT
        """
        # Log event summary
        after = event_data.get("after", {})
        camera = after.get("camera", "unknown")
        label = after.get("label", "unknown")
        zones = after.get("current_zones", [])

        self.logger.debug(
            f"Event: {camera}/{label} in zones {zones}"
        )

        # Send to all action handlers
        for action in self.actions:
            try:
                action.process_event(event_data)
            except Exception as e:
                self.logger.error(
                    f"Error in action {action.__class__.__name__}: {e}",
                    exc_info=True,
                )

    def start(self) -> None:
        """Start event dispatcher"""
        self.logger.info("Starting Event Dispatcher")
        self.logger.info(f"Active actions: {[a.__class__.__name__ for a in self.actions]}")

        # Connect to MQTT broker
        if not self.mqtt_client.connect():
            self.logger.error("Failed to connect to MQTT broker")
            sys.exit(1)

        # Start MQTT loop
        self.running = True
        self.logger.info("Event dispatcher is running. Press Ctrl+C to stop.")

        try:
            self.mqtt_client.start()  # Blocking call
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop event dispatcher"""
        if not self.running:
            return

        self.logger.info("Stopping Event Dispatcher")
        self.running = False

        # Disconnect from MQTT
        self.mqtt_client.disconnect()

        self.logger.info("Event dispatcher stopped")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}")
        self.stop()
        sys.exit(0)


def main():
    """Main entry point"""
    # Determine config path
    default_config = os.path.join(
        os.path.dirname(__file__), "config.yml"
    )

    config_path = os.environ.get("FRIGATE_EXTRAS_CONFIG", default_config)

    if not os.path.exists(config_path):
        print(f"ERROR: Configuration file not found: {config_path}")
        print(f"Please create config.yml or set FRIGATE_EXTRAS_CONFIG environment variable")
        sys.exit(1)

    # Create and start dispatcher
    dispatcher = EventDispatcher(config_path)
    dispatcher.start()


if __name__ == "__main__":
    main()
