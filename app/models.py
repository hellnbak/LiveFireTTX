# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import sqlite3
import uuid

from app.config import settings


DB_PATH = settings.database_path
GENERATED_ROOT = settings.generated_root
SCHEMA_VERSION = 3


SCENARIO_LIBRARY: Dict[str, Dict[str, Any]] = {
    "ransomware": {
        "label": "Ransomware / Business Interruption",
        "description": "A ransomware-like event impacts a business application and file storage.",
        "default_business_system": "Order Processing",
        "default_duration_minutes": 120,
        "default_difficulty": "advanced",
        "target_modules": ["mock_business_app", "postgres", "file_storage", "backup_snapshot", "synthetic_logging"],
        "chaos_modules": ["safe_file_impact", "synthetic_edr_alert", "backup_restore_delay"],
        "default_objectives": ["detect suspicious behavior", "declare incident severity", "contain affected service", "validate backups", "coordinate legal/comms"],
        "recommended_roles": [
            "Incident Commander",
            "Security Operations",
            "IT Operations",
            "Backup Team",
            "Communications",
            "Business Owner",
        ],
        "dependencies": [
            {"id": "identity", "label": "Identity Provider", "type": "identity"},
            {"id": "database", "label": "Order Database", "type": "database"},
            {"id": "storage", "label": "File Storage", "type": "storage"},
            {"id": "backup", "label": "Backup Service", "type": "backup"},
        ],
    },
    "cloud_outage": {
        "label": "Cloud / Regional Service Outage",
        "description": "A cloud dependency or regional component becomes unstable.",
        "default_business_system": "Customer API",
        "default_duration_minutes": 90,
        "default_difficulty": "intermediate",
        "target_modules": ["mock_business_app", "postgres", "cache", "queue", "object_storage", "payment_processor", "third_party_api", "health_checks", "synthetic_logging"],
        "chaos_modules": ["app_degradation", "dns_failure", "payment_failure", "queue_backlog", "object_storage_throttle", "third_party_degradation", "telemetry_gap"],
        "default_objectives": ["assess business impact", "test failover decision", "validate monitoring", "communicate outage status"],
        "recommended_roles": [
            "Incident Commander",
            "Cloud Operations",
            "Application Engineering",
            "SRE / Observability",
            "Communications",
            "Business Owner",
        ],
        "dependencies": [
            {"id": "database", "label": "Order Database", "type": "database"},
            {"id": "queue", "label": "Order Queue", "type": "queue"},
            {"id": "storage", "label": "Object Storage", "type": "storage"},
            {"id": "payments", "label": "Payment Processor", "type": "payment"},
            {"id": "vendor", "label": "Shipping API", "type": "third_party"},
            {"id": "telemetry", "label": "Telemetry Pipeline", "type": "observability"},
        ],
    },
    "supply_chain": {
        "label": "Supply Chain / Dependency Compromise",
        "description": "A suspicious dependency alert creates uncertainty around the build pipeline.",
        "default_business_system": "Software Delivery",
        "default_duration_minutes": 90,
        "default_difficulty": "advanced",
        "target_modules": ["mock_repo", "dependency_manifest", "ci_cd_simulator", "mock_business_app", "third_party_api", "synthetic_logging"],
        "chaos_modules": ["dependency_alert", "third_party_degradation", "telemetry_gap"],
        "default_objectives": ["triage dependency risk", "decide rollback", "coordinate vendor notification", "protect build pipeline"],
        "recommended_roles": [
            "Incident Commander",
            "Application Security",
            "Engineering Lead",
            "Platform Engineering",
            "Vendor Management",
            "Communications",
        ],
        "dependencies": [
            {"id": "repository", "label": "Source Repository", "type": "source"},
            {"id": "build", "label": "Build Pipeline", "type": "build"},
            {"id": "vendor", "label": "Package Registry", "type": "third_party"},
            {"id": "telemetry", "label": "Security Telemetry", "type": "observability"},
        ],
    },
    "database_corruption": {
        "label": "Database Corruption / Restore Failure",
        "description": "Application data becomes inconsistent and restore status is uncertain.",
        "default_business_system": "Order Processing",
        "default_duration_minutes": 90,
        "default_difficulty": "advanced",
        "target_modules": ["mock_business_app", "postgres", "queue", "object_storage", "backup_snapshot", "synthetic_logging"],
        "chaos_modules": ["data_corruption", "backup_restore_delay", "queue_backlog", "object_storage_throttle"],
        "default_objectives": ["measure RTO/RPO", "validate restore process", "communicate data integrity risk"],
        "recommended_roles": [
            "Incident Commander",
            "Database Team",
            "Application Engineering",
            "Backup Team",
            "Business Owner",
            "Communications",
        ],
        "dependencies": [
            {"id": "database", "label": "Primary Database", "type": "database"},
            {"id": "queue", "label": "Write Queue", "type": "queue"},
            {"id": "storage", "label": "Object Storage", "type": "storage"},
            {"id": "backup", "label": "Backup Service", "type": "backup"},
        ],
    },
    "identity_outage": {
        "label": "Identity Provider Outage",
        "description": "SSO/authentication failures affect access to business-critical systems.",
        "default_business_system": "Workforce Access",
        "default_duration_minutes": 75,
        "default_difficulty": "intermediate",
        "target_modules": ["mock_business_app", "mock_sso", "break_glass_account", "third_party_api", "synthetic_logging"],
        "chaos_modules": ["auth_failure", "third_party_degradation", "telemetry_gap"],
        "default_objectives": ["validate break-glass access", "triage SaaS dependency", "communicate access impact"],
        "recommended_roles": [
            "Incident Commander",
            "Identity Team",
            "Security Operations",
            "Service Desk",
            "Application Owner",
            "Communications",
        ],
        "dependencies": [
            {"id": "identity", "label": "Identity Provider", "type": "identity"},
            {"id": "vendor", "label": "SaaS Control Plane", "type": "third_party"},
            {"id": "telemetry", "label": "Identity Telemetry", "type": "observability"},
        ],
    },
    "dependency_cascade": {
        "label": "Critical Dependency Cascade",
        "description": "Payment, queue, storage, vendor API, and telemetry dependencies degrade in a controlled cascade.",
        "default_business_system": "Digital Commerce",
        "default_duration_minutes": 120,
        "default_difficulty": "advanced",
        "target_modules": ["mock_business_app", "payment_processor", "queue", "object_storage", "third_party_api", "synthetic_logging"],
        "chaos_modules": ["payment_failure", "queue_backlog", "object_storage_throttle", "third_party_degradation", "telemetry_gap"],
        "default_objectives": ["map dependency impact", "prioritize degraded services", "manage retry pressure", "communicate uncertainty", "validate recovery order"],
        "recommended_roles": [
            "Incident Commander",
            "Application Engineering",
            "Platform Engineering",
            "SRE / Observability",
            "Vendor Management",
            "Business Owner",
            "Communications",
        ],
        "dependencies": [
            {"id": "payments", "label": "Payment Processor", "type": "payment"},
            {"id": "queue", "label": "Order Queue", "type": "queue"},
            {"id": "storage", "label": "Object Storage", "type": "storage"},
            {"id": "vendor", "label": "Fulfillment API", "type": "third_party"},
            {"id": "telemetry", "label": "Telemetry Pipeline", "type": "observability"},
        ],
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
    started_at: Optional[str] = None
    paused_at: Optional[str] = None
    paused_seconds: int = 0
    completed_at: Optional[str] = None


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
    trigger_count: int = 0
    scheduled_offset_seconds: Optional[int] = None
    auto_deliver: bool = False


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        migrations = {
            1: _migration_1_initial_schema,
            2: _migration_2_trigger_count,
            3: _migration_3_facilitator_operations,
        }
        for version, migration in migrations.items():
            if version in applied:
                continue
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, timestamp()),
            )
        conn.commit()


