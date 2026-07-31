# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import (
    ExerciseCreate,
    SCENARIO_LIBRARY,
    add_event,
    get_exercise,
    get_inject,
    get_injects,
    init_db,
    list_events,
    list_exercises,
    mark_inject_triggered,
    save_exercise,
    save_injects,
)
from app.services.generator import create_exercise_from_request
from app.services.runtime import (
    ChaosExecutionError,
    ChaosPreflightError,
    emergency_stop,
    read_chaos_state,
    read_control_status,
    reset_chaos,
    run_chaos_inject,
)
from app.version import __version__

BASE = Path(__file__).resolve().parent
app = FastAPI(title="LiveFireTTX", version=__version__)
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["app_version"] = __version__
app.mount("/static", StaticFiles(directory=str(BASE / "templates" / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "exercises": list_exercises(), "scenarios": SCENARIO_LIBRARY})


@app.get("/new", response_class=HTMLResponse)
def new_exercise(request: Request):
    return templates.TemplateResponse("new.html", {"request": request, "scenarios": SCENARIO_LIBRARY})


@app.post("/exercises")
def create_exercise(
    name: str = Form(...),
    scenario_type: str = Form(...),
    platform: str = Form("local_docker"),
    business_system: str = Form("Order Processing"),
    difficulty: str = Form("intermediate"),
    duration_minutes: int = Form(90),
    participants: str = Form("Incident Commander, Security Operations, Cloud/IT Operations, Communications, Business Owner"),
    objectives: str = Form(""),
):
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
    ex, injects = create_exercise_from_request(req)
    save_exercise(ex)
    save_injects(injects)
    add_event(ex.id, "exercise_created", "Exercise Created", f"Generated package at {ex.package_path}")
    return RedirectResponse(f"/exercises/{ex.id}", status_code=303)


@app.get("/exercises/{exercise_id}", response_class=HTMLResponse)
def exercise_detail(request: Request, exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    injects = get_injects(exercise_id)
    events = list_events(exercise_id)
    by_stage = {}
    for i in injects:
        by_stage.setdefault(i.stage, []).append(i)
    return templates.TemplateResponse(
        "exercise.html",
        {
            "request": request,
            "exercise": ex,
            "injects_by_stage": by_stage,
            "events": events,
            "chaos_state": read_chaos_state(ex),
            "control_status": read_control_status(ex),
        },
    )


@app.post("/injects/{inject_id}/trigger")
def trigger_inject(
    inject_id: str,
    intensity: str = Form("medium"),
    duration_seconds: int = Form(300),
    guardrail_profile: str = Form("standard"),
):
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

    mark_inject_triggered(inject_id)
    detail = f"Audience: {inj.audience}\nAction: {inj.action_type}"
    if inj.action_type == "chaos_script":
        detail += (
            f"\nIntensity: {intensity}"
            f"\nDuration: {duration_seconds} seconds"
            f"\nGuardrails: {guardrail_profile}"
        )
    add_event(ex.id, "inject_triggered", inj.title, f"{detail}\n{result}")
    return RedirectResponse(f"/exercises/{inj.exercise_id}", status_code=303)


@app.post("/exercises/{exercise_id}/chaos/reset")
def reset_exercise_chaos(exercise_id: str, action: str = Form("")):
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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.post("/exercises/{exercise_id}/chaos/emergency-stop")
def emergency_stop_exercise_chaos(exercise_id: str):
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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.post("/exercises/{exercise_id}/events")
def add_manual_event(exercise_id: str, title: str = Form(...), detail: str = Form(...)):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    add_event(exercise_id, "manual_note", title, detail)
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.get("/exercises/{exercise_id}/download")
def download_exercise(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    import shutil
    archive = shutil.make_archive(str(Path(ex.package_path)), "zip", root_dir=ex.package_path)
    return FileResponse(archive, filename=f"{exercise_id}.zip", media_type="application/zip")
