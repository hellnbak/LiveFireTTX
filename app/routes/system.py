from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.models import database_health
from app.services.backups import build_backup_archive
from app.version import __version__


router = APIRouter(tags=["system"])
LOGGER = logging.getLogger("livefirettx.system")


@router.get("/healthz")
def health() -> dict[str, object]:
    return {"healthy": True, "version": __version__}


@router.get("/readyz")
def readiness() -> JSONResponse:
    database = database_health()
    generated_ready = True
    try:
        settings.generated_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        LOGGER.warning(
            "Generated package storage check failed (%s)",
            type(exc).__name__,
        )
        generated_ready = False
    database_status: dict[str, object] = {
        "healthy": bool(database.get("healthy")),
        "schema_version": int(database.get("schema_version", 0)),
    }
    if not database_status["healthy"]:
        database_status["error"] = "Database health check failed"
    ready = bool(database_status["healthy"]) and generated_ready
    return JSONResponse(
        {
            "ready": ready,
            "version": __version__,
            "database": database_status,
            "generated_storage_ready": generated_ready,
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
