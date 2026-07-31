# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import yaml

from app.models import (
    Exercise,
    ExerciseCreate,
    GENERATED_ROOT,
    InjectOption,
    SCENARIO_LIBRARY,
    new_id,
)
from app.services.lab_renderer import (
    render_chaos_environment,
    render_target_environment,
    write_executable,
)


def create_exercise_from_request(
    request: ExerciseCreate,
) -> tuple[Exercise, list[InjectOption]]:
    if request.scenario_type not in SCENARIO_LIBRARY:
        raise ValueError(f"Unknown scenario_type: {request.scenario_type}")

    scenario = SCENARIO_LIBRARY[request.scenario_type]
    exercise_id = new_id("ttx")
    package_path = GENERATED_ROOT / exercise_id
    objectives = request.objectives or scenario["default_objectives"]
    participants = request.participants or [
        "Incident Commander",
        "Security Operations",
        "Cloud/IT Operations",
        "Communications",
        "Business Owner",
    ]

    exercise = Exercise(
        id=exercise_id,
        name=request.name,
        scenario_type=request.scenario_type,
        platform=request.platform,
        business_system=request.business_system,
        difficulty=request.difficulty,
        duration_minutes=request.duration_minutes,
        participants=participants,
        objectives=objectives,
        status="created",
        created_at=datetime.now(timezone.utc).isoformat(),
        package_path=str(package_path),
    )

    injects = build_inject_options(exercise)
    render_exercise_package(exercise, injects)
    return exercise, injects


def build_inject_options(exercise: Exercise) -> list[InjectOption]:
    common = [
        _inject(
            exercise,
            "01-opening",
            "Initial Situation Brief",
            "All Participants",
            (
                f"Initial report: {exercise.business_system} is experiencing abnormal "
                "behavior. The team must establish command, scope impact, and decide "
                "first actions."
            ),
            "narrative",
            {"severity": "medium"},
        ),
        _inject(
            exercise,
            "02-pressure",
            "Executive Status Request",
            "Incident Commander",
            (
                "An executive asks for a concise business-impact estimate, current "
                "confidence level, and next decision point."
            ),
            "narrative",
            {"pressure": "executive"},
        ),
        _inject(
            exercise,
            "03-comms",
            "Customer / Business Escalation",
            "Communications",
            (
                "Customer support reports increasing complaints and asks what can be "
                "said externally."
            ),
            "artifact",
            {"artifact": "customer_complaint.md"},
        ),
    ]

    scenario_injects: dict[str, list[InjectOption]] = {
        "ransomware": [
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Trigger Safe File Impact",
                "IT Operations",
                "Safely renames generated test files and creates a simulated note.",
                "safe_file_impact",
            ),
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Generate Synthetic EDR Alerts",
                "Security Operations",
                "Creates local synthetic alert artifacts representing suspicious behavior.",
                "synthetic_edr_alert",
            ),
            _chaos_inject(
                exercise,
                "03-chaos-options",
                "Simulate Backup Restore Delay",
                "Backup Team",
                "Changes backup status and creates a restore uncertainty artifact.",
                "backup_restore_delay",
            ),
            _inject(
                exercise,
                "04-decision",
                "Legal Notification Question",
                "Legal / Comms",
                (
                    "A regulator notification threshold question is raised based on "
                    "incomplete evidence."
                ),
                "narrative",
                {"decision": "notify_or_wait"},
            ),
        ],
        "cloud_outage": [
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Degrade Application",
                "Cloud Operations",
                "Adds controlled latency and intermittent errors to the mock application.",
                "app_degradation",
            ),
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Create Synthetic DNS Failure",
                "Network / Platform",
                "Makes the simulated DNS dependency fail at a controlled rate.",
                "dns_failure",
            ),
            _inject(
                exercise,
                "03-decision",
                "Failover Decision Point",
                "Incident Commander",
                "Business asks whether to fail over or continue degraded operations.",
                "narrative",
                {"decision": "failover"},
            ),
        ],
        "supply_chain": [
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Generate Dependency Alert",
                "AppSec / Engineering",
                "Blocks the simulated build and creates a dependency advisory artifact.",
                "dependency_alert",
            ),
            _inject(
                exercise,
                "03-decision",
                "Rollback Decision",
                "Engineering Lead",
                (
                    "The team must decide whether to halt deploys, roll back, or accept "
                    "risk temporarily."
                ),
                "narrative",
                {"decision": "rollback"},
            ),
        ],
        "database_corruption": [
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Corrupt Test Records",
                "Database Team",
                "Changes non-sensitive seeded records returned by the local lab.",
                "data_corruption",
            ),
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Simulate Restore Delay",
                "Backup Team",
                "Changes backup status and creates an RPO uncertainty artifact.",
                "backup_restore_delay",
            ),
            _inject(
                exercise,
                "03-decision",
                "Data Integrity Statement",
                "Business Owner",
                "Business asks whether data can be trusted for customer-facing operations.",
                "narrative",
                {"decision": "data_integrity"},
            ),
        ],
        "identity_outage": [
            _chaos_inject(
                exercise,
                "02-chaos-options",
                "Simulate Auth Failure",
                "Identity Team",
                "Makes the mock login endpoint fail at a controlled rate.",
                "auth_failure",
            ),
            _inject(
                exercise,
                "03-decision",
                "Break-Glass Access Decision",
                "Incident Commander",
                "An executive needs emergency access while SSO is failing.",
                "narrative",
                {"decision": "break_glass"},
            ),
        ],
    }
    return common + scenario_injects[exercise.scenario_type]


