"""Base class for all action handlers"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging


class BaseAction(ABC):
    """Abstract base class for action handlers"""

    def __init__(self, config: Dict[str, Any], frigate_api: Any):
        """
        Initialize action handler

        Args:
            config: Action-specific configuration
            frigate_api: FrigateAPI instance for creating events
        """
        self.config = config
        self.frigate_api = frigate_api
        self.enabled = config.get("enabled", True)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize action-specific state
        self.state: Dict[str, Any] = {}

    @abstractmethod
    def process_event(self, event_data: Dict[str, Any]) -> None:
        """
        Process an event from Frigate

        Args:
            event_data: Event payload from MQTT (trigger.payload_json format)
        """
        pass

    def is_enabled(self) -> bool:
        """Check if action is enabled"""
        return self.enabled

    def get_camera_filter(self) -> Optional[list]:
        """Get list of cameras this action should process (None = all cameras)"""
        return self.config.get("cameras")

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
        camera_filter = self.get_camera_filter()
        if camera_filter:
            camera = event_data.get("after", {}).get("camera")
            if camera not in camera_filter:
                return False

        return True

    def create_event(
        self,
        camera: str,
        label: str,
        sub_label: str,
        duration: int = 30,
        score: float = 1.0,
        source_type: str = "custom_action",
        box: Optional[list] = None,
    ) -> Optional[str]:
        """
        Create a manual event in Frigate

        Args:
            camera: Camera name
            label: Object label
            sub_label: Sub-categorization
            duration: Event duration in seconds
            score: Confidence score (0.0-1.0)
            source_type: Source identifier
            box: Bounding box coordinates [x1, y1, x2, y2] (optional)

        Returns:
            Event ID if successful, None otherwise
        """
        try:
            event_id = self.frigate_api.create_event(
                camera=camera,
                label=label,
                sub_label=sub_label,
                duration=duration,
                score=score,
                source_type=source_type,
                box=box,
            )
            self.logger.info(
                f"Created event: {event_id} ({label}/{sub_label}) on {camera}"
            )
            return event_id
        except Exception as e:
            self.logger.error(f"Failed to create event: {e}")
            return None

    def log_info(self, message: str) -> None:
        """Log info message"""
        self.logger.info(message)

    def log_warning(self, message: str) -> None:
        """Log warning message"""
        self.logger.warning(message)

    def log_error(self, message: str) -> None:
        """Log error message"""
        self.logger.error(message)

    def log_debug(self, message: str) -> None:
        """Log debug message"""
        self.logger.debug(message)
