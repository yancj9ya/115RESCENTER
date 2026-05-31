from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path


class SubscriptionRuleModelTest(unittest.TestCase):
    def test_subscription_rule_record_is_frozen_dataclass_with_expected_fields(self) -> None:
        from src.subscriptions.repository import SubscriptionRuleRecord

        self.assertTrue(is_dataclass(SubscriptionRuleRecord))
        self.assertEqual(
            [field.name for field in fields(SubscriptionRuleRecord)],
            [
                "id",
                "name",
                "pattern",
                "enabled",
                "created_at",
                "updated_at",
                "tmdb_id",
                "tmdb_kind",
                "year",
                "require_year_match",
                "aliases",
                "poster_path",
            ],
        )

        record = SubscriptionRuleRecord(
            id=1,
            name="Movies 1080p",
            pattern="1080p",
            enabled=True,
            created_at="2026-05-27 10:00:00",
            updated_at="2026-05-27 10:00:00",
        )

        self.assertEqual(record.name, "Movies 1080p")
        self.assertEqual(record.pattern, "1080p")
        self.assertTrue(record.enabled)
        self.assertIsNone(record.tmdb_id)
        self.assertIsNone(record.tmdb_kind)
        self.assertIsNone(record.year)
        self.assertTrue(record.require_year_match)
        self.assertEqual(record.aliases, ())
        with self.assertRaises(Exception):
            record.name = "changed"  # type: ignore[misc]


