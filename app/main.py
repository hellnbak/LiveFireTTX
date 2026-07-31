# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse, urlsplit
import asyncio
import json
import logging
import uuid

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.models import (
    Exercise,
    ExerciseCreate,
    InjectOption,
    SCENARIO_LIBRARY,
    add_event,
    complete_checkpoint,
    create_checkpoint,
    create_improvement_action,
    get_checkpoint,
    get_exercise,
    get_improvement_action,
    get_inject,
    get_injects,
    get_organization_profile,
    init_db,
    list_checkpoints,
    list_events,
    list_exercises,
    list_improvement_actions,
    list_objective_assessments,
    mark_inject_triggered,
    save_objective_assessment,
    save_exercise,
    save_injects,
    update_improvement_action_status,
)
from app.routes.packages import router as packages_router
from app.routes.system import router as system_router
from app.routes.auth import router as auth_router
from app.routes.library import router as library_router
from app.services.artifacts import (
    ARTIFACT_KINDS,
    artifact_trigger_result,
    create_safe_artifact_inject,
)
from app.services.evidence import (
    EvidenceVerificationError,
    existing_key_id,
    list_evidence_archives,
    load_or_create_signing_key,
    load_signing_key,
    read_retained_archive,
    save_evidence_archive,
    signing_key_id,
)
from app.services.auth import (
    AUTH_COOKIE_NAME,
    LOCAL_ADMIN,
    required_capability,
    resolve_session,
    seed_bootstrap_admin,
)
from app.services.generator import create_exercise_from_request
from app.services.facilitator import (
    ClockTransitionError,
    clear_schedule,
    clock_snapshot,
    dispatch_due_injects,
    inject_schedule_snapshot,
    schedule_inject,
    scheduler_loop,
    transition_clock,
)
from app.services.intelligence import (
    RATING_LABELS,
    RATING_SCORES,
    build_evidence_archive,
    build_exercise_intelligence,
    render_evidence_markdown,
)
from app.services.labs import LabOperationError, lab_snapshot, run_lab_operation
from app.services.operations import (
    build_run_of_show,
    participant_snapshot,
    seed_default_checkpoints,
)
from app.services.scenario_library import (
    latest_organization_profiles,
    organization_profile_payload,
    seed_builtin_scenario_packs,
)
from app.services.runtime import (
    ChaosExecutionError,
    ChaosPreflightError,
    clone_playbook_configuration,
    control_chaos_playbook_run,
    emergency_stop,
    export_playbook_configuration,
    read_chaos_state,
    read_control_status,
    read_dependency_status,
    read_playbook_configuration,
    read_playbook_definition,
    read_playbook_library,
    reset_chaos,
    restore_playbook_version,
    run_chaos_inject,
    save_playbook_configuration,
    skip_chaos_playbook_stage,
    start_chaos_playbook,
    validate_playbook_configuration,
)
from app.services.packages import (
    build_exercise_archive,
    dependency_map,
    list_participant_briefs,
)
from app.services.paths import (
    PackagePathError,
    exercise_package_path,
    validate_exercise_id,
)
from app.version import __version__

BASE = Path(__file__).resolve().parent
LOGGER = logging.getLogger("livefirettx")
if not LOGGER.handlers:
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(log_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
app = FastAPI(
    title="LiveFireTTX",
    version=__version__,
    description="Local-first live-fire tabletop exercise orchestration.",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.allowed_hosts),
)
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["app_version"] = __version__
app.mount("/static", StaticFiles(directory=str(BASE / "templates" / "static")), name="static")
app.include_router(system_router)
app.include_router(packages_router)
app.include_router(auth_router)
app.include_router(library_router)


@app.exception_handler(PackagePathError)
async def unsafe_package_path_handler(
    request: Request,
    error: PackagePathError,
) -> JSONResponse:
    LOGGER.warning(
        json.dumps(
            {
                "event": "unsafe_package_path_rejected",
                "path": request.url.path,
                "error_type": type(error).__name__,
            },
            sort_keys=True,
        )
    )
    return JSONResponse(
        {"detail": "Exercise package metadata is invalid"},
        status_code=409,
    )


async def _form_fields(
    request: Request,
    maximum_bytes: int = 64 * 1024,
) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected URL-encoded form data")
    body = await request.body()
    if len(body) > maximum_bytes:
        raise HTTPException(413, "Form submission is too large")
    try:
        parsed = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=50,
            strict_parsing=False,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Form submission is invalid") from exc
    return {key: values[-1] for key, values in parsed.items() if values}


def _field(
    fields: dict[str, str],
    name: str,
    default: str | None = None,
) -> str:
    value = fields.get(name, default)
    if value is None:
        raise HTTPException(422, f"Missing form field: {name}")
    return value


