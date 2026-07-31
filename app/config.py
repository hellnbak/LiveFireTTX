from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import os
import re


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


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    parsed = _positive_int(name, default)
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
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


def _allowed_hosts() -> tuple[str, ...]:
    raw = os.environ.get(
        "LIVEFIRE_ALLOWED_HOSTS",
        "127.0.0.1,localhost,[::1],testserver",
    )
    hosts = tuple(dict.fromkeys(item.strip().lower() for item in raw.split(",")))
    if not hosts or any(not item for item in hosts):
        raise ValueError("LIVEFIRE_ALLOWED_HOSTS must contain at least one host")
    pattern = re.compile(
        r"(?:\[::1\]|localhost|testserver|127\.0\.0\.1|"
        r"(?:\*\.)?[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?)"
    )
    if any(not pattern.fullmatch(item) for item in hosts):
        raise ValueError("LIVEFIRE_ALLOWED_HOSTS contains an invalid host")
    return hosts


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
    lab_controls_enabled: bool
    lab_command_timeout_seconds: int
    shared_mode: bool
    allowed_hosts: tuple[str, ...]
    session_ttl_minutes: int
    secure_cookies: bool
    bootstrap_admin_username: str
    bootstrap_admin_password: str | None
    evidence_signing_key_path: Path
    evidence_retention_days: int
    evidence_retention_count: int


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
    evidence_signing_key_path = _path_from_env(
        "LIVEFIRE_EVIDENCE_SIGNING_KEY_PATH",
        data_root / "evidence-signing.key",
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
    shared_mode = _boolean("LIVEFIRE_SHARED_MODE", False)
    allowed_hosts = _allowed_hosts()
    local_hosts = {"127.0.0.1", "localhost", "[::1]", "testserver"}
    if not shared_mode and any(host not in local_hosts for host in allowed_hosts):
        raise ValueError("Non-loopback allowed hosts require LIVEFIRE_SHARED_MODE=true")
    bootstrap_admin_username = os.environ.get(
        "LIVEFIRE_BOOTSTRAP_ADMIN_USERNAME",
        "admin",
    ).strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9._-]{2,63}", bootstrap_admin_username):
        raise ValueError("LIVEFIRE_BOOTSTRAP_ADMIN_USERNAME is invalid")
    bootstrap_admin_password = (
        os.environ.get("LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD") or None
    )
    if bootstrap_admin_password is not None and not 12 <= len(
        bootstrap_admin_password
    ) <= 1024:
        raise ValueError(
            "LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD must be 12 to 1024 characters"
        )
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
        lab_controls_enabled=_boolean("LIVEFIRE_LAB_CONTROLS_ENABLED", True),
        lab_command_timeout_seconds=_positive_int(
            "LIVEFIRE_LAB_COMMAND_TIMEOUT_SECONDS",
            180,
        ),
        shared_mode=shared_mode,
        allowed_hosts=allowed_hosts,
        session_ttl_minutes=_positive_int(
            "LIVEFIRE_SESSION_TTL_MINUTES",
            480,
        ),
        secure_cookies=_boolean("LIVEFIRE_SECURE_COOKIES", shared_mode),
        bootstrap_admin_username=bootstrap_admin_username,
        bootstrap_admin_password=bootstrap_admin_password,
        evidence_signing_key_path=evidence_signing_key_path,
        evidence_retention_days=_bounded_int(
            "LIVEFIRE_EVIDENCE_RETENTION_DAYS",
            365,
            1,
            36500,
        ),
        evidence_retention_count=_bounded_int(
            "LIVEFIRE_EVIDENCE_RETENTION_COUNT",
            25,
            1,
            10000,
        ),
    )


settings = load_settings()
