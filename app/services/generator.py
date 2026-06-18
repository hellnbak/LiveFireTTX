# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent
import json
import os
import stat
import yaml

from app.models import (
    Exercise,
    ExerciseCreate,
    InjectOption,
    GENERATED_ROOT,
    SCENARIO_LIBRARY,
    new_id,
)


def create_exercise_from_request(req: ExerciseCreate) -> tuple[Exercise, list[InjectOption]]:
    if req.scenario_type not in SCENARIO_LIBRARY:
        raise ValueError(f"Unknown scenario_type: {req.scenario_type}")

    scenario = SCENARIO_LIBRARY[req.scenario_type]
    exercise_id = new_id("ttx")
    package_path = GENERATED_ROOT / exercise_id
    objectives = req.objectives or scenario["default_objectives"]
    participants = req.participants or ["Incident Commander", "Security Operations", "Cloud/IT Operations", "Communications", "Business Owner"]

    ex = Exercise(
        id=exercise_id,
        name=req.name,
        scenario_type=req.scenario_type,
        platform=req.platform,
        business_system=req.business_system,
        difficulty=req.difficulty,
        duration_minutes=req.duration_minutes,
        participants=participants,
        objectives=objectives,
        status="created",
        created_at=datetime.utcnow().isoformat() + "Z",
        package_path=str(package_path),
    )

    injects = build_inject_options(ex)
    render_exercise_package(ex, injects)
    return ex, injects


def build_inject_options(ex: Exercise) -> list[InjectOption]:
    base = SCENARIO_LIBRARY[ex.scenario_type]
    common = [
        InjectOption(new_id("inj"), ex.id, "01-opening", "Initial Situation Brief", "All Participants", f"Initial report: {ex.business_system} is experiencing abnormal behavior. The team must establish command, scope impact, and decide first actions.", "narrative", None, {"severity": "medium"}),
        InjectOption(new_id("inj"), ex.id, "02-pressure", "Executive Status Request", "Incident Commander", "An executive asks for a concise business-impact estimate, current confidence level, and next decision point.", "narrative", None, {"pressure": "executive"}),
        InjectOption(new_id("inj"), ex.id, "03-comms", "Customer / Business Escalation", "Communications", "Customer support reports increasing complaints and asks what can be said externally.", "artifact", None, {"artifact": "customer_complaint.md"}),
    ]

    specific: list[InjectOption] = []
    if ex.scenario_type == "ransomware":
        specific = [
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Trigger Safe File Impact", "IT Operations", "Safely renames test files in the generated lab and creates a fake ransom note.", "chaos_script", "safe_file_rename.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Generate Synthetic EDR Alerts", "Security Operations", "Creates local synthetic alert artifacts representing suspicious behavior.", "chaos_script", "generate_synthetic_alerts.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "03-chaos-options", "Simulate Backup Restore Delay", "Backup Team", "Creates a backup status artifact indicating uncertainty about restore freshness and timing.", "chaos_script", "simulate_backup_delay.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "04-decision", "Legal Notification Question", "Legal / Comms", "A regulator notification threshold question is raised based on incomplete evidence.", "narrative", None, {"decision": "notify_or_wait"}),
        ]
    elif ex.scenario_type == "cloud_outage":
        specific = [
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Degrade Application", "Cloud Operations", "Introduces controlled delay into the mock app status endpoint.", "chaos_script", "degrade_app.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Create Synthetic DNS Failure", "Network / Platform", "Creates a DNS failure artifact and updates the lab status page.", "chaos_script", "simulate_dns_failure.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "03-decision", "Failover Decision Point", "Incident Commander", "Business asks whether to fail over or continue degraded operations.", "narrative", None, {"decision": "failover"}),
        ]
    elif ex.scenario_type == "supply_chain":
        specific = [
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Generate Dependency Alert", "AppSec / Engineering", "Creates a fake dependency compromise advisory and failed build artifact.", "chaos_script", "dependency_alert.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "03-decision", "Rollback Decision", "Engineering Lead", "The team must decide whether to halt deploys, roll back, or accept risk temporarily.", "narrative", None, {"decision": "rollback"}),
        ]
    elif ex.scenario_type == "database_corruption":
        specific = [
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Corrupt Test Records", "Database Team", "Changes non-sensitive seeded records in the local lab to simulate integrity issues.", "chaos_script", "corrupt_test_records.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Simulate Restore Delay", "Backup Team", "Creates restore-delay and RPO uncertainty artifacts.", "chaos_script", "simulate_backup_delay.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "03-decision", "Data Integrity Statement", "Business Owner", "Business asks whether data can be trusted for customer-facing operations.", "narrative", None, {"decision": "data_integrity"}),
        ]
    elif ex.scenario_type == "identity_outage":
        specific = [
            InjectOption(new_id("inj"), ex.id, "02-chaos-options", "Simulate Auth Failure", "Identity Team", "Creates synthetic authentication failure logs and updates app status.", "chaos_script", "simulate_auth_failure.py", {"safe": True}),
            InjectOption(new_id("inj"), ex.id, "03-decision", "Break-Glass Access Decision", "Incident Commander", "An executive needs emergency access while SSO is failing.", "narrative", None, {"decision": "break_glass"}),
        ]
    return common + specific


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_exercise_package(ex: Exercise, injects: list[InjectOption]) -> None:
    root = Path(ex.package_path)
    for d in ["target/app", "chaos", "artifacts", "cleanup", "reports"]:
        (root / d).mkdir(parents=True, exist_ok=True)

    scenario = SCENARIO_LIBRARY[ex.scenario_type]
    exercise_yml = {
        "exercise": {
            "id": ex.id,
            "name": ex.name,
            "scenario_type": ex.scenario_type,
            "business_system": ex.business_system,
            "platform": ex.platform,
            "difficulty": ex.difficulty,
            "duration_minutes": ex.duration_minutes,
            "participants": ex.participants,
            "objectives": ex.objectives,
            "target_modules": scenario["target_modules"],
            "chaos_modules": scenario["chaos_modules"],
        },
        "inject_options": [i.__dict__ for i in injects],
    }
    (root / "exercise.yml").write_text(yaml.safe_dump(exercise_yml, sort_keys=False))

    (root / "facilitator_guide.md").write_text(dedent(f"""
    # Facilitator Guide: {ex.name}

    ## Scenario
    {scenario['description']}

    ## Business System
    {ex.business_system}

    ## Objectives
    {chr(10).join('- ' + o for o in ex.objectives)}

    ## Participants
    {chr(10).join('- ' + p for p in ex.participants)}

    ## Facilitator Notes
    Use the LiveFireTTX console to manually trigger injects. Multiple inject options may exist for each stage, allowing the exercise leader to steer difficulty and pacing.
    """))

    (root / "participant_brief.md").write_text(dedent(f"""
    # Participant Brief

    You are participating in a live-fire tabletop exercise for **{ex.business_system}**.

    Treat all injects as realistic but simulated. Do not attempt unauthorized actions against real systems. Record decisions, assumptions, and open questions.
    """))

    (root / "artifacts" / "customer_complaint.md").write_text("# Customer Complaint\n\nCustomers report intermittent errors and are asking whether their data or orders are affected.\n")

    render_target(root, ex)
    render_chaos(root, ex)
    render_cleanup(root, ex)
    render_report(root, ex)