class SubscriptionRepositorySchemaTest(unittest.TestCase):
    def test_init_schema_creates_subscription_rules_table_and_is_idempotent(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()
            repo.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='subscription_rules'"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertIn("subscription_rules", tables)
            self.assertIn("id INTEGER PRIMARY KEY AUTOINCREMENT", schema)
            self.assertIn("name TEXT NOT NULL", schema)
            self.assertIn("pattern TEXT NOT NULL", schema)
            self.assertIn("enabled INTEGER NOT NULL DEFAULT 1", schema)
            self.assertIn("created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", schema)
            self.assertIn("updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", schema)
            self.assertNotIn("UNIQUE(name", schema)
            self.assertNotIn("target_cid", schema)

            connection = sqlite3.connect(db_path)
            try:
                columns = {
                    row[1]: row[2]
                    for row in connection.execute("PRAGMA table_info(subscription_rules)").fetchall()
                }
            finally:
                connection.close()
            self.assertEqual(columns.get("tmdb_id"), "INTEGER")
            self.assertEqual(columns.get("tmdb_kind"), "TEXT")
            self.assertEqual(columns.get("year"), "INTEGER")
            self.assertEqual(columns.get("require_year_match"), "INTEGER")
            self.assertEqual(columns.get("aliases_json"), "TEXT")

    def test_init_schema_adds_missing_tmdb_columns_to_legacy_tables(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE subscription_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        pattern TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO subscription_rules (name, pattern, enabled) VALUES (?, ?, ?)",
                    ("legacy", "1080p", 1),
                )
                connection.commit()
            finally:
                connection.close()

            SubscriptionRepository(db_path).init_schema()

            connection = sqlite3.connect(db_path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(subscription_rules)").fetchall()
                }
                row = connection.execute(
                    "SELECT name, tmdb_id, tmdb_kind, year, require_year_match, aliases_json FROM subscription_rules"
                ).fetchone()
            finally:
                connection.close()
            self.assertTrue({"tmdb_id", "tmdb_kind", "year", "require_year_match", "aliases_json"}.issubset(columns))
            self.assertEqual(row, ("legacy", None, None, None, 1, None))


class SubscriptionRepositoryCrudTest(unittest.TestCase):
    def test_create_list_get_update_and_hard_delete_rule(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            first = repo.create_rule(name="Movies 1080p", pattern=r"1080p", enabled=True)
            second = repo.create_rule(name="Shows", pattern=r"S\\d{2}E\\d{2}", enabled=False)

            self.assertEqual(first.id + 1, second.id)
            self.assertEqual(first.name, "Movies 1080p")
            self.assertEqual(first.pattern, r"1080p")
            self.assertTrue(first.enabled)
            self.assertFalse(second.enabled)
            self.assertTrue(first.created_at)
            self.assertTrue(first.updated_at)

            self.assertEqual([rule.id for rule in repo.list_rules()], [first.id, second.id])
            self.assertEqual(repo.get_rule(first.id), first)

            updated = repo.update_rule(
                first.id,
                name="Movies UHD",
                pattern=r"2160p|4K",
                enabled=False,
            )

            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated.id, first.id)
            self.assertEqual(updated.name, "Movies UHD")
            self.assertEqual(updated.pattern, r"2160p|4K")
            self.assertFalse(updated.enabled)
            self.assertEqual(repo.get_rule(first.id), updated)
            self.assertEqual(repo.get_rule(9999), None)

            self.assertTrue(repo.delete_rule(first.id))
            self.assertFalse(repo.delete_rule(first.id))
            self.assertIsNone(repo.get_rule(first.id))
            self.assertEqual([rule.id for rule in repo.list_rules()], [second.id])

            connection = sqlite3.connect(db_path)
            try:
                deleted_count = connection.execute(
                    "SELECT COUNT(*) FROM subscription_rules WHERE id = ?",
                    (first.id,),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(deleted_count, 0)

    def test_rule_names_are_not_unique_and_patterns_round_trip_faithfully(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        pattern = r"(?i)电影\\s+S\\d{2}E\\d{2}.*1080p"
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            first = repo.create_rule(name="Duplicate", pattern=pattern, enabled=True)
            second = repo.create_rule(name="Duplicate", pattern="[stored for later validation]", enabled=True)

            self.assertNotEqual(first.id, second.id)
            self.assertEqual(first.name, second.name)
            self.assertEqual(repo.get_rule(first.id).pattern, pattern)  # type: ignore[union-attr]
            self.assertEqual([rule.id for rule in repo.list_rules()], [first.id, second.id])

    def test_partial_update_preserves_unspecified_fields_and_unknown_update_returns_none(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            rule = repo.create_rule(name="Movies", pattern="1080p", enabled=True)
            disabled = repo.update_rule(rule.id, enabled=False)

            self.assertIsNotNone(disabled)
            assert disabled is not None
            self.assertEqual(disabled.name, "Movies")
            self.assertEqual(disabled.pattern, "1080p")
            self.assertFalse(disabled.enabled)
            self.assertIsNone(repo.update_rule(9999, name="missing"))

    def test_records_persist_across_repository_instances(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            first_repo = SubscriptionRepository(db_path)
            first_repo.init_schema()
            created = first_repo.create_rule(name="Movies", pattern="1080p", enabled=True)

            second_repo = SubscriptionRepository(db_path)
            second_repo.init_schema()
            loaded = second_repo.get_rule(created.id)

            self.assertEqual(loaded, created)


class SubscriptionRepositoryTmdbAwareTest(unittest.TestCase):
    def test_create_rule_persists_tmdb_id_kind_and_aliases(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            rule = repo.create_rule(
                name="The Three-Body Problem",
                pattern="三体",
                enabled=True,
                tmdb_id=108545,
                tmdb_kind="tv",
                aliases=["三体", "Three-Body", " 3 Body Problem "],
                year=2024,
                require_year_match=True,
            )

            self.assertEqual(rule.tmdb_id, 108545)
            self.assertEqual(rule.tmdb_kind, "tv")
            self.assertEqual(rule.year, 2024)
            self.assertTrue(rule.require_year_match)
            self.assertEqual(rule.aliases, ("三体", "Three-Body", "3 Body Problem"))

            loaded = repo.get_rule(rule.id)
            self.assertEqual(loaded, rule)

    def test_create_rule_without_tmdb_fields_leaves_them_null(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            rule = repo.create_rule(name="Legacy", pattern="1080p", enabled=True)

            self.assertIsNone(rule.tmdb_id)
            self.assertIsNone(rule.tmdb_kind)
            self.assertIsNone(rule.year)
            self.assertTrue(rule.require_year_match)
            self.assertEqual(rule.aliases, ())

            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute(
                    "SELECT tmdb_id, tmdb_kind, year, require_year_match, aliases_json FROM subscription_rules WHERE id = ?",
                    (rule.id,),
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, (None, None, None, 1, None))

    def test_update_rule_can_set_and_clear_tmdb_fields_without_clobbering_others(self) -> None:
        from src.subscriptions.repository import SubscriptionRepository

        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "subscriptions.db"
            repo = SubscriptionRepository(db_path)
            repo.init_schema()

            rule = repo.create_rule(
                name="Movies",
                pattern="1080p",
                enabled=True,
                tmdb_id=42,
                tmdb_kind="movie",
                aliases=["alpha"],
                year=2024,
                require_year_match=True,
            )

            updated = repo.update_rule(rule.id, enabled=False)
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated.tmdb_id, 42)
            self.assertEqual(updated.tmdb_kind, "movie")
            self.assertEqual(updated.aliases, ("alpha",))
            self.assertEqual(updated.year, 2024)
            self.assertTrue(updated.require_year_match)
            self.assertFalse(updated.enabled)

            cleared = repo.update_rule(
                rule.id,
                tmdb_id=None,
                tmdb_kind=None,
                aliases=[],
                year=None,
                require_year_match=False,
            )
            self.assertIsNotNone(cleared)
            assert cleared is not None
            self.assertIsNone(cleared.tmdb_id)
            self.assertIsNone(cleared.tmdb_kind)
            self.assertIsNone(cleared.year)
            self.assertFalse(cleared.require_year_match)
            self.assertEqual(cleared.aliases, ())

            replaced = repo.update_rule(rule.id, aliases=["beta", "gamma"])
            self.assertIsNotNone(replaced)
            assert replaced is not None
            self.assertEqual(replaced.aliases, ("beta", "gamma"))


if __name__ == "__main__":
    unittest.main()
