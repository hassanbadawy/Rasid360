"""MQTT client for Frigate events"""

import paho.mqtt.client as mqtt
import json
import logging
from typing import Callable, Optional, Dict, Any


class MQTTClient:
    """MQTT client wrapper for Frigate event monitoring"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "frigate_extras",
    ):
        """
        Initialize MQTT client

        Args:
            host: MQTT broker hostname
            port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            client_id: MQTT client identifier
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id

        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = mqtt.Client(client_id=client_id)
        self.connected = False
        self.event_callback: Optional[Callable] = None

        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Authentication
        if username and password:
            self.client.username_pw_set(username, password)

    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Set callback function for event processing

        Args:
            callback: Function to call with event data
        """
        self.event_callback = callback

    def connect(self) -> bool:
        """
        Connect to MQTT broker

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}")
            self.client.connect(self.host, self.port, keepalive=60)
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from MQTT broker"""
        self.logger.info("Disconnecting from MQTT broker")
        self.client.disconnect()

    def start(self) -> None:
        """Start MQTT client loop (blocking)"""
        self.logger.info("Starting MQTT client loop")
        self.client.loop_forever()

    def start_async(self) -> None:
        """Start MQTT client loop (non-blocking)"""
        self.logger.info("Starting MQTT client loop (async)")
        self.client.loop_start()

    def stop_async(self) -> None:
        """Stop async MQTT client loop"""
        self.logger.info("Stopping MQTT client loop")
        self.client.loop_stop()

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            self.connected = True
            self.logger.info("Connected to MQTT broker successfully")

            # Subscribe to Frigate events topic
            self.client.subscribe("frigate/events")
            self.logger.info("Subscribed to frigate/events topic")
        else:
            self.connected = False
            self.logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        self.connected = False
        if rc != 0:
            self.logger.warning(f"Unexpected disconnection from MQTT broker. Return code: {rc}")
        else:
            self.logger.info("Disconnected from MQTT broker")

    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            # Parse JSON payload
            event_data = json.loads(msg.payload.decode("utf-8"))

            self.logger.debug(f"Received event from topic: {msg.topic}")

            # Call event callback if registered
            if self.event_callback:
                self.event_callback(event_data)

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode MQTT message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing MQTT message: {e}")

    def is_connected(self) -> bool:
        """Check if connected to MQTT broker"""
        return self.connected