def _integer_field(
    fields: dict[str, str],
    name: str,
    default: int,
) -> int:
    try:
        return int(_field(fields, name, str(default)))
    except ValueError as exc:
        raise HTTPException(422, f"{name} must be an integer") from exc


def _redirect_to_exercise(exercise: Exercise) -> RedirectResponse:
    exercise_id = validate_exercise_id(exercise.id)
    target = f"/exercises/{quote(exercise_id, safe='')}".replace("\\", "")
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/exercises/ttx_")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        target = "/"
    return RedirectResponse(target, status_code=303)


def _same_allowed_origin(request: Request, origin: str) -> bool:
    try:
        candidate = urlsplit(origin)
        request_origin = urlsplit(
            f"{request.url.scheme}://{request.headers.get('host', '')}"
        )
        candidate_port = candidate.port or (
            443 if candidate.scheme == "https" else 80
        )
        request_port = request_origin.port or (
            443 if request_origin.scheme == "https" else 80
        )
    except ValueError:
        return False
    return bool(
        candidate.scheme == request.url.scheme
        and candidate.scheme in {"http", "https"}
        and candidate.hostname == request_origin.hostname
        and (
            settings.shared_mode
            or candidate.hostname in LOOPBACK_HOSTS
        )
        and candidate_port == request_port
        and candidate.username is None
        and candidate.password is None
        and candidate.path in {"", "/"}
        and not candidate.query
        and not candidate.fragment
    )


def _redirect_to_run_mode(exercise: Exercise) -> RedirectResponse:
    return RedirectResponse(
        url=f"/exercises/{quote(exercise.id, safe='')}/run",
        status_code=303,
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    opaque_same_origin = origin == "null" and fetch_site == "same-origin"
    request.state.current_user = LOCAL_ADMIN if not settings.shared_mode else None
    if settings.shared_mode:
        request.state.current_user = resolve_session(
            request.cookies.get(AUTH_COOKIE_NAME)
        )
    required = required_capability(request.method, request.url.path)
    user = request.state.current_user
    response: Response
    if settings.shared_mode and required and not user:
        if request.method == "GET" and "text/html" in request.headers.get(
            "accept",
            "",
        ):
            next_path = quote(
                request.url.path
                + (f"?{request.url.query}" if request.url.query else ""),
                safe="/?=&",
            )
            response = RedirectResponse(
                f"/login?next={next_path}",
                status_code=303,
            )
        else:
            response = JSONResponse(
                {"detail": "Authentication required"},
                status_code=401,
            )
    elif settings.shared_mode and required and not user.can(required):
        response = JSONResponse(
            {"detail": "This account does not have permission for that action"},
            status_code=403,
        )
    elif request.method in MUTATING_METHODS and (
        (
            origin is not None
            and not opaque_same_origin
            and not _same_allowed_origin(request, origin)
        )
        or (origin is None and fetch_site == "cross-site")
    ):
        LOGGER.warning(
            json.dumps(
                {
                    "event": "request_rejected",
                    "reason": "cross_origin_mutation",
                    "method": request.method,
                    "path": request.url.path,
                    "origin": origin,
                    "host": request.headers.get("host"),
                    "sec_fetch_site": fetch_site or None,
                },
                sort_keys=True,
            )
        )
        response = JSONResponse(
            {"detail": "Cross-origin state changes are not allowed"},
            status_code=403,
        )
    else:
        response = await call_next(request)
    completed = datetime.now(timezone.utc)
    elapsed_ms = round(
        (completed - started).total_seconds() * 1000,
        2,
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )
    if settings.shared_mode:
        response.headers["Cache-Control"] = "no-store"
    if settings.shared_mode and settings.secure_cookies:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    LOGGER.info(
        json.dumps(
            {
                "event": "request_completed",
                "timestamp": completed.isoformat(),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
            sort_keys=True,
        )
    )
    return response


def _exercise_evidence(exercise):
    injects = get_injects(exercise.id)
    events = list_events(exercise.id)
    chaos_state = read_chaos_state(exercise)
    intelligence = build_exercise_intelligence(
        exercise,
        injects,
        events,
        chaos_state,
        list_objective_assessments(exercise.id),
        list_improvement_actions(exercise.id),
        list_checkpoints(exercise.id),
    )
    return injects, events, chaos_state, intelligence


def _evidence_archive_context(exercise: Exercise) -> dict[str, Any]:
    key = None
    key_id = None
    try:
        key_id = existing_key_id(settings.evidence_signing_key_path)
        if key_id:
            key = load_signing_key(settings.evidence_signing_key_path)
    except ValueError:
        pass
    return {
        "archives": list_evidence_archives(exercise, key, limit=8),
        "key_id": key_id,
        "retention_days": settings.evidence_retention_days,
        "retention_count": settings.evidence_retention_count,
    }


@app.on_event("startup")
async def startup() -> None:
    init_db()
    seed_builtin_scenario_packs()
    seed_bootstrap_admin(
        shared_mode=settings.shared_mode,
        username=settings.bootstrap_admin_username,
        password=settings.bootstrap_admin_password,
    )
    app.state.facilitator_scheduler = None
    if settings.scheduler_enabled:
        app.state.facilitator_scheduler = asyncio.create_task(
            scheduler_loop(settings.scheduler_interval_seconds)
        )


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler = getattr(app.state, "facilitator_scheduler", None)
    if scheduler:
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler
        app.state.facilitator_scheduler = None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "exercises": list_exercises(),
            "scenarios": SCENARIO_LIBRARY,
        },
    )


