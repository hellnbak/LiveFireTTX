from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json
import shutil
import sqlite3
import stat

from app.models import (
    DB_PATH,
    GENERATED_ROOT,
    SCHEMA_VERSION,
    database_schema_version,
    init_db,
)
from app.version import __version__


BACKUP_FORMAT_VERSION = 1
MAX_BACKUP_BYTES = 1024 * 1024 * 1024


def build_backup_archive(
    database_path: Path | None = None,
    generated_root: Path | None = None,
) -> bytes:
    database = (database_path or DB_PATH).resolve()
    exercises = (generated_root or GENERATED_ROOT).resolve()
    init_db()
    with TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "livefirettx.db"
        _backup_database(database, snapshot)
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "application_version": __version__,
            "database_schema_version": database_schema_version(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "exercise_count": _exercise_count(snapshot),
        }
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True),
            )
            archive.write(snapshot, "database/livefirettx.db")
            if exercises.exists():
                for path in sorted(exercises.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        archive.write(
                            path,
                            str(PurePosixPath("generated/exercises") / path.relative_to(exercises)),
                        )
        return output.getvalue()


def write_backup(
    destination: Path,
    database_path: Path | None = None,
    generated_root: Path | None = None,
) -> dict[str, Any]:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = build_backup_archive(database_path, generated_root)
    destination.write_bytes(archive)
    return {
        "path": str(destination),
        "size_bytes": len(archive),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def restore_backup(
    archive_path: Path,
    database_path: Path | None = None,
    generated_root: Path | None = None,
) -> dict[str, Any]:
    source = archive_path.expanduser().resolve()
    if not source.is_file():
        raise ValueError("Backup archive does not exist")
    if source.stat().st_size > MAX_BACKUP_BYTES:
        raise ValueError("Backup archive exceeds the supported size")
    database = (database_path or DB_PATH).resolve()
    exercises = (generated_root or GENERATED_ROOT).resolve()

    with TemporaryDirectory() as temporary:
        extracted = Path(temporary)
        with ZipFile(source) as archive:
            _validate_archive(archive)
            archive.extractall(extracted)
        manifest_path = extracted / "manifest.json"
        snapshot = extracted / "database" / "livefirettx.db"
        if not manifest_path.is_file() or not snapshot.is_file():
            raise ValueError("Backup archive is missing required files")
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("Unsupported backup format version")
        schema_version = int(manifest.get("database_schema_version", 0))
        if schema_version > SCHEMA_VERSION:
            raise ValueError("Backup requires a newer LiveFireTTX database schema")
        snapshot_schema_version = _validate_database(snapshot)
        if snapshot_schema_version != schema_version:
            raise ValueError("Backup manifest does not match the database schema")

        database.parent.mkdir(parents=True, exist_ok=True)
        restored_database = database.with_suffix(".restore.tmp")
        shutil.copy2(snapshot, restored_database)
        for sidecar in (
            Path(f"{database}-wal"),
            Path(f"{database}-shm"),
        ):
            sidecar.unlink(missing_ok=True)
        restored_database.replace(database)

        restored_exercises = extracted / "generated" / "exercises"
        if restored_exercises.exists():
            staged_exercises = exercises.with_name(f"{exercises.name}.restore.tmp")
            if staged_exercises.exists():
                shutil.rmtree(staged_exercises)
            shutil.copytree(restored_exercises, staged_exercises)
            if exercises.exists():
                shutil.rmtree(exercises)
            staged_exercises.replace(exercises)
        else:
            if exercises.exists():
                shutil.rmtree(exercises)
            exercises.mkdir(parents=True, exist_ok=True)

    init_db()
    return {
        "restored": True,
        "database_path": str(database),
        "generated_root": str(exercises),
        "schema_version": database_schema_version(),
    }


def read_backup_manifest(archive_path: Path) -> dict[str, Any]:
    with ZipFile(archive_path.expanduser().resolve()) as archive:
        _validate_archive(archive)
        try:
            return json.loads(archive.read("manifest.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Backup manifest is missing or invalid") from exc


def _backup_database(source: Path, destination: Path) -> None:
    source.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)
            tables = {
                row[0]
                for row in destination_connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "auth_sessions" in tables:
                destination_connection.execute("DELETE FROM auth_sessions")
                destination_connection.commit()
                destination_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _exercise_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT COUNT(*) FROM exercises").fetchone()
    return int(row[0]) if row else 0


def _validate_database(database: Path) -> int:
    try:
        with sqlite3.connect(database) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            connection.execute("SELECT COUNT(*) FROM exercises").fetchone()
            schema_row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Backup database is invalid") from exc
    if not result or result[0] != "ok":
        raise ValueError("Backup database failed its integrity check")
    schema_version = int(schema_row[0]) if schema_row else 0
    if schema_version > SCHEMA_VERSION:
        raise ValueError("Backup requires a newer LiveFireTTX database schema")
    return schema_version


def _validate_archive(archive: ZipFile) -> None:
    total_size = 0
    names: set[str] = set()
    for member in archive.infolist():
        _validate_member(member)
        if member.filename in names:
            raise ValueError("Backup contains duplicate archive entries")
        names.add(member.filename)
        total_size += member.file_size
        if total_size > MAX_BACKUP_BYTES:
            raise ValueError("Expanded backup exceeds the supported size")


def _validate_member(member: ZipInfo) -> None:
    path = PurePosixPath(member.filename)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Backup contains an unsafe path")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError("Backup contains an unsupported symbolic link")
