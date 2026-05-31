from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config.settings import AppSettings
from src.organizing.repository import OrganizeRepository
from src.queue import ShareLink
from src.queue.repository import QueueRepository
from src.resources import TelegramWebChannelRepository, TelegramWebChannelService
from src.runtime import RuntimeControlRepository, RuntimeControlService
from src.storage import Storage115Config
from src.organizing.tmdb import TmdbConfig


class RuntimeControlServiceTest(unittest.TestCase):
    def build_service(self, db_path: Path, settings: AppSettings | None = None) -> RuntimeControlService:
        queue_repository = QueueRepository(db_path)
        queue_repository.init_schema()
        organize_repository = OrganizeRepository(db_path)
        organize_repository.init_schema()
        channel_repository = TelegramWebChannelRepository(db_path)
        channel_repository.init_schema()
        runtime_repository = RuntimeControlRepository(db_path)
        runtime_repository.init_schema()
        return RuntimeControlService(
            repository=runtime_repository,
            queue_repository=queue_repository,
            organize_repository=organize_repository,
            telegram_web_channel_service=TelegramWebChannelService(channel_repository),
            settings=settings or AppSettings(),
        )

    def test_default_state_is_stopped_and_control_plane_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            status = self.build_service(Path(tmp_dir) / "runtime.db").status()

        self.assertEqual(status.desired_state, "stopped")
        self.assertEqual(status.effective_state, "stopped")
        self.assertTrue(status.control_plane_only)
        self.assertIsNone(status.started_at)
        self.assertIsNotNone(status.stopped_at)
        self.assertIn("API process", status.message)

    def test_start_and_stop_are_idempotent_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            service = self.build_service(db_path)
            first_start = service.start()
            second_start = service.start()
            reloaded = self.build_service(db_path).status()
            first_stop = service.stop()
            second_stop = service.stop()
            runtime_repository = RuntimeControlRepository(db_path)
            component_statuses = runtime_repository.list_component_statuses()
            heartbeats = runtime_repository.list_worker_heartbeats()

        self.assertTrue(first_start.changed)
        self.assertFalse(second_start.changed)
        self.assertEqual(first_start.desired_state, "running")
        self.assertEqual(reloaded.desired_state, "running")
        self.assertTrue(first_stop.changed)
        self.assertFalse(second_stop.changed)
        self.assertEqual(second_stop.desired_state, "stopped")
        self.assertEqual(component_statuses, [])
        self.assertEqual(heartbeats, [])

    def test_status_merges_worker_telemetry_and_degrades_effective_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            runtime_repository = RuntimeControlRepository(db_path)
            settings = AppSettings(
                p115=Storage115Config(cookies="secret-cookie", ensure_cookies=False, cache_home=Path("cache")),
                tmdb=TmdbConfig(bearer_token="secret-token"),
            )
            service = self.build_service(db_path, settings=settings)
            runtime_repository.start()
            runtime_repository.save_component_status(
                name="transfer_processor",
                status="blocked",
                enabled=True,
                configured=False,
                started_at="2026-05-28 08:00:00",
                finished_at="2026-05-28 08:00:05",
                success=False,
                error="storage secret-cookie token failed\nwith details",
                tick_count=3,
            )
            runtime_repository.save_worker_heartbeat(
                worker_name="runtime-worker",
                component_name="transfer_processor",
                status="failed",
                pid=1234,
                error="worker secret-token failed",
            )

            status = service.status()

        components = {component.name: component for component in status.components}
        transfer = components["transfer_processor"]
        self.assertFalse(status.control_plane_only)
        self.assertEqual(status.effective_state, "degraded")
        self.assertEqual(transfer.status, "blocked")
        self.assertEqual(transfer.last_status, "failed")
        self.assertEqual(transfer.tick_count, 3)
        self.assertEqual(transfer.last_started_at, "2026-05-28 08:00:00")
        self.assertEqual(transfer.last_finished_at, "2026-05-28 08:00:05")
        self.assertFalse(transfer.last_success)
        self.assertIsNotNone(transfer.last_heartbeat_at)
        self.assertNotIn("\n", transfer.last_error or "")
        self.assertNotIn("secret-cookie", transfer.last_error or "")
        self.assertNotIn("secret-token", str(status))

    def test_status_reads_repositories_and_settings_without_network_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            queue_repository = QueueRepository(db_path)
            queue_repository.init_schema()
            queue_repository.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movies",
                message_id="101",
                message_url="https://t.me/s/movies/101",
                message_text="Movie https://115.com/s/a1",
                published_at=None,
                shares=[ShareLink(share_code="a1", receive_code="", share_url="https://115.com/s/a1")],
            )
            channel_repository = TelegramWebChannelRepository(db_path)
            channel_repository.init_schema()
            channel_service = TelegramWebChannelService(channel_repository)
            channel_service.create_channel(channel="movies", enabled=True)
            settings = AppSettings(
                transfer_cid=9001,
                p115=Storage115Config(cookies="secret-cookie", ensure_cookies=False, cache_home=Path("cache")),
                tmdb=TmdbConfig(bearer_token="secret-token"),
            )
            status = self.build_service(db_path, settings=settings).start()

        components = {component.name: component for component in status.components}
        self.assertEqual(status.queue_counts.collect_queue["PENDING"], 1)
        self.assertEqual(components["telegram_collector"].status, "ready")
        self.assertEqual(components["subscription_processor"].status, "ready")
        self.assertEqual(components["transfer_processor"].status, "ready")
        self.assertEqual(components["organizer"].status, "ready")
        self.assertNotIn("secret-cookie", str(status))
        self.assertNotIn("secret-token", str(status))

    def test_missing_storage_and_tmdb_block_only_dependent_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self.build_service(Path(tmp_dir) / "runtime.db", settings=AppSettings())
            status = service.start()

        components = {component.name: component for component in status.components}
        self.assertEqual(status.effective_state, "degraded")
        self.assertEqual(components["transfer_processor"].status, "blocked")
        self.assertEqual(components["organizer"].status, "blocked")
        self.assertIn("115 storage", components["transfer_processor"].detail)
        self.assertIn("TMDB", components["organizer"].detail)

    def test_runtime_sources_do_not_import_worker_or_network_dependencies(self) -> None:
        runtime_dir = Path(__file__).resolve().parents[1] / "src" / "runtime"
        forbidden = (
            "p115client",
            "Storage115Service",
            "urlopen",
            "requests",
            "TelegramCollectionService",
            "TmdbMovieResolver",
            "TmdbMultiResolver",
            "threading",
            "asyncio",
        )
        for source_path in runtime_dir.glob("*.py"):
            content = source_path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, content, f"{token} leaked into {source_path}")


if __name__ == "__main__":
    unittest.main()
