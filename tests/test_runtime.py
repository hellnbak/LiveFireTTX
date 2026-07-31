from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import yaml

from app.models import Exercise, InjectOption
from app.services.runtime import (
    ChaosPreflightError,
    clone_playbook_configuration,
    export_playbook_configuration,
    list_playbook_versions,
    restore_playbook_version,
    run_chaos_inject,
    save_playbook_configuration,
    validate_playbook_configuration,
)


class RuntimeSafetyTests(TestCase):
    def test_guarded_inject_requires_matching_ready_controller(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            self.write_control_metadata(exercise)
            inject = self.guarded_inject(exercise)
            with patch(
                "app.services.runtime._request_json",
                return_value={
                    "exercise_id": "ttx_other",
                    "ready": True,
                    "target": {"reachable": True},
                },
            ):
                with self.assertRaisesRegex(
                    ChaosPreflightError,
                    "different exercise",
                ):
                    run_chaos_inject(
                        exercise,
                        inject,
                        guardrail_profile="strict",
                    )

    def test_guarded_inject_sends_duration_and_stop_conditions(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            self.write_control_metadata(exercise)
            inject = self.guarded_inject(exercise)
            with patch(
                "app.services.runtime._request_json",
                side_effect=[
                    {
                        "exercise_id": exercise.id,
                        "ready": True,
                        "target": {"reachable": True},
                    },
                    {
                        "ok": True,
                        "run_id": "run_test",
                        "status": "active",
                    },
                ],
            ) as request:
                result = json.loads(
                    run_chaos_inject(
                        exercise,
                        inject,
                        intensity="high",
                        duration_seconds=600,
                        guardrail_profile="strict",
                        pattern="burst",
                    )
                )

            self.assertEqual("run_test", result["run_id"])
            self.assertEqual("strict", result["guardrail_profile"])
            payload = request.call_args_list[1].args[1]
            self.assertEqual(600, payload["duration_seconds"])
            self.assertEqual("burst", payload["pattern"])
            self.assertEqual(2500, payload["max_latency_ms"])
            self.assertEqual(0.25, payload["max_error_rate"])

    def test_playbook_save_validates_remotely_and_persists_yaml(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            self.write_control_metadata(exercise)
            normalized = {
                "id": "response_drill",
                "name": "Response Drill",
                "seed": 42,
                "safety": {
                    "max_concurrent_actions": 1,
                    "max_severity_points": 2,
                    "max_playbook_seconds": 300,
                },
                "stages": [
                    {
                        "id": "degrade",
                        "action": "app_degradation",
                        "intensity": "medium",
                        "pattern": "ramp",
                        "duration_seconds": 60,
                        "start_after_seconds": 0,
                    }
                ],
            }
            with patch(
                "app.services.runtime._request_json",
                side_effect=[
                    {
                        "exercise_id": exercise.id,
                        "ready": True,
                        "target": {"reachable": True},
                    },
                    normalized,
                ],
            ) as request:
                saved = save_playbook_configuration(
                    exercise,
                    """
id: response_drill
name: Response Drill
stages:
  - id: degrade
    action: app_degradation
""",
                )

            self.assertEqual(normalized, saved)
            self.assertEqual("PUT", request.call_args_list[1].kwargs["method"])
            persisted = (
                Path(exercise.package_path)
                / "chaos"
                / "playbooks"
                / "response_drill.yml"
            )
            self.assertTrue(persisted.is_file())
            self.assertEqual(normalized, yaml.safe_load(persisted.read_text()))

    def test_playbook_version_clone_restore_and_export_workflow(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            playbook_root = Path(temporary) / "chaos" / "playbooks"
            playbook_root.mkdir(parents=True)
            original = self.playbook("scenario_cascade", "Original")
            playbook_path = playbook_root / "scenario_cascade.yml"
            playbook_path.write_text(yaml.safe_dump(original, sort_keys=False))

            def accept_configuration(
                exercise,
                endpoint,
                payload=None,
                method="POST",
            ):
                return payload

            with patch(
                "app.services.runtime._guarded_request",
                side_effect=accept_configuration,
            ):
                updated = self.playbook("scenario_cascade", "Updated")
                saved = save_playbook_configuration(exercise, updated)
                versions = list_playbook_versions(
                    exercise,
                    "scenario_cascade",
                )
                validated = validate_playbook_configuration(exercise, updated)
                cloned = clone_playbook_configuration(
                    exercise,
                    "scenario_cascade",
                    "scenario_clone",
                    "Scenario Clone",
                )
                restored = restore_playbook_version(
                    exercise,
                    "scenario_cascade",
                    versions[0]["id"],
                )
                with self.assertRaisesRegex(ValueError, "already exists"):
                    clone_playbook_configuration(
                        exercise,
                        "scenario_cascade",
                        "scenario_clone",
                        "Duplicate Clone",
                    )

            self.assertEqual("Updated", saved["name"])
            self.assertEqual("Updated", validated["name"])
            self.assertEqual(1, len(versions))
            self.assertEqual("scenario_clone", cloned["id"])
            self.assertEqual("Original", restored["name"])
            self.assertIn(
                "name: Original",
                export_playbook_configuration(
                    exercise,
                    "scenario_cascade",
                ),
            )

    def test_chaos_script_cannot_escape_generated_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            inject = InjectOption(
                id="inj_test",
                exercise_id=exercise.id,
                stage="02-chaos-options",
                title="Invalid",
                audience="Test",
                description="Test",
                action_type="chaos_script",
                script_name="../outside.py",
                payload={},
            )

            with self.assertRaisesRegex(ValueError, "Invalid chaos script path"):
                run_chaos_inject(exercise, inject)

    def exercise(self, package_path: Path) -> Exercise:
        return Exercise(
            id="ttx_test",
            name="Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=90,
            participants=[],
            objectives=[],
            status="created",
            created_at="2026-01-01T00:00:00+00:00",
            package_path=str(package_path),
        )

    def guarded_inject(self, exercise: Exercise) -> InjectOption:
        return InjectOption(
            id="inj_guarded",
            exercise_id=exercise.id,
            stage="02-chaos-options",
            title="Degrade",
            audience="Test",
            description="Test",
            action_type="chaos_script",
            script_name="chaos_cli.py",
            payload={
                "action": "app_degradation",
                "intensities": ["low", "medium", "high"],
                "durations": [60, 300, 600],
                "patterns": ["steady", "burst"],
                "guardrail_profiles": {
                    "strict": {
                        "max_latency_ms": 2500,
                        "max_error_rate": 0.25,
                        "abort_on_target_unreachable": True,
                    }
                },
            },
        )

    def write_control_metadata(self, exercise: Exercise) -> None:
        chaos_root = Path(exercise.package_path) / "chaos"
        chaos_root.mkdir(parents=True)
        (chaos_root / "control.json").write_text(
            json.dumps(
                {
                    "version": "0.4.0",
                    "exercise_id": exercise.id,
                }
            )
        )

    def playbook(self, playbook_id: str, name: str) -> dict:
        return {
            "id": playbook_id,
            "name": name,
            "description": "Test playbook",
            "seed": 42,
            "safety": {
                "max_concurrent_actions": 1,
                "max_severity_points": 2,
                "max_playbook_seconds": 300,
            },
            "stages": [
                {
                    "id": "degrade",
                    "title": "Degrade",
                    "action": "app_degradation",
                    "intensity": "medium",
                    "pattern": "ramp",
                    "duration_seconds": 60,
                    "start_after_seconds": 0,
                    "guardrail_profile": "standard",
                    "depends_on": [],
                }
            ],
        }
