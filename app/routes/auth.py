from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.auth import (
    AUTH_COOKIE_NAME,
    ROLES,
    authenticate,
    create_session,
    create_user,
    get_user,
    list_users,
    revoke_session,
    set_user_active,
    update_password,
)
from app.version import __version__


router = APIRouter(tags=["authentication"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)
templates.env.globals["app_version"] = __version__


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if not settings.shared_mode:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_path": _safe_next(next), "error": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request):
    fields = await _form_fields(request)
    username = fields.get("username", "")
    password = fields.get("password", "")
    next_path = _safe_next(fields.get("next", "/"))
    user = authenticate(username, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "next_path": next_path,
                "error": "Username or password is incorrect",
            },
            status_code=401,
        )
    token = create_session(user, settings.session_ttl_minutes)
    response = RedirectResponse(next_path, status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request):
    revoke_session(request.cookies.get(AUTH_COOKIE_NAME))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/admin/users", response_class=HTMLResponse)
def user_administration(request: Request):
    return templates.TemplateResponse(
        request,
        "users.html",
        {"users": list_users(), "roles": sorted(ROLES)},
    )


@router.post("/admin/users")
async def add_user(request: Request):
    fields = await _form_fields(request)
    try:
        create_user(
            username=fields.get("username", ""),
            display_name=fields.get("display_name", ""),
            role=fields.get("role", ""),
            password=fields.get("password", ""),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/password")
async def reset_user_password(request: Request, user_id: str):
    if not get_user(user_id):
        raise HTTPException(404, "User not found")
    fields = await _form_fields(request)
    try:
        updated = update_password(user_id, fields.get("password", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not updated:
        raise HTTPException(404, "User not found")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/status/{status}")
def change_user_status(user_id: str, status: str):
    if status not in {"active", "disabled"}:
        raise HTTPException(404, "Account status not found")
    try:
        updated = set_user_active(user_id, status == "active")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not updated:
        raise HTTPException(404, "User not found")
    return RedirectResponse("/admin/users", status_code=303)


async def _form_fields(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected URL-encoded form data")
    body = await request.body()
    if len(body) > 64 * 1024:
        raise HTTPException(413, "Form submission is too large")
    try:
        parsed = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=20,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Form submission is invalid") from exc
    return {key: values[-1] for key, values in parsed.items() if values}


def _safe_next(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
    ):
        return "/"
    return candidate
