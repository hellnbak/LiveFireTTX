from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

from app.models import Exercise, InjectOption
from app.services.runtime import (
    ChaosPreflightError,
    run_chaos_inject,
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
                    )
                )

            self.assertEqual("run_test", result["run_id"])
            self.assertEqual("strict", result["guardrail_profile"])
            payload = request.call_args_list[1].args[1]
            self.assertEqual(600, payload["duration_seconds"])
            self.assertEqual(2500, payload["max_latency_ms"])
            self.assertEqual(0.25, payload["max_error_rate"])

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
                    "version": "0.3.0",
                    "exercise_id": exercise.id,
                }
            )
        )
