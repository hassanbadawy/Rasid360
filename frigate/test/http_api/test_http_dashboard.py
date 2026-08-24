"""Tests for the dashboard analytics endpoints.

Regression coverage for the access-control bug where eight call sites invoked
the async ``get_allowed_cameras_for_filter`` with the wrong arity and without
awaiting it. Every one raised TypeError, which the endpoints' broad exception
handler turned into a 500 -- so the failure looked like "no data" rather than a
fault. A single status-code assertion per endpoint catches that whole class.
"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from frigate.analytics_db import close_analytics_db, init_analytics_db
from frigate.api.auth import get_current_user
from frigate.models import Event, Recordings, ReviewSegment
from frigate.test.http_api.base_http_test import BaseTestHttp

TEST_ANALYTICS_DB = "test_analytics.db"

# Every dashboard route, with the query strings that select each code path.
# The unfiltered form reads the pre-aggregated analytics tables; the filtered
# form falls through to a live query against frigate.db. Both must work.
UNFILTERED = [
    "/dashboard/tickets/status",
    "/dashboard/violations/by-camera",
    "/dashboard/violations/by-type",
    "/dashboard/violations/hourly-heatmap",
    "/dashboard/violations/by-weekday",
    "/dashboard/violations/by-month",
    "/dashboard/violations/by-quarter",
    "/dashboard/violations/by-year",
    "/dashboard/camera/fps",
    "/dashboard/camera/offline",
]

FILTERED = [
    "/dashboard/tickets/status?cameras=front_door",
    "/dashboard/violations/by-camera?after=1",
    "/dashboard/violations/by-type?cameras=front_door",
    "/dashboard/violations/hourly-heatmap?cameras=front_door",
    "/dashboard/violations/by-weekday?cameras=front_door",
    "/dashboard/violations/by-month?cameras=front_door",
    "/dashboard/violations/by-quarter?cameras=front_door",
    "/dashboard/violations/by-year?cameras=front_door",
]


class TestHttpDashboard(BaseTestHttp):
    def setUp(self):
        super().setUp([Event, Recordings, ReviewSegment])
        init_analytics_db(TEST_ANALYTICS_DB)
        self.app = super().create_app()

        async def mock_get_current_user():
            return {"username": "test_user", "role": "admin"}

        self.app.dependency_overrides[get_current_user] = mock_get_current_user

    def tearDown(self):
        self.app.dependency_overrides.clear()
        close_analytics_db()
        for suffix in ("", "-shm", "-wal"):
            try:
                os.remove(TEST_ANALYTICS_DB + suffix)
            except OSError:
                pass
        super().tearDown()

    def _allow(self, cameras):
        return patch(
            "frigate.api.dashboard.get_allowed_cameras_for_filter",
            new=AsyncMock(return_value=cameras),
        )

    def test_unfiltered_endpoints_return_200(self):
        with self._allow(["front_door"]), TestClient(self.app) as client:
            for route in UNFILTERED:
                resp = client.get(route)
                self.assertEqual(resp.status_code, 200, f"{route}: {resp.text}")
                self.assertTrue(resp.json()["success"], f"{route}: {resp.text}")

    def test_filtered_endpoints_return_200(self):
        """The filtered branch is where the arity bug lived."""
        with self._allow(["front_door"]), TestClient(self.app) as client:
            for route in FILTERED:
                resp = client.get(route)
                self.assertEqual(resp.status_code, 200, f"{route}: {resp.text}")
                self.assertTrue(resp.json()["success"], f"{route}: {resp.text}")

    def test_camera_filter_scopes_results(self):
        super().insert_mock_event(
            "v1", camera="front_door", data={"type": "dsl_violation_detector"}
        )
        super().insert_mock_event(
            "v2", camera="back_door", data={"type": "dsl_violation_detector"}
        )
        Event.update(sub_label="wrongway").execute()

        with self._allow(["front_door"]), TestClient(self.app) as client:
            resp = client.get("/dashboard/violations/by-camera?after=1")
            self.assertEqual(resp.status_code, 200, resp.text)
            cameras = [row["camera"] for row in resp.json()["data"]]
            self.assertIn("front_door", cameras)
            self.assertNotIn("back_door", cameras)

    def test_no_camera_access_returns_nothing(self):
        """An empty allowed-camera list must fail closed, not open."""
        super().insert_mock_event(
            "v1", camera="front_door", data={"type": "dsl_violation_detector"}
        )
        Event.update(sub_label="wrongway").execute()

        with self._allow([]), TestClient(self.app) as client:
            resp = client.get("/dashboard/violations/by-camera?after=1")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["data"], [])

    def test_requested_cameras_intersected_with_allowed(self):
        """Asking for a camera you cannot see must not return it."""
        super().insert_mock_event(
            "v1", camera="back_door", data={"type": "dsl_violation_detector"}
        )
        Event.update(sub_label="wrongway").execute()

        with self._allow(["front_door"]), TestClient(self.app) as client:
            resp = client.get("/dashboard/violations/by-type?cameras=back_door")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["data"], [])


class TestViolationDefinition(BaseTestHttp):
    """Enrichment results must not be counted as violations.

    Upstream Frigate writes sub_label for face recognition and license plate
    recognition, so `sub_label IS NOT NULL` alone over-counts.
    """

    def setUp(self):
        super().setUp([Event, Recordings, ReviewSegment])
        init_analytics_db(TEST_ANALYTICS_DB)
        self.app = super().create_app()

        async def mock_get_current_user():
            return {"username": "test_user", "role": "admin"}

        self.app.dependency_overrides[get_current_user] = mock_get_current_user

    def tearDown(self):
        self.app.dependency_overrides.clear()
        close_analytics_db()
        for suffix in ("", "-shm", "-wal"):
            try:
                os.remove(TEST_ANALYTICS_DB + suffix)
            except OSError:
                pass
        super().tearDown()

    def test_recognized_plates_are_not_violations(self):
        super().insert_mock_event(
            "viol", camera="front_door", data={"type": "dsl_violation_detector"}
        )
        super().insert_mock_event(
            "plate",
            camera="front_door",
            data={"type": "api", "recognized_license_plate": "ABC-1234"},
        )
        Event.update(sub_label="wrongway").where(Event.id == "viol").execute()
        Event.update(sub_label="ABC-1234").where(Event.id == "plate").execute()

        with patch(
            "frigate.api.dashboard.get_allowed_cameras_for_filter",
            new=AsyncMock(return_value=["front_door"]),
        ), TestClient(self.app) as client:
            resp = client.get("/dashboard/violations/by-type?cameras=front_door")
            self.assertEqual(resp.status_code, 200, resp.text)
            types = [row["sub_label"] for row in resp.json()["data"]]
            self.assertIn("wrongway", types)
            self.assertNotIn(
                "ABC-1234", types, "recognized plate counted as a violation"
            )


if __name__ == "__main__":
    unittest.main()
