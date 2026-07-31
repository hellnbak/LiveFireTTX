from __future__ import annotations

from datetime import datetime
from typing import Any

from app import models
from app.models import Exercise, ExerciseCheckpoint, InjectOption
from app.services.facilitator import clock_snapshot, inject_schedule_snapshot


def seed_default_checkpoints(exercise: Exercise) -> list[ExerciseCheckpoint]:
    checkpoints = [
        (
            min(10, exercise.duration_minutes),
            "Command and Scope Check",
            "All Participants",
            "Confirm incident command, known impact, and immediate priorities.",
            "Name the incident lead, working scope, and next decision point.",
            0 if exercise.objectives else None,
        ),
        (
            max(15, exercise.duration_minutes // 2),
            "Mid-Exercise Decision Review",
            "Incident Commander",
            "Pause for a concise decision-quality and confidence review.",
            "State current impact, confidence, options, and selected action.",
            1 if len(exercise.objectives) > 1 else 0 if exercise.objectives else None,
        ),
        (
            max(15, exercise.duration_minutes - 10),
            "Recovery and Communications Check",
            "All Participants",
            "Confirm recovery evidence, residual risk, and stakeholder messaging.",
            "Agree on recovery proof, owners, communications, and follow-up work.",
            len(exercise.objectives) - 1 if exercise.objectives else None,
        ),
    ]
    return [
        models.create_checkpoint(
            exercise.id,
            title=title,
            description=description,
            audience=audience,
            expected_action=expected_action,
            scheduled_offset_seconds=minute * 60,
            objective_index=objective_index,
        )
        for (
            minute,
            title,
            audience,
            description,
            expected_action,
            objective_index,
        ) in checkpoints
    ]


def build_run_of_show(
    exercise: Exercise,
    injects: list[InjectOption],
    checkpoints: list[ExerciseCheckpoint],
    now: datetime | None = None,
) -> dict[str, Any]:
    clock = clock_snapshot(exercise, now)
    elapsed_seconds = int(clock["elapsed_seconds"])
    schedule_by_id = {
        item["id"]: item
        for item in inject_schedule_snapshot(exercise, injects, now)
    }
    entries = [
        _inject_entry(inject, schedule_by_id[inject.id]) for inject in injects
    ]
    entries.extend(
        _checkpoint_entry(exercise, checkpoint, elapsed_seconds)
        for checkpoint in checkpoints
    )
    entries.sort(key=_timeline_sort_key)
    actionable = [
        entry
        for entry in entries
        if entry["status"] in {"due", "scheduled"}
        and entry["offset_seconds"] is not None
    ]
    actionable.sort(
        key=lambda entry: (
            0 if entry["status"] == "due" else 1,
            entry["offset_seconds"],
            entry["title"].lower(),
        )
    )
    completed = sum(
        entry["status"] in {"completed", "delivered"} for entry in entries
    )
    due = sum(entry["status"] == "due" for entry in entries)
    return {
        "clock": clock,
        "entries": entries,
        "next_entry": actionable[0] if actionable else None,
        "entry_count": len(entries),
        "completed_count": completed,
        "due_count": due,
    }


def participant_snapshot(
    exercise: Exercise,
    injects: list[InjectOption],
    now: datetime | None = None,
) -> dict[str, Any]:
    delivered = [
        {
            "id": inject.id,
            "title": inject.title,
            "audience": inject.audience,
            "description": inject.description,
            "action_type": inject.action_type,
            "triggered_at": inject.triggered_at,
        }
        for inject in injects
        if inject.triggered and inject.action_type in {"narrative", "artifact"}
    ]
    delivered.sort(key=lambda item: item["triggered_at"] or "", reverse=True)
    return {
        "exercise": {
            "id": exercise.id,
            "name": exercise.name,
            "business_system": exercise.business_system,
            "status": exercise.status,
        },
        "clock": clock_snapshot(exercise, now),
        "current_inject": delivered[0] if delivered else None,
        "delivered_injects": delivered,
    }


def _inject_entry(
    inject: InjectOption,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    kind = {
        "narrative": "narrative",
        "artifact": "artifact",
        "chaos_script": "chaos",
    }.get(inject.action_type, "inject")
    return {
        "id": inject.id,
        "source": "inject",
        "kind": kind,
        "title": inject.title,
        "description": inject.description,
        "audience": inject.audience,
        "expected_action": str(inject.payload.get("expected_action", "")),
        "objective_index": None,
        "offset_seconds": schedule["offset_seconds"],
        "remaining_seconds": schedule["remaining_seconds"],
        "status": schedule["status"],
        "auto_deliver": schedule["auto_deliver"],
        "actionable": not inject.triggered,
    }


def _checkpoint_entry(
    exercise: Exercise,
    checkpoint: ExerciseCheckpoint,
    elapsed_seconds: int,
) -> dict[str, Any]:
    status = "completed" if checkpoint.status == "completed" else "scheduled"
    if checkpoint.status != "completed":
        if exercise.status == "completed":
            status = "missed"
        elif (
            exercise.status in {"running", "paused"}
            and checkpoint.scheduled_offset_seconds <= elapsed_seconds
        ):
            status = "due"
    return {
        "id": checkpoint.id,
        "source": "checkpoint",
        "kind": "checkpoint",
        "title": checkpoint.title,
        "description": checkpoint.description,
        "audience": checkpoint.audience,
        "expected_action": checkpoint.expected_action,
        "objective_index": checkpoint.objective_index,
        "offset_seconds": checkpoint.scheduled_offset_seconds,
        "remaining_seconds": max(
            0,
            checkpoint.scheduled_offset_seconds - elapsed_seconds,
        ),
        "status": status,
        "auto_deliver": False,
        "actionable": checkpoint.status == "pending",
    }


def _timeline_sort_key(entry: dict[str, Any]) -> tuple[int, int, str]:
    offset = entry["offset_seconds"]
    return (
        1 if offset is None else 0,
        offset if offset is not None else 0,
        entry["title"].lower(),
    )
