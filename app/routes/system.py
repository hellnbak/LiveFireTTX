from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.models import database_health
from app.services.backups import build_backup_archive
from app.version import __version__


router = APIRouter(tags=["system"])


@router.get("/healthz")
def health() -> dict[str, object]:
    return {"healthy": True, "version": __version__}


@router.get("/readyz")
def readiness() -> JSONResponse:
    database = database_health()
    generated_error = None
    try:
        settings.generated_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        generated_error = str(exc)
    ready = bool(database.get("healthy")) and generated_error is None
    return JSONResponse(
        {
            "ready": ready,
            "version": __version__,
            "database": database,
            "generated_root": str(settings.generated_root),
            "generated_root_error": generated_error,
        },
        status_code=200 if ready else 503,
    )


@router.get("/admin/backup.zip")
def download_application_backup() -> Response:
    archive = build_backup_archive()
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="livefirettx-backup-{label}.zip"'
            )
        },
    )
