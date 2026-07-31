# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import Any
import json
import stat

import yaml

from app.models import Exercise, InjectOption


ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "app_degradation": {
        "label": "Application Degradation",
        "description": "Adds controlled latency and intermittent synthetic errors.",
        "reversible": True,
    },
    "auth_failure": {
        "label": "Authentication Failure",
        "description": "Makes the simulated login endpoint fail at a controlled rate.",
        "reversible": True,
    },
    "backup_restore_delay": {
        "label": "Backup Restore Delay",
        "description": "Marks backup freshness and restore timing as uncertain.",
        "reversible": True,
    },
    "data_corruption": {
        "label": "Test Data Integrity Failure",
        "description": "Returns inconsistent values in seeded, non-sensitive test records.",
        "reversible": True,
    },
    "dependency_alert": {
        "label": "Dependency Integrity Alert",
        "description": "Blocks the simulated build and creates a vendor advisory.",
        "reversible": True,
    },
    "dns_failure": {
        "label": "Dependency DNS Failure",
        "description": "Makes the simulated DNS dependency fail at a controlled rate.",
        "reversible": True,
    },
    "safe_file_impact": {
        "label": "Safe File Impact",
        "description": "Renames generated test files and creates a clearly simulated note.",
        "reversible": True,
    },
    "synthetic_edr_alert": {
        "label": "Synthetic EDR Alerts",
        "description": "Creates safe alert artifacts without executing malicious behavior.",
        "reversible": True,
    },
}


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_target_environment(root: Path, exercise: Exercise) -> None:
    compose = dedent(
        """
        services:
          livefire-target:
            build: ./app
            ports:
              - "127.0.0.1:8088:8088"
            volumes:
              - ../artifacts:/artifacts
              - ../chaos/state:/chaos_state
            environment:
              - LIVEFIRE_APP_NAME=LiveFireTTX Target
              - LIVEFIRE_STATE_DIR=/chaos_state

          livefire-chaos:
            build: ../chaos
            ports:
              - "127.0.0.1:8090:8090"
            volumes:
              - ../artifacts:/artifacts
              - ../chaos/state:/chaos_state
            environment:
              - LIVEFIRE_STATE_DIR=/chaos_state
              - LIVEFIRE_ARTIFACTS_DIR=/artifacts
            healthcheck:
              test:
                - CMD
                - python
                - -c
                - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health')"
              interval: 5s
              timeout: 2s
              retries: 10
        """
    )
    (root / "target" / "docker-compose.yml").write_text(compose)

    dockerfile = dedent(
        """
        FROM python:3.12-slim
        WORKDIR /app
        COPY target_app.py /app/target_app.py
        RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0
        CMD ["uvicorn", "target_app:app", "--host", "0.0.0.0", "--port", "8088"]
        """
    )
    (root / "target" / "app" / "Dockerfile").write_text(dockerfile)

    target_app = dedent(
        r'''
        from pathlib import Path
        import json
        import os
        import random
        import time

        from fastapi import FastAPI, HTTPException


        app = FastAPI(title="LiveFireTTX Target")
        STATE_PATH = (
            Path(os.environ.get("LIVEFIRE_STATE_DIR", "/chaos_state")) / "state.json"
        )
        APP_NAME = __BUSINESS_SYSTEM__
        EXERCISE_NAME = __EXERCISE_NAME__
        DEFAULT_CONDITIONS = {
            "latency_ms": 0,
            "error_rate": 0.0,
            "auth_failure_rate": 0.0,
            "dns_failure_rate": 0.0,
            "data_integrity": False,
            "backup_delay": False,
            "build_blocked": False,
            "file_impact": False,
        }


        def read_state():
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not STATE_PATH.exists():
                return {"revision": 0, "active_actions": {}, "conditions": DEFAULT_CONDITIONS}
            try:
                state = json.loads(STATE_PATH.read_text())
            except json.JSONDecodeError:
                return {"revision": 0, "active_actions": {}, "conditions": DEFAULT_CONDITIONS}
            if "conditions" not in state:
                legacy = state
                state = {
                    "revision": 0,
                    "active_actions": {},
                    "conditions": {
                        **DEFAULT_CONDITIONS,
                        "latency_ms": 1500 if legacy.get("degraded") else 0,
                        "auth_failure_rate": 1.0 if legacy.get("auth_failure") else 0.0,
                        "dns_failure_rate": 1.0 if legacy.get("dns_failure") else 0.0,
                    },
                }
            return state


        def conditions():
            return {**DEFAULT_CONDITIONS, **read_state().get("conditions", {})}


        def maybe_fail(rate, detail):
            if rate and random.random() < float(rate):
                raise HTTPException(status_code=503, detail=detail)


        @app.get("/")
        def home():
            state = read_state()
            current = {**DEFAULT_CONDITIONS, **state.get("conditions", {})}
            if current["latency_ms"]:
                time.sleep(float(current["latency_ms"]) / 1000)
            maybe_fail(current["error_rate"], "Synthetic application error")
            return {
                "app": APP_NAME,
                "exercise": EXERCISE_NAME,
                "status": "degraded" if any(current.values()) else "healthy",
                "state_revision": state.get("revision", 0),
                "active_actions": state.get("active_actions", {}),
                "message": "This is a simulated target environment for LiveFireTTX.",
            }


        @app.get("/health")
        def health():
            state = read_state()
            current = {**DEFAULT_CONDITIONS, **state.get("conditions", {})}
            return {
                "healthy": not any(current.values()),
                "conditions": current,
                "state_revision": state.get("revision", 0),
            }


        @app.get("/orders")
        def orders():
            current = conditions()
            orders = [
                {"order_id": "ORD-1001", "status": "processing", "amount": 123.45},
                {"order_id": "ORD-1002", "status": "paid", "amount": 88.10},
                {"order_id": "ORD-1003", "status": "pending_review", "amount": 451.19},
            ]
            if current["data_integrity"]:
                orders[1]["amount"] = 8808.10
                orders[1]["integrity_warning"] = "Synthetic mismatch"
            return orders


        @app.post("/auth/login")
        def login():
            current = conditions()
            maybe_fail(current["auth_failure_rate"], "Synthetic identity provider failure")
            return {"authenticated": True, "mode": "simulated"}


        @app.get("/dependencies/dns")
        def dns_dependency():
            current = conditions()
            maybe_fail(current["dns_failure_rate"], "Synthetic DNS resolution failure")
            return {"resolved": True, "provider": "simulated"}


        @app.get("/backups/status")
        def backup_status():
            delayed = bool(conditions()["backup_delay"])
            return {
                "status": "delayed" if delayed else "current",
                "restore_eta_minutes": 75 if delayed else 10,
                "simulated": True,
            }


        @app.get("/build/status")
        def build_status():
            blocked = bool(conditions()["build_blocked"])
            return {
                "status": "blocked" if blocked else "passing",
                "reason": "Synthetic dependency integrity alert" if blocked else None,
            }
        '''
    )
    target_app = target_app.replace(
        "__BUSINESS_SYSTEM__",
        repr(exercise.business_system),
    ).replace(
        "__EXERCISE_NAME__",
        repr(exercise.name),
    )
    (root / "target" / "app" / "target_app.py").write_text(target_app)

    write_executable(
        root / "target" / "deploy.sh",
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            docker compose up -d --build
            echo 'Target: http://127.0.0.1:8088'
            echo 'Chaos control API: http://127.0.0.1:8090/docs'
            """
        ),
    )
    write_executable(
        root / "target" / "validate.sh",
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            curl --fail --silent http://127.0.0.1:8088/health
            echo
            curl --fail --silent http://127.0.0.1:8090/health
            echo
            """
        ),
    )


