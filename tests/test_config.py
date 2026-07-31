from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from app.config import load_settings


class ConfigurationTests(TestCase):
    def test_defaults_to_user_writable_data_root(self) -> None:
        with patch.dict(
            "os.environ",
            {"HOME": "/tmp/livefire-home"},
            clear=True,
        ):
            settings = load_settings()
        expected_root = Path("/tmp/livefire-home/.livefirettx").resolve()
        self.assertEqual(expected_root, settings.data_root)
        self.assertEqual(expected_root / "livefirettx.db", settings.database_path)
        self.assertEqual(
            expected_root / "generated" / "exercises",
            settings.generated_root,
        )
        self.assertEqual(expected_root / "backups", settings.backup_root)
        self.assertTrue(settings.scheduler_enabled)
        self.assertEqual(2, settings.scheduler_interval_seconds)

    def test_data_root_sets_all_default_storage_paths(self) -> None:
        with patch.dict(
            "os.environ",
            {"LIVEFIRE_DATA_ROOT": "/tmp/livefire-data"},
            clear=True,
        ):
            settings = load_settings()
        expected_root = Path("/tmp/livefire-data").resolve()
        self.assertEqual(expected_root, settings.data_root)
        self.assertEqual(expected_root / "livefirettx.db", settings.database_path)
        self.assertEqual(
            expected_root / "generated" / "exercises",
            settings.generated_root,
        )
        self.assertEqual(expected_root / "backups", settings.backup_root)

    def test_accepts_local_control_url_and_custom_paths(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LIVEFIRE_DATABASE_PATH": "/tmp/livefire/config.db",
                "LIVEFIRE_GENERATED_ROOT": "/tmp/livefire/exercises",
                "LIVEFIRE_CONTROL_URL": "http://localhost:9000/",
                "LIVEFIRE_REQUEST_TIMEOUT_SECONDS": "7",
                "LIVEFIRE_SCHEDULER_ENABLED": "false",
                "LIVEFIRE_SCHEDULER_INTERVAL_SECONDS": "5",
            },
            clear=True,
        ):
            settings = load_settings()
        self.assertEqual(
            Path("/tmp/livefire/config.db").resolve(),
            settings.database_path,
        )
        self.assertEqual("http://localhost:9000", settings.control_url)
        self.assertEqual(7, settings.request_timeout_seconds)
        self.assertFalse(settings.scheduler_enabled)
        self.assertEqual(5, settings.scheduler_interval_seconds)

    def test_rejects_invalid_scheduler_configuration(self) -> None:
        for environment in [
            {"LIVEFIRE_SCHEDULER_ENABLED": "sometimes"},
            {"LIVEFIRE_SCHEDULER_INTERVAL_SECONDS": "0"},
            {"LIVEFIRE_SCHEDULER_INTERVAL_SECONDS": "fast"},
        ]:
            with self.subTest(environment=environment):
                with patch.dict("os.environ", environment, clear=True):
                    with self.assertRaises(ValueError):
                        load_settings()

    def test_rejects_non_local_control_url(self) -> None:
        for control_url in [
            "https://example.com",
            "https://localhost:8090",
            "http://localhost.evil.example:8090",
            "http://localhost@example.com:8090",
            "http://127.0.0.1.evil.example:8090",
            "http://localhost:8090/controller",
            "http://localhost:8090?target=external",
        ]:
            with self.subTest(control_url=control_url):
                with patch.dict(
                    "os.environ",
                    {"LIVEFIRE_CONTROL_URL": control_url},
                    clear=True,
                ):
                    with self.assertRaisesRegex(ValueError, "local HTTP origin"):
                        load_settings()

    def test_accepts_ipv6_loopback_control_url(self) -> None:
        with patch.dict(
            "os.environ",
            {"LIVEFIRE_CONTROL_URL": "http://[::1]:8090/"},
            clear=True,
        ):
            settings = load_settings()
        self.assertEqual("http://[::1]:8090", settings.control_url)

    def test_container_host_requires_explicit_opt_in(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LIVEFIRE_CONTROL_URL": "http://host.docker.internal:8090",
                "LIVEFIRE_ALLOW_CONTAINER_HOST": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "local HTTP origin"):
                load_settings()

        with patch.dict(
            "os.environ",
            {
                "LIVEFIRE_CONTROL_URL": "http://host.docker.internal:8090",
                "LIVEFIRE_ALLOW_CONTAINER_HOST": "true",
            },
            clear=True,
        ):
            settings = load_settings()
        self.assertTrue(settings.allow_container_host)
        self.assertEqual(
            "http://host.docker.internal:8090",
            settings.control_url,
        )
