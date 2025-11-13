"""Frigate API client wrapper"""

import requests
from typing import Dict, Any, Optional
import logging


class FrigateAPI:
    """Client for interacting with Frigate HTTP API"""

    def __init__(self, base_url: str = "http://localhost:5001/api"):
        """
        Initialize Frigate API client

        Args:
            base_url: Base URL for Frigate API (default: http://localhost:5001/api)
        """
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_event(
        self,
        camera: str,
        label: str,
        sub_label: str = "",
        duration: Optional[int] = 30,
        score: float = 1.0,
        source_type: str = "automation",
        include_recording: bool = True,
        box: Optional[list] = None,
    ) -> Optional[str]:
        """
        Create a manual event in Frigate

        Args:
            camera: Camera name
            label: Object label (e.g., 'car', 'person')
            sub_label: Sub-categorization (e.g., 'wrong_way_violation')
            duration: Event duration in seconds (None for manual end)
            score: Confidence score (0.0-1.0)
            source_type: Source identifier for tracking
            include_recording: Whether to include video recording
            box: Bounding box coordinates [x1, y1, x2, y2] (optional)

        Returns:
            Event ID if successful, None otherwise
        """
        endpoint = f"{self.base_url}/events/{camera}/{label}/create"

        payload = {
            "sub_label": sub_label,
            "score": score,
            "source_type": source_type,
            "include_recording": include_recording,
        }

        if duration is not None:
            payload["duration"] = duration

        if box is not None:
            payload["draw"] = {"box": box}

        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()

            data = response.json()
            event_id = data.get("event_id")

            self.logger.info(
                f"Created event {event_id}: {camera}/{label}/{sub_label}"
            )
            return event_id

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to create event: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error creating event: {e}")
            return None

    def end_event(self, event_id: str) -> bool:
        """
        End an active event

        Args:
            event_id: Event ID to end

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"{self.base_url}/events/{event_id}/end"

        try:
            response = requests.put(endpoint, timeout=5)
            response.raise_for_status()
            self.logger.info(f"Ended event: {event_id}")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to end event {event_id}: {e}")
            return False

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get event details

        Args:
            event_id: Event ID

        Returns:
            Event data if successful, None otherwise
        """
        endpoint = f"{self.base_url}/events/{event_id}"

        try:
            response = requests.get(endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get event {event_id}: {e}")
            return None

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get Frigate system statistics

        Returns:
            System stats if successful, None otherwise
        """
        endpoint = f"{self.base_url}/stats"

        try:
            response = requests.get(endpoint, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get stats: {e}")
            return None

    def health_check(self) -> bool:
        """
        Check if Frigate API is accessible

        Returns:
            True if API is accessible, False otherwise
        """
        endpoint = f"{self.base_url}/version"

        try:
            response = requests.get(endpoint, timeout=3)
            response.raise_for_status()
            return True
        except Exception:
            return False
