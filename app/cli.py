from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

from app.config import settings
from app.models import database_health, init_db
from app.services.backups import read_backup_manifest, restore_backup, write_backup
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
    else:
        if not args.confirm:
            parser.error("restore requires --confirm")
        result = restore_backup(Path(args.archive))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