def _migration_1_initial_schema(conn: sqlite3.Connection) -> None:
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS objective_assessments (
            exercise_id TEXT NOT NULL,
            objective_index INTEGER NOT NULL,
            rating TEXT NOT NULL,
            notes TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (exercise_id, objective_index),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id)
        )
        """
    )


def _migration_2_trigger_count(conn: sqlite3.Connection) -> None:
    inject_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(inject_options)").fetchall()
    }
    if "trigger_count" not in inject_columns:
        conn.execute(
            "ALTER TABLE inject_options "
            "ADD COLUMN trigger_count INTEGER NOT NULL DEFAULT 0"
        )


def _migration_3_facilitator_operations(conn: sqlite3.Connection) -> None:
    exercise_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(exercises)").fetchall()
    }
    exercise_additions = {
        "started_at": "TEXT",
        "paused_at": "TEXT",
        "paused_seconds": "INTEGER NOT NULL DEFAULT 0",
        "completed_at": "TEXT",
    }
    for column, definition in exercise_additions.items():
        if column not in exercise_columns:
            conn.execute(f"ALTER TABLE exercises ADD COLUMN {column} {definition}")

    inject_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(inject_options)").fetchall()
    }
    inject_additions = {
        "scheduled_offset_seconds": "INTEGER",
        "auto_deliver": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in inject_additions.items():
        if column not in inject_columns:
            conn.execute(
                f"ALTER TABLE inject_options ADD COLUMN {column} {definition}"
            )


def database_schema_version() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
    return int(row["version"]) if row else 0


def database_health() -> dict[str, Any]:
    try:
        with connect() as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            conn.execute("SELECT 1").fetchone()
            schema_row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
    except (OSError, sqlite3.Error) as exc:
        return {
            "healthy": False,
            "schema_version": 0,
            "error": str(exc),
            "path": str(DB_PATH),
        }
    return {
        "healthy": bool(integrity and integrity[0] == "ok"),
        "schema_version": int(schema_row[0]) if schema_row else 0,
        "path": str(DB_PATH),
    }


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        started_at=row["started_at"],
        paused_at=row["paused_at"],
        paused_seconds=row["paused_seconds"],
        completed_at=row["completed_at"],
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
        trigger_count=row["trigger_count"],
        scheduled_offset_seconds=row["scheduled_offset_seconds"],
        auto_deliver=bool(row["auto_deliver"]),
    )


def save_exercise(ex: Exercise) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO exercises (
                id,
                name,
                scenario_type,
                platform,
                business_system,
                difficulty,
                duration_minutes,
                participants,
                objectives,
                status,
                created_at,
                package_path,
                started_at,
                paused_at,
                paused_seconds,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ex.started_at,
                ex.paused_at,
                ex.paused_seconds,
                ex.completed_at,
            ),
        )
        conn.commit()


def save_injects(injects: List[InjectOption]) -> None:
    with connect() as conn:
        for inj in injects:
            conn.execute(
                """
                INSERT INTO inject_options (
                    id,
                    exercise_id,
                    stage,
                    title,
                    audience,
                    description,
                    action_type,
                    script_name,
                    payload,
                    triggered,
                    triggered_at,
                    trigger_count,
                    scheduled_offset_seconds,
                    auto_deliver
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    inj.trigger_count,
                    inj.scheduled_offset_seconds,
                    1 if inj.auto_deliver else 0,
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
    now = timestamp()
    with connect() as conn:
        conn.execute(
            """
            UPDATE inject_options
            SET triggered = 1,
                triggered_at = ?,
                trigger_count = trigger_count + 1
            WHERE id = ?
            """,
            (now, inject_id),
        )
        conn.commit()


def update_exercise_clock(
    exercise_id: str,
    expected_status: str,
    *,
    status: str,
    started_at: Optional[str],
    paused_at: Optional[str],
    paused_seconds: int,
    completed_at: Optional[str],
) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE exercises
            SET status = ?,
                started_at = ?,
                paused_at = ?,
                paused_seconds = ?,
                completed_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                status,
                started_at,
                paused_at,
                paused_seconds,
                completed_at,
                exercise_id,
                expected_status,
            ),
        )
        conn.commit()
    return cursor.rowcount == 1