def render_chaos_environment(
    root: Path,
    exercise: Exercise,
    injects: list[InjectOption],
) -> None:
    allowed_actions = sorted(
        {
            str(inject.payload["action"])
            for inject in injects
            if inject.action_type == "chaos_script" and inject.payload.get("action")
        }
    )
    state_dir = root / "chaos" / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(_default_state(), indent=2, sort_keys=True)
    )

    engine = _engine_source().replace(
        "__ALLOWED_ACTIONS__",
        repr(allowed_actions),
    )
    (root / "chaos" / "engine.py").write_text(engine)
    write_executable(root / "chaos" / "chaos_cli.py", _cli_source())
    (root / "chaos" / "server.py").write_text(_server_source())
    (root / "chaos" / "Dockerfile").write_text(
        dedent(
            """
            FROM python:3.12-slim
            WORKDIR /app
            COPY engine.py server.py /app/
            RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0
            CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
            """
        )
    )

    plan = {
        "exercise_id": exercise.id,
        "safe_only": True,
        "control_api": "http://127.0.0.1:8090",
        "cli": "python3 chaos_cli.py",
        "intensities": ["low", "medium", "high"],
        "available_actions": [
            {"id": action, **ACTION_CATALOG[action]}
            for action in allowed_actions
        ],
    }
    (root / "chaos" / "chaos-plan.yml").write_text(
        yaml.safe_dump(plan, sort_keys=False)
    )
    (root / "chaos" / "README.md").write_text(
        dedent(
            f"""
            # LiveFireTTX Chaos Control

            This package exposes safe, scenario-scoped chaos actions through both a
            local CLI and an HTTP API. It only changes generated test state and
            synthetic artifacts inside this exercise package.

            ## CLI

            ```bash
            python3 chaos_cli.py list
            python3 chaos_cli.py run {allowed_actions[0] if allowed_actions else "ACTION_ID"} --intensity medium
            python3 chaos_cli.py state
            python3 chaos_cli.py reset
            ```

            ## API

            Deploy the target package, then open `http://127.0.0.1:8090/docs`.
            The API supports listing actions, applying an action, reading state,
            resetting one action, and resetting the entire simulation.
            """
        )
    )


