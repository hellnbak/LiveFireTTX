from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.main import app


class ApplicationRouteTests(TestCase):
    def test_health_and_guided_setup_routes(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(
                models,
                "DB_PATH",
                Path(temporary) / "livefirettx.db",
            ):
                with TestClient(app) as client:
                    health = client.get("/healthz")
                    self.assertEqual(200, health.status_code)
                    self.assertEqual("1.0.0", health.json()["version"])
                    self.assertTrue(health.json()["healthy"])
                    self.assertTrue(health.headers["x-request-id"])
                    self.assertEqual(
                        "nosniff",
                        health.headers["x-content-type-options"],
                    )

                    setup = client.get("/new")
                    self.assertEqual(200, setup.status_code)
                    self.assertIn("Critical Dependency Cascade", setup.text)
                    self.assertIn("/static/new.js", setup.text)

    def test_rejects_untrusted_hosts_and_cross_origin_changes(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(
                models,
                "DB_PATH",
                Path(temporary) / "livefirettx.db",
            ):
                with TestClient(app) as client:
                    untrusted_host = client.get(
                        "/healthz",
                        headers={"host": "livefire.example"},
                    )
                    self.assertEqual(400, untrusted_host.status_code)

                    cross_origin = client.post(
                        "/exercises",
                        headers={
                            "origin": "https://livefire.example",
                            "sec-fetch-site": "cross-site",
                        },
                        data={},
                    )
                    self.assertEqual(403, cross_origin.status_code)
                    self.assertEqual(
                        "Cross-origin state changes are not allowed",
                        cross_origin.json()["detail"],
                    )

                    local_origin = client.post(
                        "/exercises",
                        headers={
                            "origin": "http://testserver",
                            "sec-fetch-site": "cross-site",
                        },
                        data={},
                    )
                    self.assertEqual(415, local_origin.status_code)

                    opaque_local_origin = client.post(
                        "/exercises",
                        headers={
                            "origin": "null",
                            "sec-fetch-site": "same-origin",
                        },
                        data={},
                    )
                    self.assertEqual(415, opaque_local_origin.status_code)

                    opaque_cross_origin = client.post(
                        "/exercises",
                        headers={
                            "origin": "null",
                            "sec-fetch-site": "cross-site",
                        },
                        data={},
                    )
                    self.assertEqual(403, opaque_cross_origin.status_code)

    def test_creates_dependency_exercise_and_serves_role_brief(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(models, "DB_PATH", root / "livefirettx.db"),
                patch(
                    "app.services.generator.GENERATED_ROOT",
                    root / "exercises",
                ),
            ):
                with TestClient(app) as client:
                    response = client.post(
                        "/exercises",
                        data={
                            "name": "Dependency exercise",
                            "scenario_type": "dependency_cascade",
                            "platform": "local_docker",
                            "business_system": "Commerce",
                            "difficulty": "advanced",
                            "duration_minutes": "90",
                            "participants": "Incident Commander, SRE",
                            "objectives": "Map impact\nRecover safely",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, response.status_code)
                    exercise = models.list_exercises()[0]
                    briefs = (
                        Path(exercise.package_path)
                        / "participants"
                        / "roles"
                    ).glob("*.md")
                    filename = next(iter(briefs)).name
                    brief = client.get(
                        f"/exercises/{exercise.id}/participants/{filename}"
                    )
                    self.assertEqual(200, brief.status_code)
                    self.assertIn("SIMULATED", brief.text.upper())
