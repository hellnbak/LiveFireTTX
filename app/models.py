# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import sqlite3
import uuid

DB_PATH = Path(__file__).resolve().parent.parent / "livefirettx.db"
GENERATED_ROOT = Path(__file__).resolve().parent.parent / "generated" / "exercises"


SCENARIO_LIBRARY: Dict[str, Dict[str, Any]] = {
    "ransomware": {
        "label": "Ransomware / Business Interruption",
        "description": "A ransomware-like event impacts a business application and file storage.",
        "target_modules": ["mock_business_app", "postgres", "file_storage", "backup_snapshot", "synthetic_logging"],
        "chaos_modules": ["safe_file_rename", "fake_ransom_note", "synthetic_edr_alert", "backup_restore_delay", "app_degradation"],
        "default_objectives": ["detect suspicious behavior", "declare incident severity", "contain affected service", "validate backups", "coordinate legal/comms"],
    },
    "cloud_outage": {
        "label": "Cloud / Regional Service Outage",
        "description": "A cloud dependency or regional component becomes unstable.",
        "target_modules": ["mock_business_app", "postgres", "cache", "health_checks", "synthetic_logging"],
        "chaos_modules": ["app_degradation", "database_latency", "dns_failure", "customer_complaints"],
        "default_objectives": ["assess business impact", "test failover decision", "validate monitoring", "communicate outage status"],
    },
    "supply_chain": {
        "label": "Supply Chain / Dependency Compromise",
        "description": "A suspicious dependency alert creates uncertainty around the build pipeline.",
        "target_modules": ["mock_repo", "dependency_manifest", "ci_cd_simulator", "mock_business_app", "synthetic_logging"],
        "chaos_modules": ["dependency_alert", "failed_build", "suspicious_outbound_log", "vendor_advisory"],
        "default_objectives": ["triage dependency risk", "decide rollback", "coordinate vendor notification", "protect build pipeline"],
    },
    "database_corruption": {
        "label": "Database Corruption / Restore Failure",
        "description": "Application data becomes inconsistent and restore status is uncertain.",
        "target_modules": ["mock_business_app", "postgres", "backup_snapshot", "synthetic_logging"],
        "chaos_modules": ["corrupt_test_records", "backup_restore_delay", "replica_lag", "customer_complaints"],
        "default_objectives": ["measure RTO/RPO", "validate restore process", "communicate data integrity risk"],
    },
    "identity_outage": {
        "label": "Identity Provider Outage",
        "description": "SSO/authentication failures affect access to business-critical systems.",
        "target_modules": ["mock_business_app", "mock_sso", "break_glass_account", "synthetic_logging"],
        "chaos_modules": ["auth_failure", "executive_access_issue", "break_glass_prompt", "customer_complaints"],
        "default_objectives": ["validate break-glass access", "triage SaaS dependency", "communicate access impact"],
    },
}


@dataclass
class ExerciseCreate:
    name: str
    scenario_type: str
    platform: str = "local_docker"
    business_system: str = "Order Processing"
    difficulty: str = "intermediate"
    duration_minutes: int = 90
    participants: List[str] = field(default_factory=list)
    objectives: List[str] = field(default_factory=list)


@dataclass
class Exercise:
    id: str
    name: str
    scenario_type: str
    platform: str
    business_system: str
    difficulty: str
    duration_minutes: int
    participants: List[str]
    objectives: List[str]
    status: str
    created_at: str
    package_path: str


@dataclass
class InjectOption:
    id: str
    exercise_id: str
    stage: str
    title: str
    audience: str
    description: str
    action_type: str
    script_name: Optional[str]
    payload: Dict[str, Any]
    triggered: bool = False
    triggered_at: Optional[str] = None


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scenario_type TEXT NOT NULL,
                platform TEXT NOT NULL,
                business_system TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                participants TEXT NOT NULL,
                objectives TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                package_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inject_options (
                id TEXT PRIMARY KEY,
                exercise_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                title TEXT NOT NULL,
                audience TEXT NOT NULL,
                description TEXT NOT NULL,
                action_type TEXT NOT NULL,
                script_name TEXT,
                payload TEXT NOT NULL,
                triggered INTEGER NOT NULL DEFAULT 0,
                triggered_at TEXT,
                FOREIGN KEY(exercise_id) REFERENCES exercises(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_events (
                id TEXT PRIMARY KEY,
                exercise_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(exercise_id) REFERENCES exercises(id)
            )
            """
        )
        conn.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def row_to_exercise(row: sqlite3.Row) -> Exercise:
    return Exercise(
        id=row["id"],
        name=row["name"],
        scenario_type=row["scenario_type"],
        platform=row["platform"],
        business_system=row["business_system"],
        difficulty=row["difficulty"],
        duration_minutes=row["duration_minutes"],
        participants=json.loads(row["participants"]),
        objectives=json.loads(row["objectives"]),
        status=row["status"],
        created_at=row["created_at"],
        package_path=row["package_path"],
    )


def row_to_inject(row: sqlite3.Row) -> InjectOption:
    return InjectOption(
        id=row["id"],
        exercise_id=row["exercise_id"],
        stage=row["stage"],
        title=row["title"],
        audience=row["audience"],
        description=row["description"],
        action_type=row["action_type"],
        script_name=row["script_name"],
        payload=json.loads(row["payload"]),
        triggered=bool(row["triggered"]),
        triggered_at=row["triggered_at"],
    )


def save_exercise(ex: Exercise) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO exercises VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ex.id,
                ex.name,
                ex.scenario_type,
                ex.platform,
                ex.business_system,
                ex.difficulty,
                ex.duration_minutes,
                json.dumps(ex.participants),
                json.dumps(ex.objectives),
                ex.status,
                ex.created_at,
                ex.package_path,
            ),
        )
        conn.commit()


def save_injects(injects: List[InjectOption]) -> None:
    with connect() as conn:
        for inj in injects:
            conn.execute(
                """
                INSERT INTO inject_options VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inj.id,
                    inj.exercise_id,
                    inj.stage,
                    inj.title,
                    inj.audience,
                    inj.description,
                    inj.action_type,
                    inj.script_name,
                    json.dumps(inj.payload),
                    1 if inj.triggered else 0,
                    inj.triggered_at,
                ),
            )
        conn.commit()


def list_exercises() -> List[Exercise]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM exercises ORDER BY created_at DESC").fetchall()
    return [row_to_exercise(r) for r in rows]


def get_exercise(exercise_id: str) -> Optional[Exercise]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return row_to_exercise(row) if row else None


def get_injects(exercise_id: str) -> List[InjectOption]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM inject_options WHERE exercise_id = ? ORDER BY stage, title", (exercise_id,)).fetchall()
    return [row_to_inject(r) for r in rows]


def get_inject(inject_id: str) -> Optional[InjectOption]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM inject_options WHERE id = ?", (inject_id,)).fetchone()
    return row_to_inject(row) if row else None


def mark_inject_triggered(inject_id: str) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    with connect() as conn:
        conn.execute("UPDATE inject_options SET triggered = 1, triggered_at = ? WHERE id = ?", (now, inject_id))
        conn.commit()


def add_event(exercise_id: str, event_type: str, title: str, detail: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?)",
            (new_id("evt"), exercise_id, event_type, title, detail, datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()


def list_events(exercise_id: str) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM run_events WHERE exercise_id = ? ORDER BY created_at DESC", (exercise_id,)).fetchall()