@app.get("/new", response_class=HTMLResponse)
def new_exercise(request: Request):
    profiles = latest_organization_profiles()
    return templates.TemplateResponse(
        request,
        "new.html",
        {
            "scenarios": SCENARIO_LIBRARY,
            "organization_profiles": profiles,
            "organization_profile_catalog": [
                {"id": profile.id, **organization_profile_payload(profile)}
                for profile in profiles
            ],
        },
    )


@app.post("/exercises")
async def create_exercise(request: Request):
    fields = await _form_fields(request)
    name = _field(fields, "name")
    scenario_type = _field(fields, "scenario_type")
    platform = _field(fields, "platform", "local_docker")
    business_system = _field(fields, "business_system", "Order Processing")
    difficulty = _field(fields, "difficulty", "intermediate")
    duration_minutes = _integer_field(fields, "duration_minutes", 90)
    participants = _field(
        fields,
        "participants",
        (
            "Incident Commander, Security Operations, Cloud/IT Operations, "
            "Communications, Business Owner"
        ),
    )
    objectives = _field(fields, "objectives", "")
    organization_profile_id = fields.get("organization_profile_id") or None
    name = name.strip()
    business_system = business_system.strip()
    if not name or len(name) > 120:
        raise HTTPException(400, "Exercise name must be between 1 and 120 characters")
    if scenario_type not in SCENARIO_LIBRARY:
        raise HTTPException(400, "Unknown scenario type")
    if platform != "local_docker":
        raise HTTPException(400, "Only the local Docker platform is currently supported")
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise HTTPException(400, "Unknown difficulty")
    if not 15 <= duration_minutes <= 480:
        raise HTTPException(400, "Duration must be between 15 and 480 minutes")
    if not business_system or len(business_system) > 120:
        raise HTTPException(400, "Business system must be between 1 and 120 characters")

    participant_list = [p.strip() for p in participants.split(",") if p.strip()]
    objective_list = [o.strip() for o in objectives.split("\n") if o.strip()]
    if len(participant_list) > 25 or any(len(item) > 120 for item in participant_list):
        raise HTTPException(400, "Participant list is too large")
    if len(objective_list) > 20 or any(len(item) > 240 for item in objective_list):
        raise HTTPException(400, "Objective list is too large")
    if organization_profile_id and not get_organization_profile(
        organization_profile_id
    ):
        raise HTTPException(400, "Organization profile was not found")

    req = ExerciseCreate(
        name=name,
        scenario_type=scenario_type,
        platform=platform,
        business_system=business_system,
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        participants=participant_list,
        objectives=objective_list,
    )
    ex, injects = create_exercise_from_request(
        req,
        organization_profile_id=organization_profile_id,
    )
    save_exercise(ex)
    save_injects(injects)
    seed_default_checkpoints(ex)
    add_event(
        ex.id,
        "exercise_created",
        "Exercise Created",
        "Generated the local exercise package",
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}", response_class=HTMLResponse)
def exercise_detail(request: Request, exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    injects, events, chaos_state, intelligence = _exercise_evidence(ex)
    clock = clock_snapshot(ex)
    inject_schedules = inject_schedule_snapshot(ex, injects)
    run_of_show = build_run_of_show(
        ex,
        injects,
        list_checkpoints(ex.id),
    )
    by_stage: dict[str, list[InjectOption]] = {}
    for i in injects:
        by_stage.setdefault(i.stage, []).append(i)
    chaos_actions = []
    known_actions = set()
    for inject in injects:
        action = inject.payload.get("action")
        if inject.action_type != "chaos_script" or not action:
            continue
        if action in known_actions:
            continue
        known_actions.add(action)
        chaos_actions.append({"id": action, "label": inject.title})
    playbook_library = read_playbook_library(ex)
    designer_playbook = (
        read_playbook_definition(ex, playbook_library[0]["id"])
        if playbook_library
        else {}
    )
    control_status = read_control_status(ex)
    dependencies: dict[str, Any] = (
        read_dependency_status(ex)
        if control_status.get("matches_exercise")
        else {"reachable": False, "dependencies": []}
    )
    dependency_status_by_id = {
        item.get("id"): item
        for item in dependencies.get("dependencies", [])
        if isinstance(item, dict)
    }
    return templates.TemplateResponse(
        request,
        "exercise.html",
        {
            "exercise": ex,
            "injects_by_stage": by_stage,
            "events": events,
            "chaos_state": chaos_state,
            "control_status": control_status,
            "playbook_configuration": read_playbook_configuration(ex),
            "playbook_library": playbook_library,
            "designer_playbook": designer_playbook,
            "chaos_actions": chaos_actions,
            "artifact_kinds": ARTIFACT_KINDS,
            "intelligence": intelligence,
            "rating_labels": RATING_LABELS,
            "scenario": SCENARIO_LIBRARY[ex.scenario_type],
            "dependency_map": dependency_map(ex),
            "dependency_status": dependencies,
            "dependency_status_by_id": dependency_status_by_id,
            "participant_briefs": list_participant_briefs(ex),
            "clock": clock,
            "inject_schedules": {
                item["id"]: item for item in inject_schedules
            },
            "scheduler_enabled": settings.scheduler_enabled,
            "run_of_show": run_of_show,
            "lab": lab_snapshot(ex),
            "improvement_actions": list_improvement_actions(ex.id),
            "evidence_exports": _evidence_archive_context(ex),
        },
    )


@app.get("/exercises/{exercise_id}/run", response_class=HTMLResponse)
def exercise_run_mode(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    injects = get_injects(exercise.id)
    run_of_show = build_run_of_show(
        exercise,
        injects,
        list_checkpoints(exercise.id),
    )
    control_status = read_control_status(exercise)
    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "exercise": exercise,
            "clock": run_of_show["clock"],
            "run_of_show": run_of_show,
            "control_status": control_status,
            "lab": lab_snapshot(exercise),
            "scheduler_enabled": settings.scheduler_enabled,
        },
    )


