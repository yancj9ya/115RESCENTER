from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.config.settings import AppSettings
from src.organizing import MEDIA_KIND_MOVIE, OrganizeMetadata, OrganizeRule
from src.processors.fakes import FakeMetadataResolver, FakeOrganizeStorage, FakeTransferStorage
from src.storage import Storage115Config, Storage115Error


class FakeTelegramFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def fetch_messages(self, source_id: str, cursor: int | None = None) -> list[object]:
        self.calls.append((source_id, cursor))
        return []


class RuntimeFactoryTest(unittest.TestCase):
    def test_module_import_and_factory_init_do_not_construct_real_runtime_clients(self) -> None:
        with patch("src.storage.service115.Storage115Service.__init__", side_effect=AssertionError("storage constructed")), \
             patch("src.organizing.tmdb.TmdbMultiResolver.__init__", side_effect=AssertionError("tmdb constructed")), \
             tempfile.TemporaryDirectory() as tmp_dir:
            module = importlib.import_module("src.runtime.factory")
            factory = module.RuntimeFactory(db_path=Path(tmp_dir) / "runtime.db", settings=AppSettings())
            status = factory.build_runtime_control_service().status()

        self.assertEqual(status.desired_state, "stopped")
        self.assertTrue(status.control_plane_only)

    def test_injected_fake_fetcher_storage_resolver_organizer_clock_and_sleeper_are_used(self) -> None:
        fixed_now = datetime(2026, 5, 28, 8, 0, tzinfo=timezone.utc)
        slept: list[float] = []
        fetcher = FakeTelegramFetcher()
        transfer_storage = FakeTransferStorage()
        metadata = OrganizeMetadata(title="Injected", year=2026, kind=MEDIA_KIND_MOVIE)
        resolver = FakeMetadataResolver({1: metadata})
        rule = OrganizeRule(media_library_root_cid=100)

        with tempfile.TemporaryDirectory() as tmp_dir:
            from src.runtime.factory import RuntimeFactory

            factory = RuntimeFactory(
                db_path=Path(tmp_dir) / "runtime.db",
                settings=AppSettings(transfer_cid=9001),
                storage=transfer_storage,
                fetcher=fetcher,
                resolver=resolver,
                organizer_rule=rule,
                clock=lambda: fixed_now,
                sleeper=lambda seconds: slept.append(seconds),
            )

            collection = factory.build_telegram_collection_service(source_id="movie_channel")
            transfer = factory.build_transfer_queue_processor(max_attempts=2)
            organize = factory.build_organize_run_service()

            collection_result = collection.poll_once()
            transfer_result = transfer.process_next_transfer()
            factory.build_sleeper()(0.25)

        self.assertIs(factory.build_clock()(), fixed_now)
        self.assertEqual(slept, [0.25])
        self.assertEqual(fetcher.calls, [("movie_channel", None)])
        self.assertEqual(collection_result.status, "SUCCESS")
        self.assertFalse(transfer_result.claimed)
        self.assertIs(transfer._storage, transfer_storage)
        self.assertIs(organize._storage, transfer_storage)
        self.assertIs(organize._metadata_resolver, resolver)
        self.assertEqual(organize._rule, rule)

    def test_default_metadata_resolver_cleans_filename_before_tmdb_search(self) -> None:
        from src.organizing.tmdb import TmdbConfig

        captured: list[str] = []

        class _Item:
            name = "大唐迷雾-S01E15.2160p.HDR10.HEVC.WEB-DL.mkv"

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("src.organizing.tmdb.TmdbMultiResolver.resolve_multi", autospec=True) as mock_resolve:
            mock_resolve.side_effect = lambda _self, query, *a, **k: captured.append(query)
            from src.runtime.factory import RuntimeFactory

            factory = RuntimeFactory(
                db_path=Path(tmp_dir) / "runtime.db",
                settings=AppSettings(tmdb=TmdbConfig(bearer_token="token")),
            )
            resolver = factory.build_metadata_resolver()
            resolver(_Item())

        # 传给 TMDB 的应是清洗后的剧名，而非完整文件名
        self.assertEqual(captured, ["大唐迷雾"])

    def test_storage_dependent_builders_are_blocked_without_p115_cookies_only_when_called(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            from src.runtime.factory import RuntimeFactory

            factory = RuntimeFactory(db_path=Path(tmp_dir) / "runtime.db", settings=AppSettings())

            self.assertEqual(factory.build_runtime_control_service().status().desired_state, "stopped")
            self.assertIsNotNone(factory.build_subscription_processor())
            with self.assertRaises(Storage115Error) as transfer_error:
                factory.build_transfer_queue_processor()
            with self.assertRaises(Storage115Error) as organize_error:
                factory.build_organize_run_service()

        current_cookie = os.getenv("P115_COOKIES", "")
        for error in (transfer_error.exception, organize_error.exception):
            text = str(error)
            self.assertIn("P115_COOKIES", text)
            self.assertNotIn("P115_COOKIES=", text)
            if current_cookie:
                self.assertNotIn(current_cookie, text)

    def test_missing_p115_cookies_does_not_block_injected_storage_builders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            from src.runtime.factory import RuntimeFactory

            storage = FakeOrganizeStorage(items=[])
            factory = RuntimeFactory(
                db_path=Path(tmp_dir) / "runtime.db",
                settings=AppSettings(),
                storage=storage,
                resolver=lambda item: None,
                organizer_rule=OrganizeRule(media_library_root_cid=100),
            )

            transfer = factory.build_transfer_queue_processor()
            organize = factory.build_organize_run_service()

        self.assertIs(transfer._storage, storage)
        self.assertIs(organize._storage, storage)

    def test_storage_builder_uses_configured_p115_only_inside_storage_builder_path(self) -> None:
        calls: list[Storage115Config] = []
        settings = AppSettings(p115=Storage115Config(cookies="super-secret-cookie"))

        def build_storage(config: Storage115Config):
            calls.append(config)
            return FakeTransferStorage()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("src.runtime.factory.Storage115Service", side_effect=build_storage):
            from src.runtime.factory import RuntimeFactory

            factory = RuntimeFactory(db_path=Path(tmp_dir) / "runtime.db", settings=settings)
            service = factory.build_storage()

        self.assertIsInstance(service, FakeTransferStorage)
        self.assertEqual(calls, [settings.p115])


if __name__ == "__main__":
    unittest.main()
