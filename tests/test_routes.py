from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app import models
from app.config import settings as default_settings
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
                    self.assertEqual("1.4.0", health.json()["version"])
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

    def test_v12_operations_views_workflow_and_one_click_launch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            route_settings = replace(
                default_settings,
                evidence_signing_key_path=root / "evidence-signing.key",
                evidence_retention_days=30,
                evidence_retention_count=2,
            )
            with (
                patch.object(models, "DB_PATH", root / "livefirettx.db"),
                patch.object(models, "GENERATED_ROOT", root / "exercises"),
                patch("app.main.settings", route_settings),
                patch(
                    "app.services.generator.GENERATED_ROOT",
                    root / "exercises",
                ),
            ):
                with TestClient(app) as client:
                    created = client.post(
                        "/exercises",
                        data={
                            "name": "Guided operations",
                            "scenario_type": "cloud_outage",
                            "platform": "local_docker",
                            "business_system": "Commerce",
                            "difficulty": "intermediate",
                            "duration_minutes": "60",
                            "participants": "Incident Commander, SRE",
                            "objectives": "Assess impact\nCommunicate status",
                        },
                        follow_redirects=False,
                    )
                    exercise = models.list_exercises()[0]
                    self.assertEqual(3, len(models.list_checkpoints(exercise.id)))

                    detail = client.get(created.headers["location"])
                    self.assertIn("Master Scenario Events List", detail.text)
                    self.assertIn("One-Click Setup", detail.text)
                    run_mode = client.get(f"/exercises/{exercise.id}/run")
                    self.assertEqual(200, run_mode.status_code)
                    self.assertIn("Facilitator Run Mode", run_mode.text)
                    self.assertIn("Next Action", run_mode.text)
                    presentation = client.get(
                        f"/exercises/{exercise.id}/present"
                    )
                    self.assertEqual(200, presentation.status_code)
                    self.assertNotIn("Executive Status Request", presentation.text)
                    evaluation = client.get(
                        f"/exercises/{exercise.id}/evaluate"
                    )
                    self.assertEqual(200, evaluation.status_code)
                    self.assertIn("Evaluator Workspace", evaluation.text)

                    added_checkpoint = client.post(
                        f"/exercises/{exercise.id}/checkpoints",
                        data={
                            "title": "Business decision",
                            "description": "Review customer impact.",
                            "audience": "Incident Commander",
                            "expected_action": "Choose a recovery path.",
                            "offset_minutes": "30",
                            "objective_index": "0",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, added_checkpoint.status_code)
                    checkpoint = next(
                        item
                        for item in models.list_checkpoints(exercise.id)
                        if item.title == "Business decision"
                    )
                    completed = client.post(
                        f"/checkpoints/{checkpoint.id}/complete",
                        follow_redirects=False,
                    )
                    self.assertEqual(303, completed.status_code)

                    improvement = client.post(
                        f"/exercises/{exercise.id}/improvements",
                        data={
                            "title": "Update escalation path",
                            "owner": "Incident Management",
                            "due_date": "2026-08-30",
                            "notes": "Name the decision owner.",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, improvement.status_code)
                    action = models.list_improvement_actions(exercise.id)[0]
                    updated = client.post(
                        f"/improvements/{action.id}/status/completed",
                        follow_redirects=False,
                    )
                    self.assertEqual(303, updated.status_code)
                    self.assertEqual(
                        "completed",
                        models.get_improvement_action(action.id).status,
                    )

                    with patch(
                        "app.main.run_lab_operation",
                        return_value={
                            "operation": "deploy",
                            "success": True,
                            "output": "Lab ready",
                        },
                    ):
                        launched = client.post(
                            f"/exercises/{exercise.id}/lab/launch",
                            follow_redirects=False,
                        )
                    self.assertEqual(303, launched.status_code)
                    self.assertEqual(
                        "running",
                        models.get_exercise(exercise.id).status,
                    )
                    opening = next(
                        inject
                        for inject in models.get_injects(exercise.id)
                        if inject.title == "Initial Situation Brief"
                    )
                    self.assertTrue(opening.triggered)

                    evidence = client.get(
                        f"/exercises/{exercise.id}/reports/evidence.zip"
                    )
                    self.assertEqual(200, evidence.status_code)
                    self.assertEqual(
                        16,
                        len(evidence.headers["x-livefire-evidence-key-id"]),
                    )
                    with ZipFile(BytesIO(evidence.content)) as archive:
                        self.assertIn("manifest.sig", archive.namelist())
                    retained_path = next(
                        (
                            root
                            / "exercises"
                            / exercise.id
                            / "reports"
                            / "evidence"
                        ).glob("*.zip")
                    )
                    retained = client.get(
                        f"/exercises/{exercise.id}/reports/evidence/"
                        f"{retained_path.name}"
                    )
                    self.assertEqual(200, retained.status_code)
                    refreshed = client.get(f"/exercises/{exercise.id}")
                    self.assertIn("Signed &amp; Retained Exports", refreshed.text)
                    self.assertIn("Verified", refreshed.text)

    def test_v13_design_library_profile_and_pack_workflow(self) -> None:
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
                    library = client.get("/library")
                    self.assertEqual(200, library.status_code)
                    self.assertIn("Portable Exercise Design", library.text)
                    self.assertIn("Import Scenario Pack", library.text)

                    profile_response = client.post(
                        "/library/profiles",
                        data={
                            "slug": "commerce-response",
                            "name": "Commerce Response",
                            "version": "1.0.0",
                            "description": "Commerce exercise context.",
                            "business_system": "Checkout Platform",
                            "participants": "Incident Commander, SRE",
                            "objectives": "Assess impact\nRecover safely",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, profile_response.status_code)
                    profile = models.list_organization_profiles()[0]
                    pack = next(
                        item
                        for item in models.list_scenario_packs()
                        if item.base_scenario_type == "cloud_outage"
                    )
                    created = client.post(
                        f"/library/packs/{pack.id}/exercises",
                        data={
                            "exercise_name": "Library exercise",
                            "organization_profile_id": profile.id,
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, created.status_code)
                    exercise = models.list_exercises()[0]
                    self.assertEqual(pack.id, exercise.scenario_pack_id)
                    self.assertEqual(profile.id, exercise.organization_profile_id)
                    self.assertEqual("Checkout Platform", exercise.business_system)

                    captured = client.post(
                        f"/exercises/{exercise.id}/scenario-pack",
                        data={
                            "slug": "library-exercise",
                            "name": "Library Exercise",
                            "version": "1.1.0",
                            "description": "Captured portable exercise design.",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, captured.status_code)
                    captured_pack = models.find_scenario_pack(
                        "library-exercise",
                        "1.1.0",
                    )
                    exported = client.get(
                        f"/library/packs/{captured_pack.id}/export.json"
                    )
                    self.assertEqual(200, exported.status_code)
                    self.assertIn(
                        "application/vnd.livefirettx.scenario-pack+json",
                        exported.headers["content-type"],
                    )
                    self.assertNotIn(exercise.id, exported.text)
