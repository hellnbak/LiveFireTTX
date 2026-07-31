from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import os


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def _positive_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _boolean(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    data_root: Path
    database_path: Path
    generated_root: Path
    control_url: str
    request_timeout_seconds: int
    backup_root: Path
    allow_container_host: bool
    scheduler_enabled: bool
    scheduler_interval_seconds: int


def load_settings() -> Settings:
    data_root = _path_from_env(
        "LIVEFIRE_DATA_ROOT",
        Path.home() / ".livefirettx",
    )
    database_path = _path_from_env(
        "LIVEFIRE_DATABASE_PATH",
        data_root / "livefirettx.db",
    )
    generated_root = _path_from_env(
        "LIVEFIRE_GENERATED_ROOT",
        data_root / "generated" / "exercises",
    )
    backup_root = _path_from_env(
        "LIVEFIRE_BACKUP_ROOT",
        data_root / "backups",
    )
    raw_control_url = os.environ.get(
        "LIVEFIRE_CONTROL_URL",
        "http://127.0.0.1:8090",
    )
    allow_container_host = _boolean("LIVEFIRE_ALLOW_CONTAINER_HOST")
    approved_control_hosts = {"127.0.0.1", "localhost", "::1"}
    if allow_container_host:
        approved_control_hosts.add("host.docker.internal")
    parsed_control_url = urlsplit(raw_control_url)
    try:
        parsed_control_url.port
    except ValueError as exc:
        raise ValueError("LIVEFIRE_CONTROL_URL has an invalid port") from exc
    if (
        parsed_control_url.scheme != "http"
        or parsed_control_url.hostname not in approved_control_hosts
        or parsed_control_url.username is not None
        or parsed_control_url.password is not None
        or parsed_control_url.path not in {"", "/"}
        or parsed_control_url.query
        or parsed_control_url.fragment
    ):
        raise ValueError(
            "LIVEFIRE_CONTROL_URL must be an approved local HTTP origin"
        )
    control_url = raw_control_url.rstrip("/")
    return Settings(
        data_root=data_root,
        database_path=database_path,
        generated_root=generated_root,
        control_url=control_url,
        request_timeout_seconds=_positive_int(
            "LIVEFIRE_REQUEST_TIMEOUT_SECONDS",
            3,
        ),
        backup_root=backup_root,
        allow_container_host=allow_container_host,
        scheduler_enabled=_boolean("LIVEFIRE_SCHEDULER_ENABLED", True),
        scheduler_interval_seconds=_positive_int(
            "LIVEFIRE_SCHEDULER_INTERVAL_SECONDS",
            2,
        ),
    )


settings = load_settings()
