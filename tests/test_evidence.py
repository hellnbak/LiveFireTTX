from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import stat

from app import models
from app.models import Exercise
from app.services.evidence import (
    EvidenceVerificationError,
    build_signed_archive,
    list_evidence_archives,
    load_or_create_signing_key,
    load_signing_key,
    save_evidence_archive,
    signing_key_id,
    verify_evidence_archive,
)


class EvidenceArchiveTests(TestCase):
    def test_creates_key_and_verifies_manifest_and_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path = root / "keys" / "evidence.key"
            key = load_or_create_signing_key(key_path)
            self.assertEqual(key, load_signing_key(key_path))
            self.assertEqual(32, len(key))
            self.assertEqual(16, len(signing_key_id(key)))

            payload = self.archive(key)
            archive_path = root / "evidence.zip"
            archive_path.write_bytes(payload)
            result = verify_evidence_archive(archive_path, key)

            self.assertTrue(result["valid"])
            self.assertEqual("ttx_evidence", result["exercise_id"])
            self.assertEqual(2, result["file_count"])

    def test_rejects_tampered_and_undeclared_evidence(self) -> None:
        key = b"v" * 32
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = BytesIO(self.archive(key))
            tampered = BytesIO()
            with ZipFile(original) as source, ZipFile(
                tampered,
                "w",
                ZIP_DEFLATED,
            ) as destination:
                for member in source.infolist():
                    content = source.read(member.filename)
                    if member.filename == "events.csv":
                        content += b"tampered"
                    destination.writestr(member, content)
                destination.writestr("extra.txt", b"undeclared")
            archive_path = root / "tampered.zip"
            archive_path.write_bytes(tampered.getvalue())

            with self.assertRaises(EvidenceVerificationError):
                verify_evidence_archive(archive_path, key)

    def test_rejects_unsafe_names_and_symbolic_links(self) -> None:
        key = b"s" * 32
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for filename, configure in [
                ("unsafe.zip", lambda archive: archive.writestr("../outside", b"x")),
                ("symlink.zip", self._write_symlink),
            ]:
                archive_path = root / filename
                with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
                    configure(archive)
                with self.subTest(filename=filename):
                    with self.assertRaises(EvidenceVerificationError):
                        verify_evidence_archive(archive_path, key)

    def test_retention_prunes_old_and_excess_archives(self) -> None:
        key = b"r" * 32
        exercise = self.exercise()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(models, "GENERATED_ROOT", root / "exercises"):
                start = datetime(2026, 1, 1, tzinfo=timezone.utc)
                for offset in range(3):
                    save_evidence_archive(
                        exercise,
                        self.archive(key),
                        retention_days=30,
                        retention_count=2,
                        now=start + timedelta(hours=offset),
                    )
                records = list_evidence_archives(exercise, key)
                self.assertEqual(2, len(records))
                self.assertTrue(all(record.valid for record in records))

                save_evidence_archive(
                    exercise,
                    self.archive(key),
                    retention_days=1,
                    retention_count=2,
                    now=start + timedelta(days=10),
                )
                records = list_evidence_archives(exercise, key)
                self.assertEqual(1, len(records))

    def archive(self, key: bytes) -> bytes:
        return build_signed_archive(
            exercise=self.exercise(),
            exercise_clock={"status": "completed", "elapsed_seconds": 3600},
            files={
                "after_action_report.md": b"# Evidence\n",
                "events.csv": b"created_at,event_type\n",
            },
            signing_key=key,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def _write_symlink(self, archive: ZipFile) -> None:
        member = ZipInfo("linked-evidence")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "manifest.json")

    def exercise(self) -> Exercise:
        return Exercise(
            id="ttx_evidence",
            name="Evidence Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=60,
            participants=["Incident Commander"],
            objectives=["Assess impact"],
            status="completed",
            created_at="2026-01-01T00:00:00Z",
            package_path="/tmp/ttx_evidence",
        )