def render_target(root: Path, ex: Exercise) -> None:
    compose = dedent("""
    services:
      livefire-target:
        build: ./app
        ports:
          - "8088:8088"
        volumes:
          - ../artifacts:/artifacts
          - ../chaos/state:/chaos_state
        environment:
          - LIVEFIRE_APP_NAME=LiveFireTTX Target
    """)
    (root / "target" / "docker-compose.yml").write_text(compose)

    dockerfile = dedent("""
    FROM python:3.12-slim
    WORKDIR /app
    COPY target_app.py /app/target_app.py
    RUN pip install fastapi uvicorn
    CMD ["uvicorn", "target_app:app", "--host", "0.0.0.0", "--port", "8088"]
    """)
    (root / "target" / "app" / "Dockerfile").write_text(dockerfile)

    target_app = dedent(f'''
    from fastapi import FastAPI
    from pathlib import Path
    import json
    import time

    app = FastAPI(title="LiveFireTTX Target")
    STATE_DIR = Path("/chaos_state")
    ARTIFACTS = Path("/artifacts")

    def state():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = STATE_DIR / "state.json"
        if not p.exists():
            p.write_text(json.dumps({{"degraded": False, "auth_failure": False, "dns_failure": False}}))
        return json.loads(p.read_text())

    @app.get("/")
    def home():
        s = state()
        if s.get("degraded"):
            time.sleep(1.5)
        return {{
            "app": "{ex.business_system}",
            "exercise": "{ex.name}",
            "status": "degraded" if any(s.values()) else "healthy",
            "chaos_state": s,
            "message": "This is a simulated target environment for LiveFireTTX."
        }}

    @app.get("/health")
    def health():
        s = state()
        return {{"healthy": not any(s.values()), "state": s}}

    @app.get("/orders")
    def orders():
        return [
            {{"order_id": "ORD-1001", "status": "processing", "amount": 123.45}},
            {{"order_id": "ORD-1002", "status": "paid", "amount": 88.10}},
            {{"order_id": "ORD-1003", "status": "pending_review", "amount": 451.19}},
        ]
    ''')
    (root / "target" / "app" / "target_app.py").write_text(target_app)

    write_executable(root / "target" / "deploy.sh", "#!/usr/bin/env bash\nset -euo pipefail\ndocker compose up -d --build\necho 'LiveFireTTX target running at http://127.0.0.1:8088'\n")
    write_executable(root / "target" / "validate.sh", "#!/usr/bin/env bash\nset -euo pipefail\ncurl -s http://127.0.0.1:8088/health || true\n")


