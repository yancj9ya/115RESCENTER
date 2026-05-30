from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

from src.resources import TelegramWebChannelRecord, TelegramWebChannelRepository, TelegramWebChannelService


class ResourceChannelModelImportTest(unittest.TestCase):
    def test_resource_channel_exports_are_available_without_side_effects(self) -> None:
        self.assertTrue(is_dataclass(TelegramWebChannelRecord))
        self.assertEqual(
            [field.name for field in fields(TelegramWebChannelRecord)],
            [
                "channel",
                "display_name",
                "enabled",
                "poll_interval_seconds",
                "created_at",
                "updated_at",
            ],
        )
        record = TelegramWebChannelRecord(
            channel="movie_channel",
            display_name="Movie Channel",
            enabled=True,
            poll_interval_seconds=1800,
            created_at="2026-05-28 10:00:00",
            updated_at="2026-05-28 10:00:00",
        )
        self.assertEqual(record.channel, "movie_channel")
        self.assertTrue(record.enabled)
        with self.assertRaises(Exception):
            record.channel = "changed"  # type: ignore[misc]


class ResourceChannelRepositorySchemaTest(unittest.TestCase):
    def test_init_schema_creates_telegram_web_channels_table_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "resources.db"
            repository = TelegramWebChannelRepository(db_path)
            repository.init_schema()
            repository.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='telegram_web_channels'"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertIn("telegram_web_channels", tables)
            self.assertIn("channel TEXT PRIMARY KEY", schema)
            self.assertIn("display_name TEXT NULL", schema)
            self.assertIn("enabled INTEGER NOT NULL DEFAULT 1", schema)
            self.assertIn("poll_interval_seconds INTEGER NOT NULL DEFAULT 1800", schema)
            self.assertIn("created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", schema)
            self.assertIn("updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", schema)


class ResourceChannelServiceTest(unittest.TestCase):
    def _service(self, tmp_dir: str) -> TelegramWebChannelService:
        repository = TelegramWebChannelRepository(Path(tmp_dir) / "resources.db")
        repository.init_schema()
        return TelegramWebChannelService(repository)

    def test_create_list_get_update_enable_disable_and_delete_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            created = service.create_channel(
                channel=" https://t.me/s/movie_channel/ ",
                display_name="  Movie Channel  ",
                enabled=False,
                poll_interval_seconds=1800,
            )
            another = service.create_channel(channel="@beta_channel", poll_interval_seconds=2400)

            self.assertEqual(created.channel, "movie_channel")
            self.assertEqual(created.display_name, "Movie Channel")
            self.assertFalse(created.enabled)
            self.assertEqual(created.poll_interval_seconds, 1800)
            self.assertTrue(created.created_at)
            self.assertTrue(created.updated_at)

            self.assertEqual(
                [record.channel for record in service.list_channels()],
                ["beta_channel", "movie_channel"],
            )
            self.assertEqual(service.get_channel("@movie_channel"), created)
            self.assertEqual(service.get_channel("https://t.me/movie_channel"), created)
            self.assertIsNone(service.get_channel("missing_channel"))

            updated = service.update_channel(
                "t.me/movie_channel",
                display_name="Movies HD",
                enabled=True,
                poll_interval_seconds=900,
            )
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated.channel, "movie_channel")
            self.assertEqual(updated.display_name, "Movies HD")
            self.assertTrue(updated.enabled)
            self.assertEqual(updated.poll_interval_seconds, 900)

            disabled = service.disable_channel("https://t.me/s/movie_channel")
            enabled = service.enable_channel("@movie_channel")
            self.assertIsNotNone(disabled)
            self.assertIsNotNone(enabled)
            assert disabled is not None
            assert enabled is not None
            self.assertFalse(disabled.enabled)
            self.assertTrue(enabled.enabled)

            self.assertTrue(service.delete_channel("movie_channel"))
            self.assertFalse(service.delete_channel("movie_channel"))
            self.assertIsNone(service.get_channel("@movie_channel"))
            self.assertEqual([record.channel for record in service.list_channels()], [another.channel])

    def test_normalize_channel_accepts_telegram_forms_and_rejects_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            self.assertEqual(service.normalize_channel(" @movie_channel "), "movie_channel")
            self.assertEqual(service.normalize_channel("t.me/movie_channel"), "movie_channel")
            self.assertEqual(service.normalize_channel("telegram.me/movie_channel/"), "movie_channel")
            self.assertEqual(service.normalize_channel("https://t.me/s/movie_channel/"), "movie_channel")

            with self.assertRaises(ValueError):
                service.normalize_channel("   ")
            with self.assertRaises(ValueError):
                service.normalize_channel("https://t.me/")

    def test_update_enable_disable_and_delete_missing_channel_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            self.assertIsNone(service.update_channel("missing", display_name="Missing"))
            self.assertIsNone(service.enable_channel("missing"))
            self.assertIsNone(service.disable_channel("missing"))
            self.assertFalse(service.delete_channel("missing"))

    def test_duplicate_channel_creation_is_deterministic_after_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            created = service.create_channel(channel="@movie_channel", display_name="Movie Channel")

            with self.assertRaises(sqlite3.IntegrityError):
                service.create_channel(channel="https://t.me/s/movie_channel", display_name="Duplicate")

            stored = service.get_channel("movie_channel")
            self.assertEqual(stored, created)
            self.assertEqual([record.channel for record in service.list_channels()], ["movie_channel"])

    def test_create_and_update_reject_invalid_poll_interval_without_persisting_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            with self.assertRaises(ValueError):
                service.create_channel(channel="movie_channel", poll_interval_seconds=0)
            self.assertEqual(service.list_channels(), [])

            created = service.create_channel(channel="movie_channel", poll_interval_seconds=1800)
            with self.assertRaises(ValueError):
                service.update_channel("movie_channel", poll_interval_seconds=-5)

            stored = service.get_channel("movie_channel")
            self.assertEqual(stored, created)


if __name__ == "__main__":
    unittest.main()
