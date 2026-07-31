from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os
import subprocess
import sys
import yaml

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
                        compose_config = yaml.safe_load(compose)
                        self.assertEqual(
                            {"livefire-target", "livefire-chaos"},
                            set(compose_config["services"]),
                        )
                        self.assertIn("127.0.0.1:8088:8088", compose)
                        self.assertIn("127.0.0.1:8090:8090", compose)
                        self.assertIn(
                            "LIVEFIRE_TARGET_URL=http://livefire-target:8088",
                            compose,
                        )
                        control = json.loads(
                            (chaos_root / "control.json").read_text()
                        )
                        self.assertEqual("0.3.0", control["version"])
                        self.assertEqual(exercise.id, control["exercise_id"])

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
                                "--duration",
                                "60",
                                "--skip-preflight",
                            )
                            self.assertTrue(result["ok"])
                            self.assertEqual(action, result["action"])
                            self.assertEqual("active", result["status"])
                            self.assertTrue(result["expires_at"])

                        state = self.run_cli(chaos_root, "state")
                        self.assertEqual(set(action_ids), set(state["active_actions"]))
                        self.assertEqual(
                            {"active"},
                            {run["status"] for run in state["runs"]},
                        )

                        reset = self.run_cli(chaos_root, "reset")
                        self.assertTrue(reset["ok"])
                        self.assertEqual("all", reset["reset"])
                        state = self.run_cli(chaos_root, "state")
                        self.assertFalse(state["active_actions"])
                        self.assertFalse(any(state["conditions"].values()))
                        self.assertEqual(
                            {"aborted"},
                            {run["status"] for run in state["runs"]},
                        )
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
                script = """
import json
import server

healthy = {
    "reachable": True,
    "matches_exercise": True,
    "exercise_id": server.EXERCISE_ID,
    "healthy": True,
    "conditions": {"latency_ms": 0, "error_rate": 0.0},
}
server.target_snapshot = lambda: healthy
paths = sorted(route.path for route in server.app.routes)
applied = server.apply_action(
    "app_degradation",
    server.ActionRequest(
        intensity="high",
        duration_seconds=60,
        max_latency_ms=2500,
        max_error_rate=0.25,
    ),
)
state = server.state()
violation = server.guardrail_violation(
    state["active_actions"]["app_degradation"],
    {
        **healthy,
        "healthy": False,
        "conditions": {"latency_ms": 3000, "error_rate": 0.4},
    },
)
stopped = server.emergency_stop()
server.target_snapshot = lambda: {
    "reachable": False,
    "matches_exercise": False,
    "error": "offline",
}
try:
    server.apply_action("dns_failure", server.ActionRequest())
except server.HTTPException:
    pass
final_state = server.state()
print(json.dumps({
    "paths": paths,
    "applied": applied,
    "state": state,
    "violation": violation,
    "stopped": stopped,
    "final_state": final_state,
}))
"""
                process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        script,
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
                self.assertIn("/runs", result["paths"])
                self.assertIn("/emergency-stop", result["paths"])
                self.assertTrue(result["applied"]["ok"])
                self.assertEqual(
                    3000,
                    result["applied"]["conditions"]["latency_ms"],
                )
                self.assertIn(
                    "app_degradation",
                    result["state"]["active_actions"],
                )
                self.assertEqual(
                    "latency_threshold_exceeded",
                    result["violation"],
                )
                self.assertEqual(
                    "emergency_stop",
                    result["stopped"]["reason"],
                )
                self.assertFalse(result["final_state"]["active_actions"])
                self.assertEqual(
                    ["aborted", "failed"],
                    [
                        run["status"]
                        for run in result["final_state"]["runs"]
                    ],
                )

    def test_timed_run_reconciles_to_completed(self) -> None:
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
                started = self.run_cli(
                    chaos_root,
                    "run",
                    "app_degradation",
                    "--duration",
                    "60",
                    "--skip-preflight",
                )
                state_path = chaos_root / "state" / "state.json"
                persisted = json.loads(state_path.read_text())
                persisted["active_actions"]["app_degradation"][
                    "expires_at"
                ] = "2000-01-01T00:00:00+00:00"
                state_path.write_text(json.dumps(persisted))
                target_environment = {
                    **os.environ,
                    "LIVEFIRE_STATE_DIR": str(chaos_root / "state"),
                }
                target_process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import json, target_app; "
                            "print(json.dumps(target_app.health()))"
                        ),
                    ],
                    cwd=Path(exercise.package_path) / "target" / "app",
                    env=target_environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    0,
                    target_process.returncode,
                    target_process.stderr,
                )
                target_health = json.loads(target_process.stdout)
                self.assertTrue(target_health["healthy"])
                self.assertFalse(any(target_health["conditions"].values()))

                process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import json, engine; "
                            "state=engine.reconcile_expired('2099-01-01T00:00:00+00:00'); "
                            "print(json.dumps(state))"
                        ),
                    ],
                    cwd=chaos_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, process.returncode, process.stderr)
                state = json.loads(process.stdout)
                self.assertFalse(state["active_actions"])
                self.assertFalse(any(state["conditions"].values()))
                run = next(
                    run
                    for run in state["runs"]
                    if run["id"] == started["run_id"]
                )
                self.assertEqual("completed", run["status"])
                self.assertEqual("duration_elapsed", run["reason"])

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
