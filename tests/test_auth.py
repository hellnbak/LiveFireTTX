from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.config import settings as default_settings
from app.main import app
from app.services.auth import (
    authenticate,
    create_session,
    create_user,
    required_capability,
    resolve_session,
    revoke_session,
    set_user_active,
)


class AuthenticationTests(TestCase):
    def test_password_sessions_and_last_admin_protection(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(
                models,
                "DB_PATH",
                Path(temporary) / "livefirettx.db",
            ):
                models.init_db()
                admin = create_user(
                    username="exercise.admin",
                    display_name="Exercise Admin",
                    role="admin",
                    password="correct-horse-battery-staple",
                )
                self.assertIsNone(authenticate("exercise.admin", "wrong-password"))
                authenticated = authenticate(
                    "exercise.admin",
                    "correct-horse-battery-staple",
                )
                self.assertEqual(admin.id, authenticated.id)
                token = create_session(admin, 60)
                self.assertEqual(admin.id, resolve_session(token).id)
                revoke_session(token)
                self.assertIsNone(resolve_session(token))
                with self.assertRaisesRegex(ValueError, "last active"):
                    set_user_active(admin.id, False)

    def test_shared_mode_enforces_role_permissions(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            shared_settings = replace(
                default_settings,
                shared_mode=True,
                scheduler_enabled=False,
                lab_controls_enabled=False,
                bootstrap_admin_username="admin",
                bootstrap_admin_password="bootstrap-password-123",
                secure_cookies=False,
            )
            with (
                patch.object(models, "DB_PATH", root / "livefirettx.db"),
                patch.object(models, "GENERATED_ROOT", root / "exercises"),
                patch("app.main.settings", shared_settings),
                patch("app.routes.auth.settings", shared_settings),
                patch(
                    "app.services.generator.GENERATED_ROOT",
                    root / "exercises",
                ),
            ):
                with TestClient(app) as client:
                    anonymous = client.get(
                        "/",
                        headers={"accept": "text/html"},
                        follow_redirects=False,
                    )
                    self.assertEqual(303, anonymous.status_code)
                    self.assertTrue(anonymous.headers["location"].startswith("/login"))

                    failed = client.post(
                        "/login",
                        data={"username": "admin", "password": "incorrect"},
                    )
                    self.assertEqual(401, failed.status_code)
                    self.assertIn("incorrect", failed.text.lower())

                    logged_in = client.post(
                        "/login",
                        data={
                            "username": "admin",
                            "password": "bootstrap-password-123",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, logged_in.status_code)
                    cookie = logged_in.headers["set-cookie"]
                    self.assertIn("HttpOnly", cookie)
                    self.assertIn("SameSite=strict", cookie)
                    created = client.post(
                        "/admin/users",
                        data={
                            "username": "participant.one",
                            "display_name": "Participant One",
                            "role": "participant",
                            "password": "participant-password-123",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, created.status_code)
                    client.post("/logout", follow_redirects=False)
                    participant_login = client.post(
                        "/login",
                        data={
                            "username": "participant.one",
                            "password": "participant-password-123",
                        },
                        follow_redirects=False,
                    )
                    self.assertEqual(303, participant_login.status_code)
                    self.assertEqual(200, client.get("/").status_code)
                    self.assertEqual(403, client.get("/new").status_code)
                    self.assertEqual(403, client.get("/library").status_code)

    def test_permission_matrix_separates_shared_roles(self) -> None:
        self.assertIsNone(required_capability("GET", "/healthz"))
        self.assertEqual("participate", required_capability("GET", "/"))
        self.assertEqual(
            "participate",
            required_capability(
                "GET",
                "/exercises/ttx_123456789abc/present/status",
            ),
        )
        self.assertEqual(
            "evaluate",
            required_capability(
                "POST",
                "/exercises/ttx_123456789abc/objectives/0",
            ),
        )
        self.assertEqual("admin", required_capability("GET", "/admin/users"))
