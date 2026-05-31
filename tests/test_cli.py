from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.queue.models import ShareLink
from src.queue.repository import QueueRepository
from src.subscriptions.repository import SubscriptionRepository


class ParseShareTextCliTest(unittest.TestCase):
    def test_parse_share_text_prints_share_code_and_receive_code(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "main.py",
                "parse-share-text",
                "资源：https://115.com/s/abc123?password=xy9z",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "abc123\txy9z\thttps://115.com/s/abc123?password=xy9z\n")

    def test_collect_tg_web_history_reads_html_file_and_prints_collected_share(self) -> None:
        html = '''
        <div class="tgme_widget_message" data-post="movie_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            新资源 https://115.com/s/abc123#xy9z
          </div>
        </div>
        '''
        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "channel.html"
            html_path.write_text(html, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "collect-tg-web-history",
                    "movie_channel",
                    "--html-file",
                    str(html_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "telegram_web\tmovie_channel\t101\tabc123\txy9z\thttps://115.com/s/abc123#xy9z\n",
        )

    def test_collect_tg_web_incremental_polls_html_file_and_prints_contract_summary(self) -> None:
        html = '''
        <div class="tgme_widget_message" data-post="some_channel/100">
          <div class="tgme_widget_message_text js-message_text">
            Chat with no share link
          </div>
        </div>
        <div class="tgme_widget_message" data-post="some_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            Movie A https://115.com/s/abc123#xy9z
          </div>
        </div>
        <div class="tgme_widget_message" data-post="some_channel/102">
          <div class="tgme_widget_message_text js-message_text">
            Movie B https://115.com/s/def456#uv88
          </div>
        </div>
        '''
        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "channel.html"
            db_path = Path(tmp_dir) / "queue.db"
            html_path.write_text(html, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "collect-tg-web-incremental",
                    "some_channel",
                    "--html-file",
                    str(html_path),
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            repeated = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "collect-tg-web-incremental",
                    "some_channel",
                    "--html-file",
                    str(html_path),
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "source_type=telegram_web\tsource_id=some_channel\tscanned=3\tparsed_shares=2\t"
            "enqueued=2\tskipped_existing=0\tcursor=102\tstatus=success\n",
        )
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(
            repeated.stdout,
            "source_type=telegram_web\tsource_id=some_channel\tscanned=3\tparsed_shares=2\t"
            "enqueued=0\tskipped_existing=2\tcursor=102\tstatus=success\n",
        )

    def test_tg_collector_status_prints_known_channel_cursor_status_contract_fields(self) -> None:
        html = '''
        <div class="tgme_widget_message" data-post="some_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            Movie A https://115.com/s/abc123#xy9z
          </div>
        </div>
        <div class="tgme_widget_message" data-post="some_channel/102">
          <div class="tgme_widget_message_text js-message_text">
            Movie B https://115.com/s/def456#uv88
          </div>
        </div>
        '''
        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "channel.html"
            db_path = Path(tmp_dir) / "queue.db"
            html_path.write_text(html, encoding="utf-8")
            poll = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "collect-tg-web-incremental",
                    "some_channel",
                    "--html-file",
                    str(html_path),
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "tg-collector-status",
                    "some_channel",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(poll.returncode, 0, poll.stderr)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "source_type=telegram_web\tsource_id=some_channel\tcursor=102\t"
            "last_status=success\tlast_error=\n",
        )

    def test_plan_organize_json_reads_temp_json_and_prints_expected_line_without_cookies(self) -> None:
        items = [
            {
                "id": 123,
                "name": "raw-file.mkv",
                "is_dir": False,
                "metadata": {
                    "title": "Title",
                    "year": 2024,
                    "kind": "movie",
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "items.json"
            json_path.write_text(json.dumps(items), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "plan-organize-json",
                    str(json_path),
                    "--media-library-root-cid",
                    "100",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "123\traw-file.mkv\tTitle（2024）.mkv\t100\t电影/未分类地区/Title（2024）\n")

    def test_plan_organize_json_reads_region_metadata_and_prints_second_level_folder(self) -> None:
        items = [
            {
                "id": 125,
                "name": "raw-file.mkv",
                "is_dir": False,
                "metadata": {
                    "title": "Title",
                    "year": 2024,
                    "kind": "movie",
                    "region_primary": "CN",
                    "region_candidates": ["CN", "HK"],
                    "region_category": "国产",
                    "region_source": "production_countries",
                    "region_confidence": "high",
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "items.json"
            json_path.write_text(json.dumps(items), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "plan-organize-json",
                    str(json_path),
                    "--media-library-root-cid",
                    "100",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "125\traw-file.mkv\tTitle（2024）.mkv\t100\t电影/国产/Title（2024）\n")

    def test_plan_organize_json_reads_series_metadata_and_prints_series_plan(self) -> None:
        items = [
            {
                "id": 124,
                "name": "raw-episode.mkv",
                "is_dir": False,
                "metadata": {
                    "title": "Series Title",
                    "year": 2024,
                    "kind": "series",
                    "season": 1,
                    "episode": 2,
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "items.json"
            json_path.write_text(json.dumps(items), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "plan-organize-json",
                    str(json_path),
                    "--media-library-root-cid",
                    "100",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "124\traw-episode.mkv\tSeries Title.2024.S01E02.第2集.mkv\t100\t剧集/未分类地区/Series Title（2024）/S01\n",
        )

    def test_dry_run_backend_reads_messages_json_and_prints_summary_without_credentials(self) -> None:
        messages = [
            {
                "share_code": "abc123",
                "receive_code": "xy9z",
                "share_url": "https://115.com/s/abc123#xy9z",
                "source_type": "telegram_web",
                "source_id": "movie_channel",
                "message_id": "101",
                "message_text": "Movie release https://115.com/s/abc123#xy9z",
                "published_at": None,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            messages_path = Path(tmp_dir) / "messages.json"
            db_path = Path(tmp_dir) / "queue.db"
            messages_path.write_text(json.dumps(messages), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "dry-run-backend",
                    "--messages-json",
                    str(messages_path),
                    "--db-file",
                    str(db_path),
                    "--staging-cid",
                    "9001",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        parts = dict(part.split("=", 1) for part in completed.stdout.strip().split("\t"))
        self.assertEqual(parts["collect_enqueued"], "1")
        self.assertEqual(parts["collect_processed"], "1")
        self.assertEqual(parts["transfer_processed"], "1")
        self.assertEqual(parts["organize_moved"], "1")
        self.assertEqual(parts["notification_count"], "2")
        self.assertEqual(parts["errors"], "")

    def test_resolve_tmdb_movie_reads_temp_json_and_prints_movie_without_credentials(self) -> None:
        payload = {"results": [{"id": 1, "title": "Movie Title", "release_date": "2024-02-03"}]}
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "tmdb.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "resolve-tmdb-movie",
                    "Movie Query",
                    "--year",
                    "2024",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Movie Title\t2024\tmovie\n")

    def test_resolve_tmdb_movie_prints_region_metadata_when_present(self) -> None:
        payload = [
            {"results": [{"id": 1, "title": "Movie Title", "release_date": "2024-02-03"}]},
            {"production_countries": [{"iso_3166_1": "KR", "name": "South Korea"}]},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "tmdb.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "resolve-tmdb-movie",
                    "Movie Query",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Movie Title\t2024\tmovie\tKR\tKR\t日韩\tproduction_countries\thigh\n")

    def test_resolve_tmdb_multi_reads_temp_json_and_prints_tv_region_metadata(self) -> None:
        payload = [
            {"results": [{"id": 279388, "media_type": "tv", "name": "逐玉", "first_air_date": "2026-03-06"}]},
            {"origin_country": ["CN"], "production_countries": [{"iso_3166_1": "CN", "name": "China"}]},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "tmdb_multi.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "resolve-tmdb-multi",
                    "逐玉",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "逐玉\t2026\tseries\tCN\tCN\t国产\torigin_country\thigh\n")

    def test_resolve_tmdb_multi_reads_temp_json_and_prints_movie_metadata(self) -> None:
        payload = [
            {"results": [{"id": 42, "media_type": "movie", "title": "Movie Title", "release_date": "2024-02-03"}]},
            {"production_countries": [{"iso_3166_1": "US", "name": "United States"}]},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "tmdb_multi.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "resolve-tmdb-multi",
                    "Movie Query",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Movie Title\t2024\tmovie\tUS\tUS\t欧美\tproduction_countries\thigh\n")

    def test_resolve_tmdb_multi_real_mode_without_dotenv_fails_before_network(self) -> None:
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [sys.executable, str(main_path), "resolve-tmdb-multi", "逐玉"],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("TMDB_BEARER_TOKEN", completed.stderr)
        self.assertIn("resolve-tmdb-multi", completed.stderr)

        payload = {"results": [{"id": 1, "title": "Movie Title", "release_date": "2024-02-03"}]}
        fake_secret = "fake-temp-dotenv-secret"
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            json_path = tmp_path / "tmdb.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            (tmp_path / ".env").write_text(f"TMDB_BEARER_TOKEN={fake_secret}\n", encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(main_path),
                    "resolve-tmdb-movie",
                    "Movie",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Movie Title\t2024\tmovie\n")
        self.assertNotIn(fake_secret, completed.stdout)
        self.assertNotIn(fake_secret, completed.stderr)

    def test_resolve_tmdb_movie_reads_empty_temp_json_and_prints_nothing_without_credentials(self) -> None:
        payload = {"results": []}
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_path = Path(tmp_dir) / "tmdb.json"
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "resolve-tmdb-movie",
                    "Movie Query",
                    "--year",
                    "2024",
                    "--json-file",
                    str(json_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_resolve_tmdb_movie_real_mode_from_temp_cwd_without_dotenv_fails_before_network(self) -> None:
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(main_path),
                    "resolve-tmdb-movie",
                    "Movie",
                    "--year",
                    "2024",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("TMDB_BEARER_TOKEN", completed.stderr)

    def test_subscription_command_names_are_registered_in_help_contract(self) -> None:
        completed = subprocess.run(
            [sys.executable, "main.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command_name in (
            "subscription-list",
            "subscription-create",
            "subscription-enable",
            "subscription-disable",
            "subscription-delete",
            "subscription-test",
            "subscription-process",
        ):
            self.assertIn(command_name, completed.stdout)

    def test_organize_run_once_command_is_registered_in_help_contract(self) -> None:
        completed = subprocess.run(
            [sys.executable, "main.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("organize-run-once", completed.stdout)

    def test_runtime_command_names_are_registered_in_help_contract(self) -> None:
        completed = subprocess.run(
            [sys.executable, "main.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        for command_name in ("runtime-status", "runtime-start", "runtime-stop", "runtime-worker"):
            self.assertIn(command_name, completed.stdout)

    def test_runtime_status_start_and_stop_are_script_friendly_without_secret_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "runtime.db"
            env = os.environ.copy()
            env["P115_COOKIES"] = "super-secret-cookie"
            env["TMDB_BEARER_TOKEN"] = "super-secret-token"
            env["P115_CACHE_HOME"] = "secret-cache-home"
            status = subprocess.run(
                [sys.executable, "main.py", "runtime-status", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            start = subprocess.run(
                [sys.executable, "main.py", "runtime-start", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            stop = subprocess.run(
                [sys.executable, "main.py", "runtime-stop", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        for completed in (status, start, stop):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            body = completed.stdout + completed.stderr
            self.assertNotIn("super-secret-cookie", body)
            self.assertNotIn("super-secret-token", body)
            self.assertNotIn("secret-cache-home", body)

        status_parts = dict(part.split("=", 1) for part in status.stdout.strip().split("\t"))
        self.assertEqual(status_parts["desired_state"], "stopped")
        self.assertEqual(status_parts["effective_state"], "stopped")
        self.assertEqual(status_parts["control_plane_only"], "true")
        self.assertIn("telegram_collector:idle", status_parts["components"])
        self.assertIn("transfer_processor:idle", status_parts["components"])

        start_lines = start.stdout.strip().splitlines()
        self.assertEqual(len(start_lines), 2)
        start_parts = dict(part.split("=", 1) for part in start_lines[0].split("\t"))
        start_action = dict(part.split("=", 1) for part in start_lines[1].split("\t"))
        self.assertEqual(start_parts["desired_state"], "running")
        self.assertEqual(start_parts["effective_state"], "running")
        self.assertEqual(start_action, {"action": "start", "changed": "true"})

        stop_lines = stop.stdout.strip().splitlines()
        self.assertEqual(len(stop_lines), 2)
        stop_parts = dict(part.split("=", 1) for part in stop_lines[0].split("\t"))
        stop_action = dict(part.split("=", 1) for part in stop_lines[1].split("\t"))
        self.assertEqual(stop_parts["desired_state"], "stopped")
        self.assertEqual(stop_action, {"action": "stop", "changed": "true"})

    def test_runtime_worker_once_uses_runtime_factory_and_run_once_without_external_clients(self) -> None:
        import main as cli_main

        worker_instance = SimpleNamespace(run_once=lambda: [
            SimpleNamespace(
                core="collector",
                status="success",
                processed=2,
                succeeded=1,
                skipped=0,
                failed=0,
                error=None,
            )
        ])
        fake_factory = object()
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(cli_main, "RuntimeFactory", return_value=fake_factory) as factory_cls, \
             patch.object(cli_main, "EventDrivenRuntime", return_value=worker_instance) as worker_cls, \
             patch.object(sys, "argv", [
                 "main.py",
                 "runtime-worker",
                 "--db-path",
                 str(Path(tmp_dir) / "runtime.db"),
                 "--once",
                 "--tick-seconds",
                 "9",
             ]), \
             patch("sys.stdout", new=stdout):
            cli_main.main()

        factory_cls.assert_called_once()
        worker_cls.assert_called_once()
        worker_call = worker_cls.call_args
        self.assertIs(worker_call.kwargs["factory"], fake_factory)
        self.assertEqual(worker_instance._interval_seconds, 9)
        self.assertEqual(
            stdout.getvalue(),
            "core=collector\tstatus=success\tprocessed=2\tsucceeded=1\tskipped=0\tfailed=0\terror=\n"
            "ticks=1\tresult_count=1\n",
        )

    def test_runtime_worker_uses_settings_intervals_when_cli_overrides_absent(self) -> None:
        import main as cli_main

        worker_instance = SimpleNamespace(run_until_stopped=lambda max_ticks: [])
        settings = SimpleNamespace(
            runtime_interval_seconds=7,
            runtime_sweep_interval_seconds=123,
            rank_refresh_interval_seconds=456,
        )
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(cli_main, "RuntimeFactory", return_value=SimpleNamespace(settings=settings)), \
             patch.object(cli_main, "EventDrivenRuntime", return_value=worker_instance) as worker_cls, \
             patch.object(worker_instance, "run_until_stopped", return_value=[]) as run_until_stopped, \
             patch.object(sys, "argv", [
                 "main.py",
                 "runtime-worker",
                 "--db-path",
                 str(Path(tmp_dir) / "runtime.db"),
                 "--max-ticks",
                 "1",
             ]), \
             patch("sys.stdout", new=stdout):
            cli_main.main()

        worker_cls.assert_called_once()
        self.assertEqual(worker_instance._interval_seconds, 7)
        self.assertEqual(worker_instance._sweep_interval_seconds, 123)
        self.assertEqual(worker_instance._rank_refresh_interval_seconds, 456)
        run_until_stopped.assert_called_once_with(max_ticks=1)

    def test_runtime_worker_max_ticks_calls_run_until_stopped_with_override_interval(self) -> None:
        import main as cli_main

        worker_instance = SimpleNamespace(run_until_stopped=lambda max_ticks: [])
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(cli_main, "RuntimeFactory", return_value=object()), \
             patch.object(cli_main, "EventDrivenRuntime", return_value=worker_instance) as worker_cls, \
             patch.object(worker_instance, "run_until_stopped", return_value=[]) as run_until_stopped, \
             patch.object(sys, "argv", [
                 "main.py",
                 "runtime-worker",
                 "--db-path",
                 str(Path(tmp_dir) / "runtime.db"),
                 "--max-ticks",
                 "3",
                 "--tick-seconds",
                 "11",
                 "--sweep-seconds",
                 "22",
             ]), \
             patch("sys.stdout", new=stdout):
            cli_main.main()

        worker_cls.assert_called_once()
        self.assertEqual(worker_instance._interval_seconds, 11)
        self.assertEqual(worker_instance._sweep_interval_seconds, 22)
        run_until_stopped.assert_called_once_with(max_ticks=3)
        self.assertEqual(stdout.getvalue(), "ticks=3\tresult_count=0\n")

    def test_organize_run_once_missing_env_fails_before_external_clients(self) -> None:
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env.pop("TMDB_BEARER_TOKEN", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(main_path),
                    "organize-run-once",
                    "--db-path",
                    str(Path(tmp_dir) / "queue.db"),
                    "--staging-cid",
                    "9001",
                    "--media-library-root-cid",
                    "100",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("P115_COOKIES", completed.stderr)
        self.assertIn("organize-run-once", completed.stderr)

    def test_subscription_create_list_toggle_test_and_delete_are_script_friendly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            create = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "subscription-create",
                    "--name",
                    "Shows",
                    "--pattern",
                    "S\\d{2}E\\d{2}",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            listing = subprocess.run(
                [sys.executable, "main.py", "subscription-list", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            disabled = subprocess.run(
                [sys.executable, "main.py", "subscription-disable", "1", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            enabled = subprocess.run(
                [sys.executable, "main.py", "subscription-enable", "1", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            tested = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "subscription-test",
                    "--rule-id",
                    "1",
                    "--text",
                    "Show S01E02",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            deleted = subprocess.run(
                [sys.executable, "main.py", "subscription-delete", "1", "--db-path", str(db_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(create.returncode, 0, create.stderr)
        self.assertEqual(create.stdout, "id=1\tname=Shows\tpattern=S\\d{2}E\\d{2}\tenabled=true\n")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(listing.stdout, create.stdout)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertEqual(disabled.stdout, "id=1\tname=Shows\tpattern=S\\d{2}E\\d{2}\tenabled=false\n")
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertEqual(enabled.stdout, create.stdout)
        self.assertEqual(tested.returncode, 0, tested.stderr)
        self.assertEqual(
            tested.stdout,
            "matched=true\trule_id=1\trule_name=Shows\tmatched_keywords=S\\d{2}E\\d{2}\n",
        )
        self.assertEqual(deleted.returncode, 0, deleted.stderr)
        self.assertEqual(deleted.stdout, "deleted=true\tid=1\n")

    def test_subscription_create_invalid_regex_fails_and_does_not_modify_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "subscription-create",
                    "--name",
                    "Broken",
                    "--pattern",
                    "[",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            repository = SubscriptionRepository(db_path)
            repository.init_schema()
            records = repository.list_rules()

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("invalid subscription pattern", completed.stderr)
        self.assertEqual(records, [])

    def test_subscription_process_moves_matching_collect_row_to_transfer_queue_once_without_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            queue_repository = QueueRepository(db_path)
            queue_repository.init_schema()
            subscription_repository = SubscriptionRepository(db_path)
            subscription_repository.init_schema()
            subscription_repository.create_rule(name="Movies", pattern="Movie", enabled=True)
            queue_repository.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="Movie release https://115.com/s/abc123#xy9z",
                published_at=None,
                shares=[
                    ShareLink(
                        share_code="abc123",
                        receive_code="xy9z",
                        share_url="https://115.com/s/abc123#xy9z",
                    )
                ],
            )
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "netdisk.yml").write_text("p115:\n  transfer_cid: 9001\n", encoding="utf-8")
            main_path = str(Path(__file__).resolve().parents[1] / "main.py")
            completed = subprocess.run(
                [
                    sys.executable,
                    main_path,
                    "subscription-process",
                    "--limit",
                    "100",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )
            first_transfer_records = queue_repository.list_transfer_queue()
            repeated = subprocess.run(
                [
                    sys.executable,
                    main_path,
                    "subscription-process",
                    "--limit",
                    "100",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_dir,
                env=env,
            )
            repeated_transfer_records = queue_repository.list_transfer_queue()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "scanned=1\tmatched=1\tcreated=1\tskipped=0\terrors=\n")
        self.assertEqual(len(first_transfer_records), 1)
        self.assertEqual(first_transfer_records[0].share_code, "abc123")
        self.assertEqual(first_transfer_records[0].receive_code, "xy9z")
        self.assertEqual(first_transfer_records[0].staging_cid, 9001)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(repeated.stdout, "scanned=0\tmatched=0\tcreated=0\tskipped=0\terrors=\n")
        self.assertEqual(len(repeated_transfer_records), 1)

    def test_subscription_process_limit_scans_one_collect_row_without_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            queue_repository = QueueRepository(db_path)
            queue_repository.init_schema()
            subscription_repository = SubscriptionRepository(db_path)
            subscription_repository.init_schema()
            subscription_repository.create_rule(name="Movies", pattern="Movie", enabled=True)
            queue_repository.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="101",
                message_url="https://t.me/s/movie_channel/101",
                message_text="Movie release https://115.com/s/abc123#xy9z",
                published_at=None,
                shares=[ShareLink(share_code="abc123", receive_code="xy9z", share_url="https://115.com/s/abc123#xy9z")],
            )
            queue_repository.enqueue_collected_message(
                source_type="telegram_web",
                source_id="movie_channel",
                message_id="102",
                message_url="https://t.me/s/movie_channel/102",
                message_text="Movie release https://115.com/s/def456#uv88",
                published_at=None,
                shares=[ShareLink(share_code="def456", receive_code="uv88", share_url="https://115.com/s/def456#uv88")],
            )
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            env["P115_TRANSFER_CID"] = "9001"
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "subscription-process",
                    "--limit",
                    "1",
                    "--db-path",
                    str(db_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            transfer_records = queue_repository.list_transfer_queue()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "scanned=1\tmatched=1\tcreated=1\tskipped=0\terrors=\n")
        self.assertEqual(len(transfer_records), 1)

    def test_subscription_test_command_prints_exact_match_contract(self) -> None:
        env = os.environ.copy()
        env.pop("P115_COOKIES", None)
        completed = subprocess.run(
            [
                sys.executable,
                "main.py",
                "subscription-test",
                "--pattern",
                "S\\d{2}E\\d{2}",
                "--text",
                "Show S01E02",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout,
            "matched=true\trule_id=\trule_name=Ad hoc\tmatched_keywords=S\\d{2}E\\d{2}\n",
        )

    def test_subscription_process_command_prints_exact_summary_contract_without_cookies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env.pop("P115_COOKIES", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "subscription-process",
                    "--limit",
                    "100",
                    "--db-path",
                    str(Path(tmp_dir) / "queue.db"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        parts = dict(part.split("=", 1) for part in completed.stdout.strip().split("\t"))
        self.assertEqual(set(parts), {"scanned", "matched", "created", "skipped", "errors"})


if __name__ == "__main__":
    unittest.main()
