from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
import json
import sqlite3

from app import models
from app.services.backups import (
    build_backup_archive,
    read_backup_manifest,
    restore_backup,
)
from app.services.auth import create_session, create_user


class BackupTests(TestCase):
    def test_backup_excludes_active_authentication_sessions(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "livefirettx.db"
            with patch.object(models, "DB_PATH", database):
                models.init_db()
                user = create_user(
                    username="backup.admin",
                    display_name="Backup Admin",
                    role="admin",
                    password="backup-password-123",
                )
                create_session(user, 60)
                archive = BytesIO(
                    build_backup_archive(database, root / "missing")
                )
            with ZipFile(archive) as backup:
                snapshot = root / "snapshot.db"
                snapshot.write_bytes(backup.read("database/livefirettx.db"))
            with sqlite3.connect(snapshot) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM auth_sessions"
                ).fetchone()[0]
            self.assertEqual(0, count)

    def test_backup_and_restore_preserve_database_and_packages(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "livefirettx.db"
            generated = root / "generated" / "exercises"
            package = generated / "ttx_backup"
            package.mkdir(parents=True)
            (package / "exercise.yml").write_text("exercise: simulated\n")
            with patch.object(models, "DB_PATH", database):
                models.init_db()
                models.save_exercise(
                    models.Exercise(
                        id="ttx_backup",
                        name="Backup exercise",
                        scenario_type="dependency_cascade",
                        platform="local_docker",
                        business_system="Commerce",
                        difficulty="advanced",
                        duration_minutes=90,
                        participants=["Incident Commander"],
                        objectives=["Restore safely"],
                        status="created",
                        created_at="2026-01-01T00:00:00+00:00",
                        package_path=str(package),
                    )
                )
                archive_path = root / "backup.zip"
                archive_path.write_bytes(
                    build_backup_archive(database, generated)
                )
                manifest = read_backup_manifest(archive_path)
                self.assertEqual(1, manifest["format_version"])
                self.assertEqual(1, manifest["exercise_count"])

                database.unlink()
                (package / "exercise.yml").unlink()
                restore_backup(archive_path, database, generated)
                self.assertEqual("Backup exercise", models.get_exercise("ttx_backup").name)
                self.assertEqual(
                    "exercise: simulated\n",
                    (package / "exercise.yml").read_text(),
                )

    def test_restore_rejects_path_traversal(self) -> None:
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("../outside.txt", "unsafe")
        with TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "unsafe.zip"
            archive_path.write_bytes(output.getvalue())
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                restore_backup(archive_path)

    def test_restore_rejects_manifest_schema_mismatch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "livefirettx.db"
            with patch.object(models, "DB_PATH", database):
                models.init_db()
                original = BytesIO(build_backup_archive(database, root / "missing"))
            tampered = BytesIO()
            with (
                ZipFile(original) as source,
                ZipFile(tampered, "w", ZIP_DEFLATED) as destination,
            ):
                for member in source.infolist():
                    content = source.read(member.filename)
                    if member.filename == "manifest.json":
                        manifest = json.loads(content)
                        manifest["database_schema_version"] = 1
                        content = json.dumps(manifest).encode()
                    destination.writestr(member, content)
            archive_path = root / "tampered.zip"
            archive_path.write_bytes(tampered.getvalue())
            with self.assertRaisesRegex(ValueError, "does not match"):
                restore_backup(archive_path, database, root / "generated")

    def test_restore_without_packages_clears_stale_generated_content(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "livefirettx.db"
            generated = root / "generated" / "exercises"
            with patch.object(models, "DB_PATH", database):
                models.init_db()
                archive_path = root / "backup.zip"
                archive_path.write_bytes(
                    build_backup_archive(database, root / "missing")
                )
                generated.mkdir(parents=True)
                (generated / "stale.txt").write_text("remove me")
                Path(f"{database}-wal").write_text("stale")
                Path(f"{database}-shm").write_text("stale")
                restore_backup(archive_path, database, generated)
            self.assertEqual([], list(generated.iterdir()))