@app.get("/exercises/{exercise_id}/present", response_class=HTMLResponse)
def exercise_presentation(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    snapshot = participant_snapshot(exercise, get_injects(exercise.id))
    return templates.TemplateResponse(
        request,
        "present.html",
        {
            "exercise": exercise,
            "snapshot": snapshot,
        },
    )


@app.get("/exercises/{exercise_id}/present/status")
def exercise_presentation_status(exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    return JSONResponse(
        participant_snapshot(exercise, get_injects(exercise.id))
    )


@app.get("/exercises/{exercise_id}/evaluate", response_class=HTMLResponse)
def exercise_evaluation(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    injects, events, _, intelligence = _exercise_evidence(exercise)
    return templates.TemplateResponse(
        request,
        "evaluate.html",
        {
            "exercise": exercise,
            "intelligence": intelligence,
            "rating_labels": RATING_LABELS,
            "events": events,
            "run_of_show": build_run_of_show(
                exercise,
                injects,
                list_checkpoints(exercise.id),
            ),
            "improvement_actions": list_improvement_actions(exercise.id),
            "evidence_exports": _evidence_archive_context(exercise),
        },
    )


@app.post("/exercises/{exercise_id}/lab/{command}")
def control_exercise_lab(exercise_id: str, command: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    operation = "deploy" if command == "launch" else command
    if operation not in {"deploy", "validate", "destroy"}:
        raise HTTPException(404, "Lab operation not found")
    try:
        result = run_lab_operation(exercise, operation)
    except LabOperationError as exc:
        add_event(
            exercise.id,
            "lab_operation_failed",
            f"Lab {command.title()} Failed",
            str(exc),
        )
        raise HTTPException(503, str(exc)) from exc
    add_event(
        exercise.id,
        "lab_operation",
        f"Lab {command.title()} Completed",
        result["output"],
    )
    if command == "launch" and exercise.status == "created":
        exercise = transition_clock(exercise.id, "start")
        add_event(
            exercise.id,
            "exercise_start",
            "Exercise Started",
            "One-click launch deployed the lab and started the facilitator clock",
        )
        if settings.scheduler_enabled:
            dispatch_due_injects(exercise.id)
    return _redirect_to_run_mode(exercise)


@app.post("/exercises/{exercise_id}/checkpoints")
async def add_exercise_checkpoint(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    if exercise.status == "completed":
        raise HTTPException(409, "Completed exercises cannot add checkpoints")
    fields = await _form_fields(request)
    title = _field(fields, "title").strip()
    description = _field(fields, "description").strip()
    audience = _field(fields, "audience").strip()
    expected_action = _field(fields, "expected_action").strip()
    offset_minutes = _integer_field(fields, "offset_minutes", 0)
    raw_objective_index = _field(fields, "objective_index", "")
    if not title or len(title) > 120:
        raise HTTPException(400, "Checkpoint title must be 1 to 120 characters")
    if not description or len(description) > 1000:
        raise HTTPException(400, "Checkpoint description must be 1 to 1000 characters")
    if not audience or len(audience) > 120:
        raise HTTPException(400, "Checkpoint audience must be 1 to 120 characters")
    if not expected_action or len(expected_action) > 1000:
        raise HTTPException(400, "Expected action must be 1 to 1000 characters")
    if not 0 <= offset_minutes <= exercise.duration_minutes:
        raise HTTPException(400, "Checkpoint time is outside the exercise duration")
    objective_index = None
    if raw_objective_index:
        try:
            objective_index = int(raw_objective_index)
        except ValueError as exc:
            raise HTTPException(400, "Objective selection is invalid") from exc
        if not 0 <= objective_index < len(exercise.objectives):
            raise HTTPException(400, "Objective selection is invalid")
    checkpoint = create_checkpoint(
        exercise.id,
        title=title,
        description=description,
        audience=audience,
        expected_action=expected_action,
        scheduled_offset_seconds=offset_minutes * 60,
        objective_index=objective_index,
    )
    add_event(
        exercise.id,
        "checkpoint_created",
        f"MSEL Checkpoint Added: {checkpoint.title}",
        f"Scheduled for T+{offset_minutes} minutes\nAudience: {audience}",
    )
    return _redirect_to_exercise(exercise)


@app.post("/checkpoints/{checkpoint_id}/complete")
def complete_exercise_checkpoint(checkpoint_id: str):
    checkpoint = get_checkpoint(checkpoint_id)
    if not checkpoint:
        raise HTTPException(404, "Checkpoint not found")
    exercise = get_exercise(checkpoint.exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    if not complete_checkpoint(checkpoint.id):
        raise HTTPException(409, "Checkpoint has already been completed")
    add_event(
        exercise.id,
        "checkpoint_completed",
        f"MSEL Checkpoint Completed: {checkpoint.title}",
        f"Expected action: {checkpoint.expected_action}",
    )
    return _redirect_to_run_mode(exercise)


@app.post("/exercises/{exercise_id}/improvements")
async def add_improvement_action(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    fields = await _form_fields(request)
    title = _field(fields, "title").strip()
    owner = _field(fields, "owner").strip()
    due_date = _field(fields, "due_date", "").strip() or None
    notes = _field(fields, "notes", "").strip()
    if not title or len(title) > 160:
        raise HTTPException(400, "Action title must be 1 to 160 characters")
    if not owner or len(owner) > 120:
        raise HTTPException(400, "Action owner must be 1 to 120 characters")
    if len(notes) > 3000:
        raise HTTPException(400, "Action notes must be 3000 characters or fewer")
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError as exc:
            raise HTTPException(400, "Due date must use YYYY-MM-DD") from exc
    action = create_improvement_action(
        exercise.id,
        title=title,
        owner=owner,
        due_date=due_date,
        notes=notes,
    )
    add_event(
        exercise.id,
        "improvement_action_created",
        f"Improvement Action Added: {action.title}",
        f"Owner: {action.owner}\nDue: {action.due_date or 'Not set'}",
    )
    return RedirectResponse(
        url=f"/exercises/{quote(exercise.id, safe='')}/evaluate",
        status_code=303,
    )


@app.post("/improvements/{action_id}/status/{status}")
def set_improvement_action_status(action_id: str, status: str):
    if status not in {"open", "in_progress", "completed"}:
        raise HTTPException(404, "Improvement status not found")
    action = get_improvement_action(action_id)
    if not action:
        raise HTTPException(404, "Improvement action not found")
    exercise = get_exercise(action.exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    update_improvement_action_status(action.id, status)
    add_event(
        exercise.id,
        "improvement_action_status",
        f"Improvement Action Updated: {action.title}",
        f"Status: {status.replace('_', ' ')}",
    )
    return RedirectResponse(
        url=f"/exercises/{quote(exercise.id, safe='')}/evaluate",
        status_code=303,
    )


@app.post("/exercises/{exercise_id}/clock/{command}")
def control_exercise_clock(request: Request, exercise_id: str, command: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    try:
        updated = transition_clock(exercise.id, command)
    except ClockTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    event_titles = {
        "start": "Exercise Started",
        "pause": "Exercise Paused",
        "resume": "Exercise Resumed",
        "complete": "Exercise Completed",
        "reset": "Exercise Clock Reset",
    }
    add_event(
        updated.id,
        f"exercise_{command}",
        event_titles[command],
        f"Facilitator changed exercise clock to {updated.status}",
    )
    if settings.scheduler_enabled and command in {"start", "resume"}:
        dispatch_due_injects(updated.id)
    if request.query_params.get("view") == "run":
        return _redirect_to_run_mode(updated)
    return _redirect_to_exercise(updated)


@app.post("/injects/{inject_id}/trigger")
async def trigger_inject(
    request: Request,
    inject_id: str,
):
    fields = await _form_fields(request)
    intensity = _field(fields, "intensity", "medium")
    duration_seconds = _integer_field(fields, "duration_seconds", 300)
    guardrail_profile = _field(fields, "guardrail_profile", "standard")
    pattern = _field(fields, "pattern", "steady")
    inj = get_inject(inject_id)
    if not inj:
        raise HTTPException(404, "Inject not found")
    ex = get_exercise(inj.exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if inj.triggered and inj.action_type != "chaos_script":
        raise HTTPException(409, "Narrative inject has already been triggered")

    result = "Triggered narrative/artifact inject."
    if inj.action_type == "chaos_script":
        try:
            result = run_chaos_inject(
                ex,
                inj,
                intensity,
                duration_seconds,
                guardrail_profile,
                pattern,
            )
        except ValueError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(400, result) from exc
        except ChaosPreflightError as exc:
            result = str(exc)
            add_event(ex.id, "inject_preflight_failed", inj.title, result)
            raise HTTPException(503, result) from exc
        except ChaosExecutionError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(500, result) from exc
    elif inj.action_type == "artifact":
        try:
            result = artifact_trigger_result(ex, inj)
        except ValueError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(400, result) from exc

    mark_inject_triggered(inject_id)
    detail = f"Audience: {inj.audience}\nAction: {inj.action_type}"
    if inj.action_type == "chaos_script":
        detail += (
            f"\nIntensity: {intensity}"
            f"\nDuration: {duration_seconds} seconds"
            f"\nPattern: {pattern}"
            f"\nGuardrails: {guardrail_profile}"
        )
    add_event(ex.id, "inject_triggered", inj.title, f"{detail}\n{result}")
    if request.query_params.get("view") == "run":
        return _redirect_to_run_mode(ex)
    return _redirect_to_exercise(ex)


@app.post("/injects/{inject_id}/schedule")
async def set_inject_schedule(request: Request, inject_id: str):
    inject = get_inject(inject_id)
    if not inject:
        raise HTTPException(404, "Inject not found")
    exercise = get_exercise(inject.exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    fields = await _form_fields(request)
    offset_minutes = _integer_field(fields, "offset_minutes", 0)
    auto_deliver = _field(fields, "auto_deliver", "") == "on"
    try:
        updated = schedule_inject(
            inject,
            exercise,
            offset_minutes,
            auto_deliver,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        exercise.id,
        "inject_scheduled",
        f"Inject Scheduled: {updated.title}",
        (
            f"Delivery: T+{offset_minutes} minutes\n"
            f"Mode: {'automatic' if auto_deliver else 'facilitator prompt'}"
        ),
    )
    if settings.scheduler_enabled:
        dispatch_due_injects(exercise.id)
    return _redirect_to_exercise(exercise)


@app.post("/injects/{inject_id}/schedule/clear")
def clear_inject_schedule(inject_id: str):
    inject = get_inject(inject_id)
    if not inject:
        raise HTTPException(404, "Inject not found")
    exercise = get_exercise(inject.exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    try:
        clear_schedule(inject)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        exercise.id,
        "inject_schedule_cleared",
        f"Inject Schedule Cleared: {inject.title}",
        "The facilitator removed the scheduled delivery time",
    )
    return _redirect_to_exercise(exercise)


@app.post("/exercises/{exercise_id}/chaos/reset")
async def reset_exercise_chaos(request: Request, exercise_id: str):
    action = _field(await _form_fields(request), "action", "")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = reset_chaos(ex, action or None)
    except ChaosPreflightError as exc:
        add_event(ex.id, "chaos_reset_failed", "Chaos Reset Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "chaos_reset_failed", "Chaos Reset Failed", str(exc))
        raise HTTPException(500, str(exc)) from exc

    label = action or "all actions"
    add_event(ex.id, "chaos_reset", "Chaos State Reset", f"Reset: {label}\n{result}")
    if request.query_params.get("view") == "run":
        return _redirect_to_run_mode(ex)
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/chaos/emergency-stop")
def emergency_stop_exercise_chaos(request: Request, exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = emergency_stop(ex)
    except ChaosExecutionError as exc:
        add_event(
            ex.id,
            "chaos_emergency_stop_failed",
            "Emergency Stop Failed",
            str(exc),
        )
        raise HTTPException(503, str(exc)) from exc

    add_event(
        ex.id,
        "chaos_emergency_stop",
        "Emergency Stop",
        result,
    )
    if request.query_params.get("view") == "run":
        return _redirect_to_run_mode(ex)
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/chaos/status")
def exercise_chaos_status(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    injects = get_injects(ex.id)
    control_status = read_control_status(ex)
    dependencies = (
        read_dependency_status(ex)
        if control_status.get("matches_exercise")
        else {"reachable": False, "dependencies": []}
    )
    return JSONResponse(
        {
            "state": read_chaos_state(ex),
            "control": control_status,
            "dependencies": dependencies,
            "clock": clock_snapshot(ex),
            "inject_schedules": inject_schedule_snapshot(ex, injects),
            "run_of_show": build_run_of_show(
                ex,
                injects,
                list_checkpoints(ex.id),
            ),
        }
    )


@app.post("/exercises/{exercise_id}/objectives/{objective_index}")
async def assess_exercise_objective(
    request: Request,
    exercise_id: str,
    objective_index: int,
):
    fields = await _form_fields(request)
    rating = _field(fields, "rating")
    notes = _field(fields, "notes", "")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if not 0 <= objective_index < len(ex.objectives):
        raise HTTPException(404, "Objective not found")
    if rating not in RATING_SCORES:
        raise HTTPException(400, "Unknown objective rating")
    notes = notes.strip()
    if len(notes) > 2000:
        raise HTTPException(400, "Objective notes must be 2000 characters or fewer")
    save_objective_assessment(
        exercise_id,
        objective_index,
        rating,
        notes,
    )
    add_event(
        exercise_id,
        "objective_assessed",
        f"Objective Assessed: {ex.objectives[objective_index]}",
        f"Rating: {RATING_LABELS[rating]}\nNotes: {notes or 'None'}",
    )
    if request.query_params.get("view") == "evaluate":
        return RedirectResponse(
            url=f"/exercises/{quote(ex.id, safe='')}/evaluate",
            status_code=303,
        )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/reports/after-action.md")
def download_after_action_report(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    _, events, chaos_state, intelligence = _exercise_evidence(ex)
    report = render_evidence_markdown(
        ex,
        intelligence,
        events,
        chaos_state,
    )
    report_path = exercise_package_path(
        ex,
        "reports",
        "after_action_report.md",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    return Response(
        report,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ex.id}-after-action.md"'
            )
        },
    )


@app.get("/exercises/{exercise_id}/reports/evidence.zip")
def download_evidence_package(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    _, events, chaos_state, intelligence = _exercise_evidence(ex)
    try:
        signing_key = load_or_create_signing_key(
            settings.evidence_signing_key_path
        )
        archive = build_evidence_archive(
            ex,
            intelligence,
            events,
            chaos_state,
            signing_key=signing_key,
        )
        save_evidence_archive(
            ex,
            archive,
            retention_days=settings.evidence_retention_days,
            retention_count=settings.evidence_retention_count,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("Evidence export failed: %s", type(exc).__name__)
        raise HTTPException(503, "Evidence signing or storage is unavailable") from exc
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ex.id}-evidence.zip"'
            ),
            "X-LiveFire-Evidence-Key-ID": signing_key_id(signing_key),
        },
    )


@app.get("/exercises/{exercise_id}/reports/evidence/{filename}")
def download_retained_evidence_package(exercise_id: str, filename: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        signing_key = load_signing_key(settings.evidence_signing_key_path)
        archive = read_retained_archive(ex, filename, signing_key)
    except (EvidenceVerificationError, ValueError) as exc:
        raise HTTPException(409, "Evidence archive verification failed") from exc
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.post("/exercises/{exercise_id}/playbooks")
async def save_exercise_playbook(
    request: Request,
    exercise_id: str,
):
    playbook_yaml = _field(
        await _form_fields(request, maximum_bytes=96 * 1024),
        "playbook_yaml",
    )
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook = save_playbook_configuration(ex, playbook_yaml)
    except ValueError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_saved",
        f"Playbook Saved: {playbook['name']}",
        f"ID: {playbook['id']}\nStages: {len(playbook['stages'])}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/designer/validate")
def validate_designer_playbook(
    exercise_id: str,
    playbook: dict = Body(...),
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        normalized = validate_playbook_configuration(ex, playbook)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"valid": True, "playbook": normalized})


@app.post("/exercises/{exercise_id}/playbooks/designer/save")
def save_designer_playbook(
    exercise_id: str,
    playbook: dict = Body(...),
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        normalized = save_playbook_configuration(ex, playbook)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_saved",
        f"Playbook Saved: {normalized['name']}",
        (
            f"ID: {normalized['id']}\n"
            f"Stages: {len(normalized['stages'])}\n"
            "Source: visual designer"
        ),
    )
    return JSONResponse({"saved": True, "playbook": normalized})


@app.post("/exercises/{exercise_id}/playbooks/{playbook_id}/clone")
async def clone_exercise_playbook(
    request: Request,
    exercise_id: str,
    playbook_id: str,
):
    fields = await _form_fields(request)
    new_playbook_id = _field(fields, "new_playbook_id")
    new_name = _field(fields, "new_name")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        clone = clone_playbook_configuration(
            ex,
            playbook_id,
            new_playbook_id,
            new_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_cloned",
        f"Playbook Cloned: {clone['name']}",
        f"Source: {playbook_id}\nClone: {clone['id']}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/import")
async def import_exercise_playbook(
    request: Request,
    exercise_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type not in {"application/yaml", "text/yaml", "text/plain"}:
        raise HTTPException(415, "Playbook import must use a YAML content type")
    filename = request.headers.get("x-livefire-filename", "imported-playbook.yml")
    if len(filename) > 120 or not filename.lower().endswith((".yml", ".yaml")):
        raise HTTPException(400, "Playbook filename must end in .yml or .yaml")
    content = await request.body()
    if len(content) > 64 * 1024:
        raise HTTPException(400, "Playbook configuration is too large")
    try:
        configuration = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Playbook must use UTF-8 encoding") from exc
    try:
        playbook = save_playbook_configuration(ex, configuration)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_imported",
        f"Playbook Imported: {playbook['name']}",
        f"File: {filename}\nID: {playbook['id']}",
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/playbooks/{playbook_id}/export.yml")
def export_exercise_playbook(exercise_id: str, playbook_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        configuration = export_playbook_configuration(ex, playbook_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        configuration,
        media_type="application/yaml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{playbook_id}.yml"'
            )
        },
    )


@app.post(
    "/exercises/{exercise_id}/playbooks/{playbook_id}"
    "/versions/{version_id}/restore"
)
def restore_exercise_playbook_version(
    exercise_id: str,
    playbook_id: str,
    version_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook = restore_playbook_version(
            ex,
            playbook_id,
            version_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_restored",
        f"Playbook Restored: {playbook['name']}",
        f"Version: {version_id}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/{playbook_id}/start")
def start_exercise_playbook(exercise_id: str, playbook_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook_run = start_chaos_playbook(ex, playbook_id)
    except ChaosPreflightError as exc:
        add_event(ex.id, "playbook_start_failed", "Playbook Start Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "playbook_start_failed", "Playbook Start Failed", str(exc))
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_started",
        f"Playbook Started: {playbook_run['name']}",
        f"Run: {playbook_run['id']}\nSeed: {playbook_run['seed']}",
    )
    return _redirect_to_exercise(ex)


@app.post(
    "/exercises/{exercise_id}/playbook-runs/{playbook_run_id}/{command}"
)
def control_exercise_playbook(
    exercise_id: str,
    playbook_run_id: str,
    command: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = control_chaos_playbook_run(
            ex,
            playbook_run_id,
            command,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        f"playbook_{command}",
        f"Playbook {command.title()}",
        f"Run: {result['id']}\nStatus: {result['status']}",
    )
    return _redirect_to_exercise(ex)


@app.post(
    "/exercises/{exercise_id}/playbook-runs/{playbook_run_id}"
    "/stages/{stage_id}/skip"
)
def skip_exercise_playbook_stage(
    exercise_id: str,
    playbook_run_id: str,
    stage_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        stage = skip_chaos_playbook_stage(
            ex,
            playbook_run_id,
            stage_id,
        )
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_stage_skipped",
        f"Playbook Stage Skipped: {stage['title']}",
        f"Run: {playbook_run_id}\nStage: {stage_id}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/artifacts")
async def create_exercise_artifact(
    request: Request,
    exercise_id: str,
):
    fields = await _form_fields(request)
    title = _field(fields, "title")
    audience = _field(fields, "audience")
    stage = _field(fields, "stage")
    artifact_kind = _field(fields, "artifact_kind")
    content = _field(fields, "content")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        inject = create_safe_artifact_inject(
            ex,
            title,
            audience,
            stage,
            artifact_kind,
            content,
        )
    except PackagePathError:
        raise
    except OSError as exc:
        LOGGER.warning("Failed to write a safe exercise artifact")
        raise HTTPException(500, "Exercise artifact could not be written") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    save_injects([inject])
    add_event(
        ex.id,
        "artifact_created",
        f"Safe Artifact Created: {inject.title}",
        (
            f"Type: {artifact_kind}\n"
            f"Stage: {stage}\n"
            f"Path: {inject.payload['artifact']}"
        ),
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/events")
async def add_manual_event(request: Request, exercise_id: str):
    fields = await _form_fields(request)
    title = _field(fields, "title").strip()
    detail = _field(fields, "detail").strip()
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if not title or len(title) > 120:
        raise HTTPException(400, "Event title must be between 1 and 120 characters")
    if not detail or len(detail) > 5000:
        raise HTTPException(400, "Event detail must be between 1 and 5000 characters")
    add_event(exercise_id, "manual_note", title, detail)
    if request.query_params.get("view") == "evaluate":
        return RedirectResponse(
            url=f"/exercises/{quote(ex.id, safe='')}/evaluate",
            status_code=303,
        )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/download")
def download_exercise(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    archive = build_exercise_archive(ex)
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ex.id}.zip"',
        },
    )
