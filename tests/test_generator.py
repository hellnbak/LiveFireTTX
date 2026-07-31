from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os
import subprocess
import sys

from app.models import ExerciseCreate, SCENARIO_LIBRARY
from app.services.generator import create_exercise_from_request


class GeneratedPackageTests(TestCase):
    def test_every_scenario_generates_runnable_chaos_controls(self) -> None:
        with TemporaryDirectory() as temporary:
            generated_root = Path(temporary)
            with patch(
                "app.services.generator.GENERATED_ROOT",
                generated_root,
            ):
                for index, scenario_type in enumerate(SCENARIO_LIBRARY):
                    with self.subTest(scenario_type=scenario_type):
                        name = 'Exercise "quoted"\nname' if index == 0 else "Exercise"
                        exercise, injects = create_exercise_from_request(
                            ExerciseCreate(
                                name=name,
                                scenario_type=scenario_type,
                            )
                        )
                        package = Path(exercise.package_path)
                        chaos_root = package / "chaos"

                        for source in [
                            package / "target" / "app" / "target_app.py",
                            chaos_root / "engine.py",
                            chaos_root / "chaos_cli.py",
                            chaos_root / "server.py",
                        ]:
                            compile(source.read_text(), str(source), "exec")

                        compose = (
                            package / "target" / "docker-compose.yml"
                        ).read_text()
                        self.assertIn("127.0.0.1:8088:8088", compose)
                        self.assertIn("127.0.0.1:8090:8090", compose)

                        action_ids = [
                            inject.payload["action"]
                            for inject in injects
                            if inject.action_type == "chaos_script"
                        ]
                        self.assertEqual(
                            sorted(
                                SCENARIO_LIBRARY[scenario_type]["chaos_modules"]
                            ),
                            sorted(action_ids),
                        )
                        listed = self.run_cli(chaos_root, "list")
                        self.assertEqual(
                            sorted(action_ids),
                            sorted(listed["actions"]),
                        )

                        for action in action_ids:
                            result = self.run_cli(
                                chaos_root,
                                "run",
                                action,
                                "--intensity",
                                "low",
                            )
                            self.assertTrue(result["ok"])
                            self.assertEqual(action, result["action"])

                        state = self.run_cli(chaos_root, "state")
                        self.assertEqual(set(action_ids), set(state["active_actions"]))
                        self.assertEqual(len(action_ids), state["revision"])

                        reset = self.run_cli(chaos_root, "reset")
                        self.assertTrue(reset["ok"])
                        self.assertEqual("all", reset["reset"])
                        state = self.run_cli(chaos_root, "state")
                        self.assertFalse(state["active_actions"])
                        self.assertFalse(any(state["conditions"].values()))
                        self.assertFalse(
                            list((package / "artifacts").rglob("*.locked"))
                        )

    def test_scenario_allowlist_rejects_unavailable_action(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch(
                "app.services.generator.GENERATED_ROOT",
                Path(temporary),
            ):
                exercise, _ = create_exercise_from_request(
                    ExerciseCreate(
                        name="Identity exercise",
                        scenario_type="identity_outage",
                    )
                )
                chaos_root = Path(exercise.package_path) / "chaos"
                process = subprocess.run(
                    [
                        sys.executable,
                        str(chaos_root / "chaos_cli.py"),
                        "run",
                        "app_degradation",
                    ],
                    cwd=chaos_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(2, process.returncode)
                self.assertIn("not available", process.stderr)

    def test_generated_api_applies_and_resets_action(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch(
                "app.services.generator.GENERATED_ROOT",
                Path(temporary),
            ):
                exercise, _ = create_exercise_from_request(
                    ExerciseCreate(
                        name="Cloud exercise",
                        scenario_type="cloud_outage",
                    )
                )
                chaos_root = Path(exercise.package_path) / "chaos"
                environment = {
                    **os.environ,
                    "LIVEFIRE_STATE_DIR": str(chaos_root / "state"),
                    "LIVEFIRE_ARTIFACTS_DIR": str(
                        Path(exercise.package_path) / "artifacts"
                    ),
                }
                process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import json, server; "
                            "paths=sorted(r.path for r in server.app.routes); "
                            "applied=server.apply_action("
                            "'app_degradation', server.ActionRequest(intensity='high')); "
                            "state=server.state(); "
                            "reset=server.reset_all(); "
                            "print(json.dumps({'paths': paths, 'applied': applied, "
                            "'state': state, 'reset': reset}))"
                        ),
                    ],
                    cwd=chaos_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, process.returncode, process.stderr)
                result = json.loads(process.stdout)
                self.assertIn("/actions/{action}", result["paths"])
                self.assertIn("/state", result["paths"])
                self.assertIn("/reset", result["paths"])
                self.assertTrue(result["applied"]["ok"])
                self.assertEqual(
                    3000,
                    result["applied"]["conditions"]["latency_ms"],
                )
                self.assertIn(
                    "app_degradation",
                    result["state"]["active_actions"],
                )
                self.assertEqual("all", result["reset"]["reset"])
                self.assertFalse(any(result["reset"]["conditions"].values()))

    def run_cli(self, chaos_root: Path, *arguments: str) -> dict:
        process = subprocess.run(
            [
                sys.executable,
                str(chaos_root / "chaos_cli.py"),
                *arguments,
            ],
            cwd=chaos_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, process.returncode, process.stderr)
        return json.loads(process.stdout)