def set_inject_schedule(
    inject_id: str,
    offset_seconds: int,
    auto_deliver: bool,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE inject_options
            SET scheduled_offset_seconds = ?, auto_deliver = ?
            WHERE id = ?
            """,
            (offset_seconds, 1 if auto_deliver else 0, inject_id),
        )
        conn.commit()


def clear_inject_schedule(inject_id: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE inject_options
            SET scheduled_offset_seconds = NULL, auto_deliver = 0
            WHERE id = ?
            """,
            (inject_id,),
        )
        conn.commit()


def deliver_scheduled_inject(inject_id: str, elapsed_seconds: int) -> bool:
    delivered_at = timestamp()
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE inject_options
            SET triggered = 1,
                triggered_at = ?,
                trigger_count = trigger_count + 1
            WHERE id = ?
              AND action_type = 'narrative'
              AND triggered = 0
              AND auto_deliver = 1
              AND scheduled_offset_seconds IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM exercises
                  WHERE exercises.id = inject_options.exercise_id
                    AND exercises.status = 'running'
              )
            """,
            (delivered_at, inject_id),
        )
        if cursor.rowcount != 1:
            return False
        inject = conn.execute(
            """
            SELECT exercise_id, title, audience
            FROM inject_options
            WHERE id = ?
            """,
            (inject_id,),
        ).fetchone()
        if not inject:
            raise RuntimeError("Scheduled inject disappeared during delivery")
        conn.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_id("evt"),
                inject["exercise_id"],
                "scheduled_inject_delivered",
                inject["title"],
                (
                    f"Audience: {inject['audience']}\n"
                    f"Delivered automatically at T+{elapsed_seconds} seconds"
                ),
                delivered_at,
            ),
        )
        conn.commit()
    return True


def add_event(exercise_id: str, event_type: str, title: str, detail: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?)",
            (new_id("evt"), exercise_id, event_type, title, detail, timestamp()),
        )
        conn.commit()


def list_events(exercise_id: str) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM run_events WHERE exercise_id = ? ORDER BY created_at DESC", (exercise_id,)).fetchall()


def save_objective_assessment(
    exercise_id: str,
    objective_index: int,
    rating: str,
    notes: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO objective_assessments (
                exercise_id,
                objective_index,
                rating,
                notes,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(exercise_id, objective_index) DO UPDATE SET
                rating = excluded.rating,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                exercise_id,
                objective_index,
                rating,
                notes,
                timestamp(),
            ),
        )
        conn.commit()


def list_objective_assessments(exercise_id: str) -> List[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT *
            FROM objective_assessments
            WHERE exercise_id = ?
            ORDER BY objective_index
            """,
            (exercise_id,),
        ).fetchall()