def render_chaos(root: Path, ex: Exercise) -> None:
    state_dir = root / "chaos" / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps({"degraded": False, "auth_failure": False, "dns_failure": False}, indent=2))

    common = """
from pathlib import Path
import json
from datetime import datetime

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'state.json'
ARTIFACTS = ROOT.parent / 'artifacts'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
STATE.parent.mkdir(parents=True, exist_ok=True)

def read_state():
    if not STATE.exists():
        STATE.write_text(json.dumps({'degraded': False, 'auth_failure': False, 'dns_failure': False}, indent=2))
    return json.loads(STATE.read_text())

def write_state(s):
    STATE.write_text(json.dumps(s, indent=2))

def stamp():
    return datetime.utcnow().isoformat() + 'Z'
"""
    scripts = {
        "generate_synthetic_alerts.py": common + """
alert = {
    'time': stamp(),
    'source': 'LiveFireTTX synthetic EDR',
    'severity': 'high',
    'title': 'Suspicious process behavior detected',
    'detail': 'Synthetic alert only. No malware or exploit code was executed.'
}
(ARTIFACTS / 'synthetic_edr_alert.json').write_text(json.dumps(alert, indent=2))
print('Created artifacts/synthetic_edr_alert.json')
""",
        "safe_file_rename.py": common + """
lab = ARTIFACTS / 'safe_file_impact_lab'
lab.mkdir(exist_ok=True)
for i in range(1, 6):
    original = lab / f'test_file_{i}.txt'
    original.write_text('This is harmless test data for LiveFireTTX.\n')
for p in list(lab.glob('*.txt')):
    p.rename(p.with_suffix(p.suffix + '.locked'))
(ARTIFACTS / 'RANSOM_NOTE_SIMULATED.txt').write_text('SIMULATED EXERCISE ARTIFACT ONLY. No encryption occurred.\n')
print('Created safe file-impact simulation artifacts.')
""",
        "simulate_backup_delay.py": common + """
(ARTIFACTS / 'backup_status_report.md').write_text('# Backup Status\n\nLast known good backup is uncertain. Restore test is delayed. This is a simulated inject.\n')
print('Created artifacts/backup_status_report.md')
""",
        "degrade_app.py": common + """
s = read_state()
s['degraded'] = True
write_state(s)
(ARTIFACTS / 'app_degradation.md').write_text('# App Degradation\n\nThe target application is now reporting degraded performance.\n')
print('Target app state set to degraded.')
""",
        "simulate_dns_failure.py": common + """
s = read_state()
s['dns_failure'] = True
write_state(s)
(ARTIFACTS / 'dns_failure.md').write_text('# DNS Failure\n\nSynthetic DNS/provider failure inject.\n')
print('DNS failure state set.')
""",
        "dependency_alert.py": common + """
(ARTIFACTS / 'dependency_advisory.md').write_text('# Dependency Advisory\n\nA simulated vendor advisory reports a potentially compromised dependency.\n')
(ARTIFACTS / 'failed_build.log').write_text('BUILD FAILED: dependency integrity check failed. Synthetic exercise artifact.\n')
print('Created dependency advisory and failed build artifacts.')
""",
        "corrupt_test_records.py": common + """
(ARTIFACTS / 'data_integrity_alert.md').write_text('# Data Integrity Alert\n\nSeeded test order records no longer reconcile with payment totals. Synthetic exercise artifact.\n')
print('Created data integrity alert artifact.')
""",
        "simulate_auth_failure.py": common + """
s = read_state()
s['auth_failure'] = True
write_state(s)
(ARTIFACTS / 'auth_failure.log').write_text('Multiple SSO login failures detected. Synthetic exercise artifact.\n')
print('Auth failure state set.')
""",
        "reset_chaos.py": common + """
write_state({'degraded': False, 'auth_failure': False, 'dns_failure': False})
print('Chaos state reset.')
""",
    }
    for name, content in scripts.items():
        write_executable(root / "chaos" / name, content)

    (root / "chaos" / "chaos-plan.yml").write_text(yaml.safe_dump({"exercise_id": ex.id, "safe_only": True, "available_scripts": list(scripts.keys())}, sort_keys=False))


def render_cleanup(root: Path, ex: Exercise) -> None:
    write_executable(root / "cleanup" / "destroy.sh", "#!/usr/bin/env bash\nset -euo pipefail\ncd ../target\ndocker compose down -v || true\necho 'LiveFireTTX target environment destroyed.'\n")


def render_report(root: Path, ex: Exercise) -> None:
    (root / "reports" / "after_action_template.md").write_text(dedent(f"""
    # After Action Report: {ex.name}

    ## Exercise Metadata
    - Exercise ID: {ex.id}
    - Scenario Type: {ex.scenario_type}
    - Business System: {ex.business_system}
    - Duration: {ex.duration_minutes} minutes

    ## Objectives Tested
    {chr(10).join('- ' + o for o in ex.objectives)}

    ## Timeline
    _Export facilitator console events and paste here._

    ## What Went Well

    ## Gaps Observed

    ## Decisions and Assumptions

    ## RTO/RPO Notes

    ## Communications Notes

    ## Remediation Items

    ## Retest Plan
    """))
