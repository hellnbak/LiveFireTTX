from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, quote
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.models import (
    add_event,
    get_exercise,
    get_injects,
    get_scenario_pack,
    list_checkpoints,
    list_organization_profiles,
    list_scenario_packs,
    save_exercise,
    save_injects,
)
from app.services.operations import seed_default_checkpoints
from app.services.scenario_library import (
    PACK_MEDIA_TYPE,
    PROFILE_MEDIA_TYPE,
    capture_exercise_as_pack,
    create_organization_profile,
    create_pack_checkpoints,
    export_scenario_pack,
    import_scenario_pack,
    instantiate_scenario_pack,
    latest_organization_profiles,
    latest_scenario_packs,
    organization_profile_payload,
)
from app.version import __version__


router = APIRouter(tags=["design-library"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)
templates.env.globals["app_version"] = __version__


@router.get("/library", response_class=HTMLResponse)
def design_library(request: Request):
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "packs": latest_scenario_packs(),
            "pack_versions": list_scenario_packs(),
            "profiles": latest_organization_profiles(),
            "profile_versions": list_organization_profiles(),
        },
    )


@router.post("/library/packs/import")
async def import_pack(request: Request):
    fields = await _form_fields(request, maximum_bytes=512 * 1024)
    try:
        pack = import_scenario_pack(fields.get("pack_json", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(
        f"/library#pack-{quote(pack.id, safe='')}",
        status_code=303,
    )


@router.get("/library/packs/{pack_id}/export.json")
def export_pack(pack_id: str):
    pack = get_scenario_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Scenario pack not found")
    return Response(
        export_scenario_pack(pack),
        media_type=PACK_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{pack.slug}-{pack.version}.livefire.json"'
            )
        },
    )


@router.post("/library/packs/{pack_id}/exercises")
async def create_exercise_from_pack(request: Request, pack_id: str):
    pack = get_scenario_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Scenario pack not found")
    fields = await _form_fields(request)
    profile_id = fields.get("organization_profile_id") or None
    try:
        exercise, injects = instantiate_scenario_pack(
            pack,
            exercise_name=fields.get("exercise_name", ""),
            organization_profile_id=profile_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    save_exercise(exercise)
    save_injects(injects)
    if create_pack_checkpoints(pack, exercise) == 0:
        seed_default_checkpoints(exercise)
    add_event(
        exercise.id,
        "exercise_created_from_pack",
        "Exercise Created from Scenario Pack",
        f"Pack: {pack.name} {pack.version}\nChecksum: {pack.checksum}",
    )
    return RedirectResponse(
        f"/exercises/{quote(exercise.id, safe='')}",
        status_code=303,
    )


@router.post("/exercises/{exercise_id}/scenario-pack")
async def capture_exercise_pack(request: Request, exercise_id: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    fields = await _form_fields(request)
    try:
        pack = capture_exercise_as_pack(
            exercise,
            get_injects(exercise.id),
            list_checkpoints(exercise.id),
            slug=fields.get("slug", ""),
            name=fields.get("name", ""),
            version=fields.get("version", ""),
            description=fields.get("description", ""),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        exercise.id,
        "scenario_pack_captured",
        "Scenario Pack Captured",
        f"Pack: {pack.name} {pack.version}\nChecksum: {pack.checksum}",
    )
    return RedirectResponse(
        f"/library#pack-{quote(pack.id, safe='')}",
        status_code=303,
    )


@router.post("/library/profiles")
async def add_organization_profile(request: Request):
    fields = await _form_fields(request)
    participants = [
        item.strip()
        for item in fields.get("participants", "").split(",")
        if item.strip()
    ]
    objectives = [
        item.strip()
        for item in fields.get("objectives", "").splitlines()
        if item.strip()
    ]
    try:
        profile = create_organization_profile(
            slug=fields.get("slug", ""),
            name=fields.get("name", ""),
            version=fields.get("version", ""),
            description=fields.get("description", ""),
            business_system=fields.get("business_system", ""),
            participants=participants,
            objectives=objectives,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse(
        f"/library#profile-{quote(profile.id, safe='')}",
        status_code=303,
    )


@router.get("/library/profiles/{profile_id}/export.json")
def export_organization_profile(profile_id: str):
    profile = next(
        (
            item
            for item in list_organization_profiles()
            if item.id == profile_id
        ),
        None,
    )
    if not profile:
        raise HTTPException(404, "Organization profile not found")
    return Response(
        json.dumps(organization_profile_payload(profile), indent=2, sort_keys=True)
        + "\n",
        media_type=PROFILE_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{profile.slug}-{profile.version}.organization.json"'
            )
        },
    )


async def _form_fields(
    request: Request,
    *,
    maximum_bytes: int = 96 * 1024,
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
            max_num_fields=30,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Form submission is invalid") from exc
    return {key: values[-1] for key, values in parsed.items() if values}
