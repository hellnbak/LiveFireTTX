from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import asyncio
import logging

from app import models
from app.models import Exercise, InjectOption


LOGGER = logging.getLogger("livefirettx.facilitator")
CLOCK_STATUSES = {"created", "running", "paused", "completed"}
CLOCK_COMMANDS = {"start", "pause", "resume", "complete", "reset"}


class ClockTransitionError(ValueError):
    pass


def clock_snapshot(
    exercise: Exercise,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = _utc_now(now)
    started_at = _parse_timestamp(exercise.started_at)
    paused_at = _parse_timestamp(exercise.paused_at)
    completed_at = _parse_timestamp(exercise.completed_at)
    elapsed_seconds = 0
    if started_at:
        effective_end = current_time
        if exercise.status == "paused" and paused_at:
            effective_end = paused_at
        elif exercise.status == "completed" and completed_at:
            effective_end = completed_at
        elapsed_seconds = max(
            0,
            int((effective_end - started_at).total_seconds())
            - exercise.paused_seconds,
        )
    duration_seconds = exercise.duration_minutes * 60
    remaining_seconds = max(0, duration_seconds - elapsed_seconds)
    overtime_seconds = max(0, elapsed_seconds - duration_seconds)
    progress_percent = min(
        100,
        round((elapsed_seconds / max(1, duration_seconds)) * 100),
    )
    return {
        "status": exercise.status,
        "started_at": exercise.started_at,
        "paused_at": exercise.paused_at,
        "completed_at": exercise.completed_at,
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds,
        "overtime_seconds": overtime_seconds,
        "duration_seconds": duration_seconds,
        "progress_percent": progress_percent,
        "server_time": current_time.isoformat(),
    }


def transition_clock(
    exercise_id: str,
    command: str,
    now: datetime | None = None,
) -> Exercise:
    if command not in CLOCK_COMMANDS:
        raise ClockTransitionError("Unsupported exercise clock command")
    exercise = models.get_exercise(exercise_id)
    if not exercise:
        raise ClockTransitionError("Exercise not found")
    if exercise.status not in CLOCK_STATUSES:
        raise ClockTransitionError("Exercise clock state is invalid")

    current_time = _utc_now(now)
    current_timestamp = current_time.isoformat()
    next_status = exercise.status
    started_at = exercise.started_at
    paused_at = exercise.paused_at
    paused_seconds = exercise.paused_seconds
    completed_at = exercise.completed_at

    if command == "start" and exercise.status == "created":
        next_status = "running"
        started_at = current_timestamp
        paused_at = None
        paused_seconds = 0
        completed_at = None
    elif command == "pause" and exercise.status == "running":
        next_status = "paused"
        paused_at = current_timestamp
    elif command == "resume" and exercise.status == "paused":
        paused_seconds += _seconds_between(exercise.paused_at, current_time)
        next_status = "running"
        paused_at = None
    elif command == "complete" and exercise.status in {"running", "paused"}:
        if exercise.status == "paused":
            paused_seconds += _seconds_between(exercise.paused_at, current_time)
        next_status = "completed"
        paused_at = None
        completed_at = current_timestamp
    elif command == "reset" and exercise.status == "completed":
        next_status = "created"
        started_at = None
        paused_at = None
        paused_seconds = 0
        completed_at = None
    else:
        raise ClockTransitionError(
            f"Cannot {command} an exercise in {exercise.status} state"
        )

    updated = models.update_exercise_clock(
        exercise.id,
        exercise.status,
        status=next_status,
        started_at=started_at,
        paused_at=paused_at,
        paused_seconds=paused_seconds,
        completed_at=completed_at,
    )
    if not updated:
        raise ClockTransitionError("Exercise clock changed; refresh and try again")
    refreshed = models.get_exercise(exercise.id)
    if not refreshed:
        raise ClockTransitionError("Exercise not found")
    return refreshed


def schedule_inject(
    inject: InjectOption,
    exercise: Exercise,
    offset_minutes: int,
    auto_deliver: bool,
) -> InjectOption:
    if inject.exercise_id != exercise.id:
        raise ValueError("Inject does not belong to this exercise")
    if inject.action_type != "narrative":
        raise ValueError("Only narrative injects can be scheduled")
    if inject.triggered:
        raise ValueError("Triggered injects cannot be rescheduled")
    if exercise.status == "completed":
        raise ValueError("Completed exercises cannot be rescheduled")
    if offset_minutes < 0 or offset_minutes > exercise.duration_minutes:
        raise ValueError(
            f"Schedule must be between 0 and {exercise.duration_minutes} minutes"
        )
    models.set_inject_schedule(
        inject.id,
        offset_minutes * 60,
        auto_deliver,
    )
    updated = models.get_inject(inject.id)
    if not updated:
        raise ValueError("Inject not found")
    return updated


def clear_schedule(inject: InjectOption) -> InjectOption:
    if inject.triggered:
        raise ValueError("Triggered inject schedules cannot be cleared")
    models.clear_inject_schedule(inject.id)
    updated = models.get_inject(inject.id)
    if not updated:
        raise ValueError("Inject not found")
    return updated


def inject_schedule_snapshot(
    exercise: Exercise,
    injects: list[InjectOption],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    clock = clock_snapshot(exercise, now)
    elapsed_seconds = int(clock["elapsed_seconds"])
    snapshots = []
    for inject in injects:
        offset = inject.scheduled_offset_seconds
        status = "unscheduled"
        remaining_seconds: int | None = None
        if inject.triggered:
            status = "delivered"
        elif offset is not None:
            remaining_seconds = max(0, offset - elapsed_seconds)
            if exercise.status == "completed":
                status = "missed"
            elif exercise.status in {"running", "paused"} and offset <= elapsed_seconds:
                status = "due"
            else:
                status = "scheduled"
        snapshots.append(
            {
                "id": inject.id,
                "title": inject.title,
                "action_type": inject.action_type,
                "status": status,
                "offset_seconds": offset,
                "remaining_seconds": remaining_seconds,
                "auto_deliver": inject.auto_deliver,
                "triggered_at": inject.triggered_at,
            }
        )
    return snapshots


def dispatch_due_injects(
    exercise_id: str | None = None,
    now: datetime | None = None,
) -> list[str]:
    current_time = _utc_now(now)
    exercises = (
        [exercise]
        if exercise_id and (exercise := models.get_exercise(exercise_id))
        else models.list_exercises()
        if exercise_id is None
        else []
    )
    delivered = []
    for exercise in exercises:
        if exercise.status != "running":
            continue
        elapsed_seconds = int(clock_snapshot(exercise, current_time)["elapsed_seconds"])
        for inject in models.get_injects(exercise.id):
            offset = inject.scheduled_offset_seconds
            if (
                inject.action_type != "narrative"
                or inject.triggered
                or not inject.auto_deliver
                or offset is None
                or offset > elapsed_seconds
            ):
                continue
            if models.deliver_scheduled_inject(inject.id, elapsed_seconds):
                delivered.append(inject.id)
    return delivered


async def scheduler_loop(interval_seconds: int) -> None:
    while True:
        try:
            await asyncio.to_thread(dispatch_due_injects)
        except Exception as exc:
            LOGGER.warning(
                "Scheduled inject dispatch failed (%s)",
                type(exc).__name__,
            )
        await asyncio.sleep(interval_seconds)


def _utc_now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ClockTransitionError("Exercise clock timestamp is invalid") from exc
    return _utc_now(parsed)


def _seconds_between(value: str | None, current_time: datetime) -> int:
    started = _parse_timestamp(value)
    if not started:
        raise ClockTransitionError("Exercise pause timestamp is missing")
    return max(0, int((current_time - started).total_seconds()))