def _default_state() -> dict[str, Any]:
    return {
        "revision": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "active_actions": {},
        "conditions": {
            "latency_ms": 0,
            "error_rate": 0.0,
            "auth_failure_rate": 0.0,
            "dns_failure_rate": 0.0,
            "data_integrity": False,
            "backup_delay": False,
            "build_blocked": False,
            "file_impact": False,
        },
        "history": [],
    }


def _engine_source() -> str:
    return dedent(
        r'''
        from contextlib import contextmanager
        from datetime import datetime, timezone
        from pathlib import Path
        import json
        import os

        try:
            import fcntl
        except ImportError:
            fcntl = None


        ROOT = Path(__file__).resolve().parent
        STATE_DIR = Path(os.environ.get("LIVEFIRE_STATE_DIR", ROOT / "state"))
        ARTIFACTS_DIR = Path(
            os.environ.get("LIVEFIRE_ARTIFACTS_DIR", ROOT.parent / "artifacts")
        )
        STATE_PATH = STATE_DIR / "state.json"
        LOCK_PATH = STATE_DIR / "state.lock"
        ALLOWED_ACTIONS = set(__ALLOWED_ACTIONS__)
        INTENSITY_PROFILES = {
            "low": {"rate": 0.2, "latency_ms": 400, "error_rate": 0.02, "count": 3},
            "medium": {"rate": 0.6, "latency_ms": 1500, "error_rate": 0.15, "count": 6},
            "high": {"rate": 1.0, "latency_ms": 3000, "error_rate": 0.4, "count": 10},
        }
        ACTION_CATALOG = {
            "app_degradation": {
                "label": "Application Degradation",
                "description": "Adds controlled latency and intermittent synthetic errors.",
                "reversible": True,
            },
            "auth_failure": {
                "label": "Authentication Failure",
                "description": "Makes the simulated login endpoint fail at a controlled rate.",
                "reversible": True,
            },
            "backup_restore_delay": {
                "label": "Backup Restore Delay",
                "description": "Marks backup freshness and restore timing as uncertain.",
                "reversible": True,
            },
            "data_corruption": {
                "label": "Test Data Integrity Failure",
                "description": "Returns inconsistent values in seeded test records.",
                "reversible": True,
            },
            "dependency_alert": {
                "label": "Dependency Integrity Alert",
                "description": "Blocks the simulated build and creates a vendor advisory.",
                "reversible": True,
            },
            "dns_failure": {
                "label": "Dependency DNS Failure",
                "description": "Makes the simulated DNS dependency fail at a controlled rate.",
                "reversible": True,
            },
            "safe_file_impact": {
                "label": "Safe File Impact",
                "description": "Renames generated test files and creates a clearly simulated note.",
                "reversible": True,
            },
            "synthetic_edr_alert": {
                "label": "Synthetic EDR Alerts",
                "description": "Creates safe alert artifacts without executing malicious behavior.",
                "reversible": True,
            },
        }
        DEFAULT_CONDITIONS = {
            "latency_ms": 0,
            "error_rate": 0.0,
            "auth_failure_rate": 0.0,
            "dns_failure_rate": 0.0,
            "data_integrity": False,
            "backup_delay": False,
            "build_blocked": False,
            "file_impact": False,
        }
        RESET_FIELDS = {
            "app_degradation": {"latency_ms": 0, "error_rate": 0.0},
            "auth_failure": {"auth_failure_rate": 0.0},
            "backup_restore_delay": {"backup_delay": False},
            "data_corruption": {"data_integrity": False},
            "dependency_alert": {"build_blocked": False},
            "dns_failure": {"dns_failure_rate": 0.0},
            "safe_file_impact": {"file_impact": False},
            "synthetic_edr_alert": {},
        }


        def timestamp():
            return datetime.now(timezone.utc).isoformat()


        def default_state():
            return {
                "revision": 0,
                "updated_at": timestamp(),
                "active_actions": {},
                "conditions": dict(DEFAULT_CONDITIONS),
                "history": [],
            }


        def normalize_state(state):
            if "conditions" not in state:
                legacy = state
                state = default_state()
                state["conditions"].update(
                    {
                        "latency_ms": 1500 if legacy.get("degraded") else 0,
                        "auth_failure_rate": 1.0 if legacy.get("auth_failure") else 0.0,
                        "dns_failure_rate": 1.0 if legacy.get("dns_failure") else 0.0,
                    }
                )
            state["conditions"] = {
                **DEFAULT_CONDITIONS,
                **state.get("conditions", {}),
            }
            state.setdefault("active_actions", {})
            state.setdefault("history", [])
            state.setdefault("revision", 0)
            state.setdefault("updated_at", timestamp())
            return state


        def read_state_unlocked():
            if not STATE_PATH.exists():
                return default_state()
            try:
                return normalize_state(json.loads(STATE_PATH.read_text()))
            except json.JSONDecodeError:
                return default_state()


        def write_state_unlocked(state):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            temporary = STATE_PATH.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(state, indent=2, sort_keys=True))
            temporary.replace(STATE_PATH)


        @contextmanager
        def state_lock():
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with LOCK_PATH.open("a+") as lock:
                if fcntl:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


        def available_actions():
            return {
                action: ACTION_CATALOG[action]
                for action in sorted(ALLOWED_ACTIONS)
                if action in ACTION_CATALOG
            }


        def get_state():
            with state_lock():
                return read_state_unlocked()


        def perform_action(action, intensity="medium"):
            if action not in ALLOWED_ACTIONS or action not in ACTION_CATALOG:
                raise ValueError(f"Action is not available for this exercise: {action}")
            if intensity not in INTENSITY_PROFILES:
                raise ValueError(f"Unsupported intensity: {intensity}")

            profile = INTENSITY_PROFILES[intensity]
            with state_lock():
                state = read_state_unlocked()
                artifacts = apply_effect(state, action, intensity, profile)
                applied_at = timestamp()
                state["active_actions"][action] = {
                    "intensity": intensity,
                    "applied_at": applied_at,
                }
                state["revision"] += 1
                state["updated_at"] = applied_at
                event = {
                    "type": "action_applied",
                    "action": action,
                    "intensity": intensity,
                    "at": applied_at,
                    "artifacts": artifacts,
                }
                state["history"] = (state["history"] + [event])[-100:]
                write_state_unlocked(state)
                return {
                    "ok": True,
                    "action": action,
                    "intensity": intensity,
                    "revision": state["revision"],
                    "artifacts": artifacts,
                    "conditions": state["conditions"],
                }


        def reset(action=None):
            if action and (action not in ALLOWED_ACTIONS or action not in ACTION_CATALOG):
                raise ValueError(f"Action is not available for this exercise: {action}")

            with state_lock():
                state = read_state_unlocked()
                if action:
                    reverse_effect(action)
                    state["conditions"].update(RESET_FIELDS[action])
                    state["active_actions"].pop(action, None)
                    reset_action = action
                else:
                    for active_action in state["active_actions"]:
                        reverse_effect(active_action)
                    state["conditions"] = dict(DEFAULT_CONDITIONS)
                    state["active_actions"] = {}
                    reset_action = "all"
                reset_at = timestamp()
                state["revision"] += 1
                state["updated_at"] = reset_at
                state["history"] = (
                    state["history"]
                    + [{"type": "reset", "action": reset_action, "at": reset_at}]
                )[-100:]
                write_state_unlocked(state)
                return {
                    "ok": True,
                    "reset": reset_action,
                    "revision": state["revision"],
                    "conditions": state["conditions"],
                }


        def reverse_effect(action):
            if action != "safe_file_impact":
                return
            artifact_root = ARTIFACTS_DIR / "chaos"
            for lab in artifact_root.glob("*_safe_file_impact"):
                for locked_file in lab.glob("*.locked"):
                    original = locked_file.with_suffix("")
                    if not original.exists():
                        locked_file.rename(original)


        def apply_effect(state, action, intensity, profile):
            conditions = state["conditions"]
            if action == "app_degradation":
                conditions["latency_ms"] = profile["latency_ms"]
                conditions["error_rate"] = profile["error_rate"]
            elif action == "auth_failure":
                conditions["auth_failure_rate"] = profile["rate"]
            elif action == "backup_restore_delay":
                conditions["backup_delay"] = True
            elif action == "data_corruption":
                conditions["data_integrity"] = True
            elif action == "dependency_alert":
                conditions["build_blocked"] = True
            elif action == "dns_failure":
                conditions["dns_failure_rate"] = profile["rate"]
            elif action == "safe_file_impact":
                conditions["file_impact"] = True
            return create_artifacts(action, intensity, profile)


        def create_artifacts(action, intensity, profile):
            artifact_root = ARTIFACTS_DIR / "chaos"
            artifact_root.mkdir(parents=True, exist_ok=True)
            label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

            if action == "safe_file_impact":
                lab = artifact_root / f"{label}_safe_file_impact"
                lab.mkdir()
                for index in range(1, profile["count"] + 1):
                    path = lab / f"test_file_{index}.txt"
                    path.write_text("Harmless generated test data for LiveFireTTX.\n")
                    path.rename(path.with_suffix(".txt.locked"))
                (lab / "RANSOM_NOTE_SIMULATED.txt").write_text(
                    "SIMULATED EXERCISE ARTIFACT ONLY. No encryption occurred.\n"
                )
                return [artifact_reference(lab)]

            suffix = "json" if action == "synthetic_edr_alert" else "md"
            path = artifact_root / f"{label}_{action}.{suffix}"
            if action == "synthetic_edr_alert":
                content = {
                    "source": "LiveFireTTX synthetic EDR",
                    "severity": intensity,
                    "count": profile["count"],
                    "title": "Suspicious process behavior detected",
                    "detail": "Synthetic alert only. No malware or exploit code was executed.",
                    "created_at": timestamp(),
                }
                path.write_text(json.dumps(content, indent=2))
            else:
                path.write_text(artifact_markdown(action, intensity, profile))
            return [artifact_reference(path)]


        def artifact_markdown(action, intensity, profile):
            messages = {
                "app_degradation": (
                    f"Latency is {profile['latency_ms']} ms with a "
                    f"{profile['error_rate']:.0%} synthetic error rate."
                ),
                "auth_failure": (
                    f"The simulated identity provider fails approximately "
                    f"{profile['rate']:.0%} of login requests."
                ),
                "backup_restore_delay": (
                    "Last-known-good backup freshness is uncertain and the "
                    "simulated restore ETA has increased."
                ),
                "data_corruption": (
                    "Seeded test order records no longer reconcile with payment totals."
                ),
                "dependency_alert": (
                    "A simulated vendor advisory has blocked the generated build status."
                ),
                "dns_failure": (
                    f"The simulated DNS dependency fails approximately "
                    f"{profile['rate']:.0%} of checks."
                ),
            }
            title = ACTION_CATALOG[action]["label"]
            return (
                f"# {title}\n\n"
                f"Intensity: **{intensity}**\n\n"
                f"{messages[action]}\n\n"
                "This is a safe LiveFireTTX exercise artifact.\n"
            )


        def artifact_reference(path):
            try:
                return str(path.relative_to(ARTIFACTS_DIR.parent))
            except ValueError:
                return str(path)
        '''
    )


