from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

from app.config import settings
from app.models import database_health, init_db
from app.services.backups import read_backup_manifest, restore_backup, write_backup
from app.services.evidence import (
    existing_key_id,
    load_signing_key,
    verify_evidence_archive,
)
from app.version import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description="LiveFireTTX local administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Validate configuration and database health")

    backup = commands.add_parser("backup", help="Create a local backup archive")
    backup.add_argument(
        "destination",
        nargs="?",
        help="Destination ZIP path; defaults to LIVEFIRE_BACKUP_ROOT",
    )

    inspect = commands.add_parser("inspect-backup", help="Read a backup manifest")
    inspect.add_argument("archive")

    restore = commands.add_parser("restore", help="Restore a local backup archive")
    restore.add_argument("archive")
    restore.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm replacement of the local database and generated packages",
    )

    verify_evidence = commands.add_parser(
        "verify-evidence",
        help="Verify a signed evidence archive and all declared files",
    )
    verify_evidence.add_argument("archive")
    verify_evidence.add_argument(
        "--key-file",
        help="Signing key file; defaults to LIVEFIRE_EVIDENCE_SIGNING_KEY_PATH",
    )

    args = parser.parse_args()
    if args.command == "doctor":
        init_db()
        result = {
            "version": __version__,
            "data_root": str(settings.data_root),
            "database": database_health(),
            "generated_root": str(settings.generated_root),
            "control_url": settings.control_url,
            "allow_container_host": settings.allow_container_host,
            "shared_mode": settings.shared_mode,
            "allowed_hosts": settings.allowed_hosts,
            "secure_cookies": settings.secure_cookies,
            "evidence": {
                "signing_key_path": str(settings.evidence_signing_key_path),
                "signing_key_id": existing_key_id(
                    settings.evidence_signing_key_path
                ),
                "retention_days": settings.evidence_retention_days,
                "retention_count": settings.evidence_retention_count,
            },
        }
    elif args.command == "backup":
        destination = (
            Path(args.destination)
            if args.destination
            else settings.backup_root
            / (
                "livefirettx-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
            )
        )
        result = write_backup(destination)
    elif args.command == "inspect-backup":
        result = read_backup_manifest(Path(args.archive))
    elif args.command == "restore":
        if not args.confirm:
            parser.error("restore requires --confirm")
        result = restore_backup(Path(args.archive))
    else:
        key_path = (
            Path(args.key_file)
            if args.key_file
            else settings.evidence_signing_key_path
        )
        try:
            result = verify_evidence_archive(
                Path(args.archive),
                load_signing_key(key_path),
            )
        except ValueError as exc:
            parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
