from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
from typing import Any
import base64
import hmac
import re
import secrets
import sqlite3

from app.models import connect, new_id, timestamp


AUTH_COOKIE_NAME = "livefire_session"
PASSWORD_ITERATIONS = 310000
PASSWORD_PATTERN = re.compile(r"[a-z][a-z0-9._-]{2,63}")
ROLES = {"admin", "facilitator", "evaluator", "participant"}
ROLE_CAPABILITIES = {
    "admin": {"admin", "design", "facilitate", "evaluate", "participate"},
    "facilitator": {"design", "facilitate", "evaluate", "participate"},
    "evaluator": {"evaluate", "participate"},
    "participant": {"participate"},
}


@dataclass(frozen=True)
class AuthUser:
    id: str
    username: str
    display_name: str
    role: str
    active: bool
    created_at: str

    def can(self, capability: str) -> bool:
        return capability in ROLE_CAPABILITIES.get(self.role, set())


LOCAL_ADMIN = AuthUser(
    id="local",
    username="local",
    display_name="Local Administrator",
    role="admin",
    active=True,
    created_at="",
)


def seed_bootstrap_admin(
    *,
    shared_mode: bool,
    username: str,
    password: str | None,
) -> AuthUser | None:
    if not shared_mode:
        return None
    if list_users():
        return None
    if password is None:
        raise RuntimeError(
            "LIVEFIRE_BOOTSTRAP_ADMIN_PASSWORD is required for the first shared-mode start"
        )
    return create_user(
        username=username,
        display_name="LiveFireTTX Administrator",
        role="admin",
        password=password,
    )


def create_user(
    *,
    username: str,
    display_name: str,
    role: str,
    password: str,
) -> AuthUser:
    normalized_username = _username(username)
    normalized_display_name = _single_line(display_name, "Display name", 120)
    if role not in ROLES:
        raise ValueError("Unknown account role")
    password_hash = hash_password(password)
    user = AuthUser(
        id=new_id("usr"),
        username=normalized_username,
        display_name=normalized_display_name,
        role=role,
        active=True,
        created_at=timestamp(),
    )
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id,
                    username,
                    display_name,
                    role,
                    password_hash,
                    active,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username,
                    user.display_name,
                    user.role,
                    password_hash,
                    1,
                    user.created_at,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username already exists") from exc
    return user


def list_users() -> list[AuthUser]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return [_row_to_user(row) for row in rows]


def get_user(user_id: str) -> AuthUser | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def authenticate(username: str, password: str) -> AuthUser | None:
    normalized_username = username.strip().lower()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            (normalized_username,),
        ).fetchone()
    if not row:
        _derive_password(password[:1024], bytes(16), PASSWORD_ITERATIONS)
        return None
    if not bool(row["active"]) or not verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def create_session(user: AuthUser, ttl_minutes: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    created = datetime.now(timezone.utc)
    expires = created + timedelta(minutes=ttl_minutes)
    with connect() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (created.isoformat(),))
        conn.execute(
            """
            INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user.id, created.isoformat(), expires.isoformat()),
        )
        conn.commit()
    return token


def resolve_session(token: str | None) -> AuthUser | None:
    if not token or len(token) > 256:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ?
              AND auth_sessions.expires_at > ?
              AND users.active = 1
            """,
            (_token_hash(token), timestamp()),
        ).fetchone()
    return _row_to_user(row) if row else None


def revoke_session(token: str | None) -> None:
    if not token or len(token) > 256:
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ?",
            (_token_hash(token),),
        )
        conn.commit()


def update_password(user_id: str, password: str) -> bool:
    password_hash = hash_password(password)
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    return cursor.rowcount == 1


def set_user_active(user_id: str, active: bool) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    if user.role == "admin" and user.active and not active:
        active_admins = [item for item in list_users() if item.role == "admin" and item.active]
        if len(active_admins) <= 1:
            raise ValueError("The last active administrator cannot be disabled")
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET active = ? WHERE id = ?",
            (1 if active else 0, user_id),
        )
        if not active:
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
    return cursor.rowcount == 1


def hash_password(password: str) -> str:
    _validate_password(password)
    salt = secrets.token_bytes(16)
    digest = _derive_password(password, salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        _encode(salt),
        _encode(digest),
    )


def verify_password(password: str, encoded: str) -> bool:
    if not 1 <= len(password) <= 1024:
        return False
    try:
        algorithm, iterations_value, salt_value, digest_value = encoded.split("$", 3)
        iterations = int(iterations_value)
        salt = _decode(salt_value)
        expected = _decode(digest_value)
    except (TypeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256" or not 100000 <= iterations <= 1000000:
        return False
    candidate = _derive_password(password, salt, iterations)
    return hmac.compare_digest(candidate, expected)


def required_capability(method: str, path: str) -> str | None:
    if path in {"/healthz", "/readyz", "/login"} or path.startswith("/static/"):
        return None
    if path.startswith("/admin/") or path == "/admin":
        return "admin"
    if path.startswith("/library") or path == "/new":
        return "design"
    if re.fullmatch(
        r"/exercises/ttx_[a-f0-9]{12}/scenario-pack",
        path,
    ):
        return "design"
    if method == "POST" and path == "/exercises":
        return "design"
    if path == "/logout":
        return None
    if path == "/":
        return "participate"
    if method == "GET" and re.fullmatch(
        r"/exercises/ttx_[a-f0-9]{12}/present(?:/status)?",
        path,
    ):
        return "participate"
    if method == "GET" and re.fullmatch(
        r"/exercises/ttx_[a-f0-9]{12}/participants/[a-z0-9.-]+",
        path,
    ):
        return "participate"
    evaluator_patterns = (
        r"/exercises/ttx_[a-f0-9]{12}/evaluate",
        (
            r"/exercises/ttx_[a-f0-9]{12}/reports/(?:after-action\.md|evidence\.zip|"
            r"evidence/evidence-[0-9]{8}T[0-9]{12}Z-[a-f0-9]{8}\.zip)"
        ),
        r"/exercises/ttx_[a-f0-9]{12}/objectives/[0-9]+",
        r"/exercises/ttx_[a-f0-9]{12}/improvements",
        r"/improvements/imp_[a-f0-9]{12}/status/[a-z_]+",
        r"/exercises/ttx_[a-f0-9]{12}/events",
        r"/checkpoints/chk_[a-f0-9]{12}/complete",
    )
    if any(re.fullmatch(pattern, path) for pattern in evaluator_patterns):
        return "evaluate"
    return "facilitate"


def _row_to_user(row: Any) -> AuthUser:
    return AuthUser(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


def _derive_password(password: str, salt: bytes, iterations: int) -> bytes:
    return pbkdf2_hmac("sha256", password.encode(), salt, iterations)


def _token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _username(value: str) -> str:
    normalized = value.strip().lower()
    if not PASSWORD_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Username must use 3 to 64 lowercase letters, numbers, dots, dashes, or underscores"
        )
    return normalized


def _single_line(value: str, label: str, maximum: int) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or "\n" in normalized
        or "\r" in normalized
    ):
        raise ValueError(f"{label} must be between 1 and {maximum} characters")
    return normalized


def _validate_password(password: str) -> None:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Password must be between 12 and 1024 characters")