def _inject(
    exercise: Exercise,
    stage: str,
    title: str,
    audience: str,
    description: str,
    action_type: str,
    payload: dict[str, object],
    script_name: str | None = None,
) -> InjectOption:
    return InjectOption(
        id=new_id("inj"),
        exercise_id=exercise.id,
        stage=stage,
        title=title,
        audience=audience,
        description=description,
        action_type=action_type,
        script_name=script_name,
        payload=payload,
    )


def _chaos_inject(
    exercise: Exercise,
    stage: str,
    title: str,
    audience: str,
    description: str,
    action: str,
) -> InjectOption:
    return _inject(
        exercise,
        stage,
        title,
        audience,
        description,
        "chaos_script",
        {
            "safe": True,
            "action": action,
            "control_version": "0.4.0",
            "intensities": ["low", "medium", "high"],
            "default_intensity": "medium",
            "patterns": ["steady", "ramp", "burst", "flap", "jitter"],
            "default_pattern": "steady",
            "durations": [60, 300, 600, 900],
            "default_duration": 300,
            "guardrail_profiles": {
                "strict": {
                    "max_latency_ms": 2500,
                    "max_error_rate": 0.25,
                    "abort_on_target_unreachable": True,
                },
                "standard": {
                    "max_latency_ms": 5000,
                    "max_error_rate": 0.5,
                    "abort_on_target_unreachable": True,
                },
                "observe": {
                    "max_latency_ms": 10000,
                    "max_error_rate": 1.0,
                    "abort_on_target_unreachable": False,
                },
            },
            "default_guardrail_profile": "standard",
        },
        "chaos_cli.py",
    )


def render_exercise_package(
    exercise: Exercise,
    injects: list[InjectOption],
) -> None:
    root = Path(exercise.package_path)
    for directory in ["target/app", "chaos", "artifacts", "cleanup", "reports"]:
        (root / directory).mkdir(parents=True, exist_ok=True)

    scenario = SCENARIO_LIBRARY[exercise.scenario_type]
    exercise_yml = {
        "exercise": {
            "id": exercise.id,
            "name": exercise.name,
            "scenario_type": exercise.scenario_type,
            "business_system": exercise.business_system,
            "platform": exercise.platform,
            "difficulty": exercise.difficulty,
            "duration_minutes": exercise.duration_minutes,
            "participants": exercise.participants,
            "objectives": exercise.objectives,
            "target_modules": scenario["target_modules"],
            "chaos_modules": scenario["chaos_modules"],
        },
        "inject_options": [inject.__dict__ for inject in injects],
    }
    (root / "exercise.yml").write_text(
        yaml.safe_dump(exercise_yml, sort_keys=False)
    )

    (root / "facilitator_guide.md").write_text(
        dedent(
            f"""
            # Facilitator Guide: {exercise.name}

            ## Scenario
            {scenario['description']}

            ## Business System
            {exercise.business_system}

            ## Objectives
            {chr(10).join('- ' + objective for objective in exercise.objectives)}

            ## Participants
            {chr(10).join('- ' + participant for participant in exercise.participants)}

            ## Facilitator Notes
            Use the LiveFireTTX console to trigger narrative injects and safe chaos
            actions. Chaos runs support low, medium, and high intensity, bounded
            durations, deterministic fault patterns, target preflight checks,
            automatic rollback, and configurable stop conditions.

            The generated control API is available at `http://127.0.0.1:8090/docs`
            after deploying the target environment. The facilitator console can edit
            playbooks visually or through YAML, validate and preview schedules,
            manage template versions, create watermarked safe artifacts, pause future
            stage scheduling, skip stages, replay a run with the same seed, and
            monitor safety budgets. Use the emergency stop whenever observed impact
            exceeds the exercise plan.
            """
        )
    )
    (root / "participant_brief.md").write_text(
        dedent(
            f"""
            # Participant Brief

            You are participating in a live-fire tabletop exercise for
            **{exercise.business_system}**.

            Treat all injects as realistic but simulated. Do not attempt unauthorized
            actions against real systems. Record decisions, assumptions, and open
            questions.
            """
        )
    )
    (root / "artifacts" / "customer_complaint.md").write_text(
        dedent(
            """
            # Customer Complaint

            Customers report intermittent errors and are asking whether their data or
            orders are affected.
            """
        )
    )

    render_target_environment(root, exercise)
    render_chaos_environment(root, exercise, injects)
    _render_cleanup(root)
    _render_report(root, exercise)


def _render_cleanup(root: Path) -> None:
    write_executable(
        root / "cleanup" / "destroy.sh",
        dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            cd ../target
            docker compose down -v || true
            echo 'LiveFireTTX target and chaos controller destroyed.'
            """
        ),
    )


def _render_report(root: Path, exercise: Exercise) -> None:
    (root / "reports" / "after_action_template.md").write_text(
        dedent(
            f"""
            # After Action Report: {exercise.name}

            ## Exercise Metadata
            - Exercise ID: {exercise.id}
            - Scenario Type: {exercise.scenario_type}
            - Business System: {exercise.business_system}
            - Duration: {exercise.duration_minutes} minutes

            ## Objectives Tested
            {chr(10).join('- ' + objective for objective in exercise.objectives)}

            ## Timeline
            _Download the generated Markdown report or evidence package from the
            facilitator console to populate this section automatically._

            ## Chaos Actions Applied
            _The evidence export includes action, intensity, pattern, peak observed
            impact, lifecycle status, and reset reason._

            ## What Went Well

            ## Gaps Observed

            ## Decisions and Assumptions

            ## RTO/RPO Notes

            ## Communications Notes

            ## Remediation Items

            ## Retest Plan
            """
        )
    )
