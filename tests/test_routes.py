from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.main import app


class ApplicationRouteTests(TestCase):
    def test_readiness_does_not_expose_exception_or_path_details(self) -> None:
        class UnavailableStorage:
            def mkdir(self, **kwargs) -> None:
                raise PermissionError("secret path: /private/generated")

        with TemporaryDirectory() as temporary:
            with patch.object(
                models,
                "DB_PATH",
                Path(temporary) / "livefirettx.db",
            ):
                with TestClient(app) as client:
                    with (
                        patch(
                            "app.routes.system.database_health",
                            return_value={
                                "healthy": False,
                                "schema_version": 0,
                                "error": "secret database error",
                                "path": "/private/database.db",
                            },
                        ),
                        patch(
                            "app.routes.system.settings",
                            SimpleNamespace(generated_root=UnavailableStorage()),
                        ),
                    ):
                        response = client.get("/readyz")

        self.assertEqual(503, response.status_code)
        self.assertNotIn("secret", response.text)
        self.assertNotIn("/private", response.text)
        self.assertEqual(
            "Database health check failed",
            response.json()["database"]["error"],
        )

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
                    self.assertEqual("1.1.0", health.json()["version"])
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
                patch.object(models, "GENERATED_ROOT", root / "exercises"),
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
                    self.assertRegex(
                        response.headers["location"],
                        r"^/exercises/ttx_[a-f0-9]{12}$",
                    )
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

    def test_facilitator_clock_controls_and_auto_delivery(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(models, "DB_PATH", root / "livefirettx.db"),
                patch.object(models, "GENERATED_ROOT", root / "exercises"),
                patch(
                    "app.services.generator.GENERATED_ROOT",
                    root / "exercises",
                ),
            ):
                with TestClient(app) as client:
                    created = client.post(
                        "/exercises",
                        data={
                            "name": "Operations exercise",
                            "scenario_type": "cloud_outage",
                            "platform": "local_docker",
                            "business_system": "Commerce",
                            "difficulty": "intermediate",
                            "duration_minutes": "60",
                            "participants": "Incident Commander, SRE",
                            "objectives": "Assess impact",
                        },
                        follow_redirects=False,
                    )
                    exercise = models.list_exercises()[0]

                    detail = client.get(created.headers["location"])
                    self.assertEqual(200, detail.status_code)
                    self.assertIn("Facilitator Clock", detail.text)
                    self.assertIn("Scheduled Delivery", detail.text)

                    started = client.post(
                        f"/exercises/{exercise.id}/clock/start",
                        follow_redirects=False,
                    )
                    self.assertEqual(303, started.status_code)
                    self.assertEqual("running", models.get_exercise(exercise.id).status)
                    opening = next(
                        inject
                        for inject in models.get_injects(exercise.id)
                        if inject.title == "Initial Situation Brief"
                    )
                    self.assertTrue(opening.triggered)
                    self.assertEqual(1, opening.trigger_count)

                    for command, expected_status in [
                        ("pause", "paused"),
                        ("resume", "running"),
                        ("complete", "completed"),
                        ("reset", "created"),
                    ]:
                        response = client.post(
                            f"/exercises/{exercise.id}/clock/{command}",
                            follow_redirects=False,
                        )
                        self.assertEqual(303, response.status_code)
                        self.assertEqual(
                            expected_status,
                            models.get_exercise(exercise.id).status,
                        )
