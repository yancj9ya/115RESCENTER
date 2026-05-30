from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path


class RankCacheRepositoryTest(unittest.TestCase):
    def build_repository(self, db_path: Path):
        from src.ranks.repository import RankCacheRepository

        repository = RankCacheRepository(db_path)
        repository.init_schema()
        return repository

    def test_schema_initialization_creates_table_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "ranks.db"
            repository = self.build_repository(db_path)
            repository.init_schema()

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()

        self.assertIn("rank_cache", tables)

    def test_upsert_then_get_round_trips_items_and_metadata(self) -> None:
        items = [
            {"rank": 1, "tmdb_id": 10, "kind": "tv", "title": "甲"},
            {"rank": 2, "tmdb_id": 20, "kind": "movie", "title": "乙"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            saved = repository.upsert(
                source="tencent",
                key="tv",
                items=items,
                status="ok",
                error=None,
            )
            fetched = repository.get(source="tencent", key="tv")

        self.assertEqual(saved.source, "tencent")
        self.assertEqual(saved.key, "tv")
        self.assertEqual(saved.status, "ok")
        self.assertIsNone(saved.error)
        self.assertEqual(saved.items, items)
        self.assertIsNotNone(saved.refreshed_at)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.items, items)
        self.assertEqual(fetched.status, "ok")

    def test_upsert_overwrites_existing_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            repository.upsert(source="tmdb", key="tv_popular", items=[{"a": 1}], status="ok", error=None)
            repository.upsert(
                source="tmdb",
                key="tv_popular",
                items=[],
                status="error",
                error="boom",
            )
            fetched = repository.get(source="tmdb", key="tv_popular")

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.items, [])
        self.assertEqual(fetched.status, "error")
        self.assertEqual(fetched.error, "boom")

    def test_get_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            self.assertIsNone(repository.get(source="tencent", key="movie"))

    def test_get_all_returns_every_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            repository.upsert(source="tencent", key="tv", items=[], status="ok", error=None)
            repository.upsert(source="tmdb", key="tv_popular", items=[], status="ok", error=None)
            records = repository.get_all()

        keys = {(r.source, r.key) for r in records}
        self.assertEqual(keys, {("tencent", "tv"), ("tmdb", "tv_popular")})

    def test_oldest_refreshed_at_reports_min_or_none_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            self.assertIsNone(repository.oldest_refreshed_at())
            repository.upsert(source="tencent", key="tv", items=[], status="ok", error=None)
            self.assertIsNotNone(repository.oldest_refreshed_at())

    def test_count_reports_number_of_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = self.build_repository(Path(tmp_dir) / "ranks.db")
            self.assertEqual(repository.count(), 0)
            repository.upsert(source="tencent", key="tv", items=[], status="ok", error=None)
            self.assertEqual(repository.count(), 1)


if __name__ == "__main__":
    unittest.main()
