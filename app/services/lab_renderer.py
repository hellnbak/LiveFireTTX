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

from app.models import Exercise, InjectOption, SCENARIO_LIBRARY


TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"
CONTROL_VERSION = "1.0.0"
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
    "object_storage_throttle": {
        "label": "Object Storage Throttling",
        "description": "Adds synthetic throttling and stale reads to local object storage.",
        "reversible": True,
    },
    "payment_failure": {
        "label": "Payment Processor Failure",
        "description": "Makes simulated payment authorization fail at a controlled rate.",
        "reversible": True,
    },
    "queue_backlog": {
        "label": "Queue Backlog",
        "description": "Builds a synthetic backlog and delays the local consumer.",
        "reversible": True,
    },
    "safe_file_impact": {
        "label": "Safe File Impact",
        "description": "Renames generated test files and creates a simulated note.",
        "reversible": True,
    },
    "synthetic_edr_alert": {
        "label": "Synthetic EDR Alerts",
        "description": "Creates safe alerts without executing malicious behavior.",
        "reversible": True,
    },
    "telemetry_gap": {
        "label": "Observability Gap",
        "description": "Delays or drops simulated telemetry without hiding real activity.",
        "reversible": True,
    },
    "third_party_degradation": {
        "label": "Third-Party API Degradation",
        "description": "Adds controlled vendor API failures and rate-limit responses.",
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
    "object_storage_throttle_rate": 0.0,
    "payment_failure_rate": 0.0,
    "queue_backlog_depth": 0,
    "queue_consumer_delay_ms": 0,
    "stale_read_rate": 0.0,
    "telemetry_delay_seconds": 0,
    "telemetry_gap_rate": 0.0,
    "third_party_error_rate": 0.0,
    "third_party_retry_after_seconds": 0,
}


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_target_environment(root: Path, exercise: Exercise) -> None:
    compose = dedent(
        f"""
        services:
          livefire-target:
            build: ./app
            user: "${{LIVEFIRE_RUNTIME_UID:-1000}}:${{LIVEFIRE_RUNTIME_GID:-1000}}"
            ports:
              - "127.0.0.1:${{LIVEFIRE_TARGET_HOST_PORT:-8088}}:8088"
            volumes:
              - ../artifacts:/artifacts
              - ../chaos/state:/chaos_state
            environment:
              - LIVEFIRE_APP_NAME=LiveFireTTX Target
              - LIVEFIRE_STATE_DIR=/chaos_state
            healthcheck:
              test:
                - CMD
                - python
                - -c
                - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health')"
              interval: 3s
              timeout: 2s
              retries: 15

          livefire-chaos:
            build: ../chaos
            user: "${{LIVEFIRE_RUNTIME_UID:-1000}}:${{LIVEFIRE_RUNTIME_GID:-1000}}"
            depends_on:
              livefire-target:
                condition: service_healthy
            ports:
              - "127.0.0.1:${{LIVEFIRE_CONTROL_HOST_PORT:-8090}}:8090"
            volumes:
              - ../artifacts:/artifacts
              - ../chaos/state:/chaos_state
            environment:
              - LIVEFIRE_EXERCISE_ID={exercise.id}
              - LIVEFIRE_STATE_DIR=/chaos_state
              - LIVEFIRE_ARTIFACTS_DIR=/artifacts
              - LIVEFIRE_TARGET_URL=http://livefire-target:8088
            healthcheck:
              test:
                - CMD
                - python
                - -c
                - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/ready')"
              interval: 5s
              timeout: 2s
              retries: 10
        """
    )
    (root / "target" / "docker-compose.yml").write_text(compose)

    (root / "target" / "app" / "Dockerfile").write_text(
        dedent(
            """
            FROM python:3.12-slim
            WORKDIR /app
            RUN pip install --no-cache-dir fastapi==0.128.8 starlette==0.49.3 uvicorn==0.39.0 pydantic==2.13.4
            COPY target_app.py /app/target_app.py
            CMD ["uvicorn", "target_app:app", "--host", "0.0.0.0", "--port", "8088"]
            """
        )
    )
    target_app = _target_app_source()
    target_app = target_app.replace(
        "__BUSINESS_SYSTEM__",
        repr(exercise.business_system),
    ).replace(
        "__EXERCISE_NAME__",
        repr(exercise.name),
    ).replace(
        "__EXERCISE_ID__",
        repr(exercise.id),
    ).replace(
        "__DEPENDENCY_MAP__",
        repr(SCENARIO_LIBRARY[exercise.scenario_type]["dependencies"]),
    )
    (root / "target" / "app" / "target_app.py").write_text(target_app)

    write_executable(
        root / "target" / "deploy.sh",
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            export LIVEFIRE_RUNTIME_UID="${LIVEFIRE_RUNTIME_UID:-$(id -u)}"
            export LIVEFIRE_RUNTIME_GID="${LIVEFIRE_RUNTIME_GID:-$(id -g)}"
            docker compose up -d --build --wait
            echo "Target: http://127.0.0.1:${LIVEFIRE_TARGET_HOST_PORT:-8088}"
            echo "Guarded chaos API: http://127.0.0.1:${LIVEFIRE_CONTROL_HOST_PORT:-8090}/docs"
            """
        ),
    )
    write_executable(
        root / "target" / "validate.sh",
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            target_port="${LIVEFIRE_TARGET_HOST_PORT:-8088}"
            control_port="${LIVEFIRE_CONTROL_HOST_PORT:-8090}"
            curl --fail --silent "http://127.0.0.1:${target_port}/health"
            echo
            curl --fail --silent "http://127.0.0.1:${control_port}/ready"
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
    default_playbooks = _default_playbooks(exercise, allowed_actions)
    state_dir = root / "chaos" / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            _default_state(default_playbooks),
            indent=2,
            sort_keys=True,
        )
    )
    playbook_dir = root / "chaos" / "playbooks"
    playbook_dir.mkdir(exist_ok=True)
    for playbook_id, playbook in default_playbooks.items():
        (playbook_dir / f"{playbook_id}.yml").write_text(
            yaml.safe_dump(playbook, sort_keys=False)
        )

    replacements = {
        "__ALLOWED_ACTIONS__": repr(allowed_actions),
        "__DEFAULT_PLAYBOOKS__": repr(default_playbooks),
        "__DEPENDENCY_MAP__": repr(
            SCENARIO_LIBRARY[exercise.scenario_type]["dependencies"]
        ),
        "__EXERCISE_ID__": exercise.id,
    }
    engine = _load_template("chaos_engine.py.tmpl", replacements)
    cli = _load_template("chaos_cli.py.tmpl", replacements)
    server = _load_template("chaos_server.py.tmpl", replacements)
    (root / "chaos" / "engine.py").write_text(engine)
    write_executable(root / "chaos" / "chaos_cli.py", cli)
    (root / "chaos" / "server.py").write_text(server)
    (root / "chaos" / "Dockerfile").write_text(
        dedent(
            """
            FROM python:3.12-slim
            WORKDIR /app
            RUN pip install --no-cache-dir fastapi==0.128.8 starlette==0.49.3 uvicorn==0.39.0 pydantic==2.13.4
            COPY engine.py server.py /app/
            CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
            """
        )
    )
    (root / "chaos" / "control.json").write_text(
        json.dumps(
            {
                "version": CONTROL_VERSION,
                "exercise_id": exercise.id,
                "api": "http://127.0.0.1:8090",
            },
            indent=2,
        )
    )

    plan = {
        "exercise_id": exercise.id,
        "control_version": CONTROL_VERSION,
        "safe_only": True,
        "control_api": "http://127.0.0.1:8090",
        "target": "http://127.0.0.1:8088",
        "cli": "python3 chaos_cli.py",
        "intensities": ["low", "medium", "high"],
        "patterns": ["steady", "ramp", "burst", "flap", "jitter"],
        "duration_seconds": {"minimum": 15, "default": 300, "maximum": 3600},
        "playbooks": {
            "directory": "playbooks",
            "default": next(iter(default_playbooks), None),
            "safety_budgets": [
                "max_concurrent_actions",
                "max_severity_points",
                "max_playbook_seconds",
            ],
        },
        "default_stop_conditions": {
            "max_latency_ms": 5000,
            "max_error_rate": 0.5,
            "abort_on_target_unreachable": True,
        },
        "available_actions": [
            {"id": action, **ACTION_CATALOG[action]}
            for action in allowed_actions
        ],
        "dependency_map": SCENARIO_LIBRARY[exercise.scenario_type][
            "dependencies"
        ],
    }
    (root / "chaos" / "chaos-plan.yml").write_text(
        yaml.safe_dump(plan, sort_keys=False)
    )
    (root / "chaos" / "README.md").write_text(
        dedent(
            f"""
            # LiveFireTTX Chaos Orchestration Studio

            This package exposes scenario-scoped chaos actions through a local CLI
            and HTTP API. It supports deterministic fault patterns, YAML playbooks,
            bounded safety budgets, target preflight, live telemetry, and automatic
            rollback.

            ## CLI

            ```bash
            python3 chaos_cli.py preflight
            python3 chaos_cli.py list
            python3 chaos_cli.py run {allowed_actions[0] if allowed_actions else "ACTION_ID"} --intensity medium --pattern ramp --duration 300
            python3 chaos_cli.py state
            python3 chaos_cli.py stop
            ```

            ## API

            Deploy the target package, then open `http://127.0.0.1:8090/docs`.
            The controller monitors active runs every second and aborts them
            when configured latency, error-rate, target-availability, or exercise
            identity guardrails fail.

            Default playbooks are stored in `playbooks/` and can be validated,
            saved, started, paused, resumed, stopped, skipped, and replayed through
            the API or the LiveFireTTX facilitator console.

            `--skip-preflight` exists only for offline package validation. Never use
            it during an exercise.
            """
        )
    )


def _load_template(name: str, replacements: dict[str, str]) -> str:
    content = (TEMPLATE_ROOT / name).read_text()
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    return content


def _default_state(
    playbooks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 5,
        "control_version": CONTROL_VERSION,
        "revision": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "active_actions": {},
        "conditions": dict(DEFAULT_CONDITIONS),
        "runs": [],
        "playbooks": playbooks or {},
        "playbook_runs": [],
        "history": [],
    }


def _default_playbooks(
    exercise: Exercise,
    allowed_actions: list[str],
) -> dict[str, dict[str, Any]]:
    if not allowed_actions:
        return {}
    patterns = {
        "app_degradation": "ramp",
        "auth_failure": "burst",
        "dns_failure": "flap",
        "object_storage_throttle": "jitter",
        "payment_failure": "burst",
        "queue_backlog": "ramp",
        "synthetic_edr_alert": "jitter",
        "telemetry_gap": "flap",
        "third_party_degradation": "burst",
    }
    stages = []
    for index, action in enumerate(allowed_actions):
        stages.append(
            {
                "id": f"wave_{index + 1}_{action}",
                "title": ACTION_CATALOG[action]["label"],
                "action": action,
                "intensity": "medium",
                "pattern": patterns.get(action, "steady"),
                "duration_seconds": 180,
                "start_after_seconds": index * 45,
                "guardrail_profile": "standard",
                "depends_on": [],
            }
        )
    playbook_id = "scenario_cascade"
    playbook: dict[str, Any] = {
        "id": playbook_id,
        "name": f"{exercise.name} Scenario Cascade",
        "description": (
            "A deterministic, overlapping fault sequence generated for this "
            "exercise. Edit timing, patterns, and budgets before facilitation."
        ),
        "seed": 2026 + sum(ord(character) for character in exercise.id),
        "safety": {
            "max_concurrent_actions": min(2, len(stages)),
            "max_severity_points": min(4, len(stages) * 2),
            "max_playbook_seconds": 900,
        },
        "stages": stages,
    }
    return {playbook_id: playbook}


def _target_app_source() -> str:
    return dedent(
        r'''
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        import json
        import os
        import random
        import time

        from fastapi import FastAPI, HTTPException
        from starlette.middleware.trustedhost import TrustedHostMiddleware


        app = FastAPI(title="LiveFireTTX Target")
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                "127.0.0.1",
                "localhost",
                "[::1]",
                "livefire-target",
                "testserver",
            ],
        )
        STATE_PATH = (
            Path(os.environ.get("LIVEFIRE_STATE_DIR", "/chaos_state")) / "state.json"
        )
        APP_NAME = __BUSINESS_SYSTEM__
        EXERCISE_NAME = __EXERCISE_NAME__
        EXERCISE_ID = __EXERCISE_ID__
        DEPENDENCY_MAP = __DEPENDENCY_MAP__
        DEFAULT_CONDITIONS = {
            "latency_ms": 0,
            "error_rate": 0.0,
            "auth_failure_rate": 0.0,
            "dns_failure_rate": 0.0,
            "data_integrity": False,
            "backup_delay": False,
            "build_blocked": False,
            "file_impact": False,
            "object_storage_throttle_rate": 0.0,
            "payment_failure_rate": 0.0,
            "queue_backlog_depth": 0,
            "queue_consumer_delay_ms": 0,
            "stale_read_rate": 0.0,
            "telemetry_delay_seconds": 0,
            "telemetry_gap_rate": 0.0,
            "third_party_error_rate": 0.0,
            "third_party_retry_after_seconds": 0,
        }


        def parse_timestamp(value):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))


        def read_state():
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not STATE_PATH.exists():
                return {
                    "revision": 0,
                    "active_actions": {},
                    "conditions": DEFAULT_CONDITIONS,
                }
            try:
                return json.loads(STATE_PATH.read_text())
            except json.JSONDecodeError:
                return {
                    "revision": 0,
                    "active_actions": {},
                    "conditions": DEFAULT_CONDITIONS,
                }


        def effective_state(state):
            conditions = dict(DEFAULT_CONDITIONS)
            live_actions = {}
            guarded_state = False
            current = datetime.now(timezone.utc)
            for action, active in state.get("active_actions", {}).items():
                effect = active.get("effect")
                if effect is None:
                    continue
                guarded_state = True
                expires_at = active.get("expires_at")
                if expires_at and parse_timestamp(expires_at) <= current:
                    continue
                live_actions[action] = active
                for field, value in effect.items():
                    if isinstance(value, bool):
                        conditions[field] = conditions[field] or value
                    else:
                        conditions[field] = max(conditions[field], value)
            if not guarded_state:
                conditions.update(state.get("conditions", {}))
                live_actions = state.get("active_actions", {})
            return conditions, live_actions


        def conditions():
            return effective_state(read_state())[0]


        def maybe_fail(rate, detail):
            if rate and random.random() < float(rate):
                raise HTTPException(status_code=503, detail=detail)


        @app.get("/")
        def home():
            state = read_state()
            current, active = effective_state(state)
            if current["latency_ms"]:
                time.sleep(float(current["latency_ms"]) / 1000)
            maybe_fail(current["error_rate"], "Synthetic application error")
            return {
                "app": APP_NAME,
                "exercise": EXERCISE_NAME,
                "exercise_id": EXERCISE_ID,
                "status": "degraded" if any(current.values()) else "healthy",
                "state_revision": state.get("revision", 0),
                "active_actions": active,
                "message": "This is a simulated target environment for LiveFireTTX.",
            }


        @app.get("/health")
        def health():
            state = read_state()
            current, active = effective_state(state)
            return {
                "exercise_id": EXERCISE_ID,
                "healthy": not any(current.values()),
                "conditions": current,
                "active_actions": list(active),
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


        @app.get("/dependencies")
        def dependency_map():
            current = conditions()
            condition_fields = {
                "payment": ("payment_failure_rate",),
                "queue": ("queue_backlog_depth", "queue_consumer_delay_ms"),
                "storage": ("object_storage_throttle_rate", "stale_read_rate"),
                "third_party": (
                    "third_party_error_rate",
                    "third_party_retry_after_seconds",
                ),
                "observability": (
                    "telemetry_delay_seconds",
                    "telemetry_gap_rate",
                ),
                "identity": ("auth_failure_rate",),
                "backup": ("backup_delay",),
                "build": ("build_blocked",),
                "database": ("data_integrity",),
            }
            dependencies = []
            for dependency in DEPENDENCY_MAP:
                fields = condition_fields.get(dependency["type"], ())
                degraded = any(current.get(field) for field in fields)
                dependencies.append(
                    {
                        **dependency,
                        "status": "degraded" if degraded else "healthy",
                        "conditions": {
                            field: current.get(field)
                            for field in fields
                        },
                    }
                )
            return {
                "exercise_id": EXERCISE_ID,
                "application": APP_NAME,
                "dependencies": dependencies,
                "simulated": True,
            }


        @app.post("/payments/charge")
        def charge_payment():
            current = conditions()
            maybe_fail(
                current["payment_failure_rate"],
                "Synthetic payment processor decline",
            )
            return {
                "authorized": True,
                "processor": "LiveFire simulated payments",
                "simulated": True,
            }


        @app.get("/queue/status")
        def queue_status():
            current = conditions()
            return {
                "backlog_depth": current["queue_backlog_depth"],
                "consumer_delay_ms": current["queue_consumer_delay_ms"],
                "consumer_status": (
                    "delayed"
                    if current["queue_consumer_delay_ms"]
                    else "current"
                ),
                "simulated": True,
            }


        @app.get("/storage/objects/{object_key}")
        def storage_object(object_key: str):
            current = conditions()
            maybe_fail(
                current["object_storage_throttle_rate"],
                "Synthetic object storage throttle",
            )
            stale = bool(
                current["stale_read_rate"]
                and random.random() < float(current["stale_read_rate"])
            )
            return {
                "key": object_key,
                "version": "previous" if stale else "current",
                "stale": stale,
                "simulated": True,
            }


        @app.get("/dependencies/vendor")
        def vendor_dependency():
            current = conditions()
            maybe_fail(
                current["third_party_error_rate"],
                "Synthetic third-party API failure",
            )
            return {
                "available": True,
                "retry_after_seconds": current[
                    "third_party_retry_after_seconds"
                ],
                "provider": "simulated",
            }


        @app.get("/observability/metrics")
        def observability_metrics():
            current = conditions()
            maybe_fail(
                current["telemetry_gap_rate"],
                "Synthetic telemetry sample unavailable",
            )
            observed_at = datetime.now(timezone.utc) - timedelta(
                seconds=current["telemetry_delay_seconds"]
            )
            return {
                "observed_at": observed_at.isoformat(),
                "delay_seconds": current["telemetry_delay_seconds"],
                "metrics": {
                    "requests_per_minute": 120,
                    "error_rate": current["error_rate"],
                },
                "simulated": True,
            }


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