def _cli_source() -> str:
    return dedent(
        '''\
        #!/usr/bin/env python3
        import argparse
        import json
        import sys

        from engine import available_actions, get_state, perform_action, reset


        def main():
            parser = argparse.ArgumentParser(description="LiveFireTTX safe chaos control")
            commands = parser.add_subparsers(dest="command", required=True)
            commands.add_parser("list", help="List scenario-scoped actions")
            commands.add_parser("state", help="Show current chaos state")

            run_parser = commands.add_parser("run", help="Apply a safe chaos action")
            run_parser.add_argument("action")
            run_parser.add_argument(
                "--intensity",
                choices=["low", "medium", "high"],
                default="medium",
            )

            reset_parser = commands.add_parser("reset", help="Reset one action or all state")
            reset_parser.add_argument("action", nargs="?")
            args = parser.parse_args()

            try:
                if args.command == "list":
                    result = {"actions": available_actions()}
                elif args.command == "state":
                    result = get_state()
                elif args.command == "run":
                    result = perform_action(args.action, args.intensity)
                else:
                    result = reset(args.action)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2

            print(json.dumps(result, indent=2, sort_keys=True))
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    )


def _server_source() -> str:
    return dedent(
        '''
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel

        from engine import available_actions, get_state, perform_action, reset


        app = FastAPI(
            title="LiveFireTTX Safe Chaos Control",
            description=(
                "Scenario-scoped, reversible simulation controls. "
                "This API does not execute exploits or destructive payloads."
            ),
            version="0.2.0",
        )


        class ActionRequest(BaseModel):
            intensity: str = "medium"


        @app.get("/health")
        def health():
            state = get_state()
            return {"healthy": True, "revision": state["revision"]}


        @app.get("/actions")
        def actions():
            return {"actions": available_actions()}


        @app.get("/state")
        def state():
            return get_state()


        @app.post("/actions/{action}")
        def apply_action(action: str, request: ActionRequest):
            try:
                return perform_action(action, request.intensity)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc


        @app.post("/reset")
        def reset_all():
            return reset()


        @app.post("/reset/{action}")
        def reset_one(action: str):
            try:
                return reset(action)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        '''
    )
