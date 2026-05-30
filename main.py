from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.collectors import TelegramWebCollector, parse_115_shares
from src.collectors.telegram_web import parse_telegram_public_channel_html
from src.config import AppSettings
from src.logging_config import setup_logging
from src.notifications import InMemoryNotifier
from src.organizing import OrganizeMetadata, OrganizeRule, TmdbConfig, TmdbMovieResolver, TmdbMultiResolver, build_organize_plans
from src.processors.dry_run_backend import DryRunBackendService
from src.processors.fakes import FakeMetadataResolver, FakeOrganizeStorage, FakeTransferStorage
from src.processors.organize_run import OrganizeRunService
from src.processors.subscription_processor import SubscriptionProcessor
from src.processors.telegram_collection import TelegramCollectionResult, TelegramCollectionService
from src.queue.repository import QueueRepository
from src.organizing.repository import OrganizeRepository
from src.runtime import RuntimeFactory
from src.runtime.event_runtime import EventDrivenRuntime
from src.storage import Storage115Service
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule
from src.subscriptions.repository import SubscriptionRepository, SubscriptionRuleRecord
from src.subscriptions.service import SubscriptionRuleNotFoundError, SubscriptionService, SubscriptionTestResult



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="115 resource center command line")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_share_text = subparsers.add_parser("parse-share-text", help="Parse 115 share links from text")
    parse_share_text.add_argument("text")

    collect_tg_web_history = subparsers.add_parser(
        "collect-tg-web-history",
        help="Collect 115 share links from a public Telegram channel web page",
    )
    collect_tg_web_history.add_argument("channel")
    collect_tg_web_history.add_argument("--limit", type=int, default=20)
    collect_tg_web_history.add_argument("--html-file", default="")

    collect_tg_web_incremental = subparsers.add_parser(
        "collect-tg-web-incremental",
        help="Collect new 115 share links from a public Telegram channel web page",
    )
    collect_tg_web_incremental.add_argument("channel")
    collect_tg_web_incremental.add_argument("--limit", type=int, default=20)
    collect_tg_web_incremental.add_argument("--html-file", default="")
    collect_tg_web_incremental.add_argument("--db-path", default="queue.db")

    tg_collector_status = subparsers.add_parser(
        "tg-collector-status",
        help="Show Telegram web collector cursor status",
    )
    tg_collector_status.add_argument("channel")
    tg_collector_status.add_argument("--db-path", default="queue.db")

    plan_organize_json = subparsers.add_parser(
        "plan-organize-json",
        help="Build offline organize plans from a local JSON item list",
    )
    plan_organize_json.add_argument("items_json_file")
    plan_organize_json.add_argument("--media-library-root-cid", type=int, required=True)

    organize_run_once = subparsers.add_parser(
        "organize-run-once",
        help="Run one organize scan against the staging folder",
    )
    organize_run_once.add_argument("--db-path", default="queue.db")
    organize_run_once.add_argument("--staging-cid", type=int, default=None)
    organize_run_once.add_argument("--media-library-root-cid", type=int, required=True)

    resolve_tmdb_movie = subparsers.add_parser(
        "resolve-tmdb-movie",
        help="Resolve movie metadata from TMDB",
    )
    resolve_tmdb_movie.add_argument("query")
    resolve_tmdb_movie.add_argument("--year", type=int, default=None)
    resolve_tmdb_movie.add_argument("--json-file", default="")

    resolve_tmdb_multi = subparsers.add_parser(
        "resolve-tmdb-multi",
        help="Resolve movie or TV metadata from TMDB",
    )
    resolve_tmdb_multi.add_argument("query")
    resolve_tmdb_multi.add_argument("--year", type=int, default=None)
    resolve_tmdb_multi.add_argument("--json-file", default="")

    dry_run_backend = subparsers.add_parser(
        "dry-run-backend",
        help="Run the offline dry-run backend against local JSON messages",
    )
    dry_run_backend.add_argument("--messages-json", required=True)
    dry_run_backend.add_argument("--db-file", required=True)
    dry_run_backend.add_argument("--staging-cid", type=int, default=0)
    dry_run_backend.add_argument("--include-keyword", default="Movie")

    subscription_list = subparsers.add_parser("subscription-list", help="List subscription rules")
    subscription_list.add_argument("--db-path", default="queue.db")

    subscription_create = subparsers.add_parser("subscription-create", help="Create a subscription rule")
    subscription_create.add_argument("--name", required=True)
    subscription_create.add_argument("--pattern", required=True)
    subscription_create.add_argument("--disabled", action="store_true")
    subscription_create.add_argument("--db-path", default="queue.db")

    subscription_enable = subparsers.add_parser("subscription-enable", help="Enable a subscription rule")
    subscription_enable.add_argument("rule_id", type=int)
    subscription_enable.add_argument("--db-path", default="queue.db")

    subscription_disable = subparsers.add_parser("subscription-disable", help="Disable a subscription rule")
    subscription_disable.add_argument("rule_id", type=int)
    subscription_disable.add_argument("--db-path", default="queue.db")

    subscription_delete = subparsers.add_parser("subscription-delete", help="Delete a subscription rule")
    subscription_delete.add_argument("rule_id", type=int)
    subscription_delete.add_argument("--db-path", default="queue.db")

    subscription_test = subparsers.add_parser("subscription-test", help="Test a subscription rule or pattern")
    subscription_test.add_argument("--rule-id", type=int, default=None)
    subscription_test.add_argument("--pattern", default="")
    subscription_test.add_argument("--text", required=True)
    subscription_test.add_argument("--db-path", default="queue.db")

    subscription_process = subparsers.add_parser(
        "subscription-process",
        help="Process collected shares into transfer queue",
    )
    subscription_process.add_argument("--limit", type=int, default=100)
    subscription_process.add_argument("--db-path", default="queue.db")

    runtime_status = subparsers.add_parser("runtime-status", help="Show runtime desired/effective state and component status")
    runtime_status.add_argument("--db-path", default="queue.db")

    runtime_start = subparsers.add_parser("runtime-start", help="Persist runtime start intent")
    runtime_start.add_argument("--db-path", default="queue.db")

    runtime_stop = subparsers.add_parser("runtime-stop", help="Persist runtime stop intent")
    runtime_stop.add_argument("--db-path", default="queue.db")

    runtime_worker = subparsers.add_parser("runtime-worker", help="Run runtime worker loop")
    runtime_worker.add_argument("--db-path", default="queue.db")
    runtime_worker.add_argument("--once", action="store_true")
    runtime_worker.add_argument("--max-ticks", type=int, default=None)
    runtime_worker.add_argument("--tick-seconds", type=int, default=None, help="tick 间隔秒；每 tick 认领手动触发（影响手动触发响应延迟）")
    runtime_worker.add_argument("--sweep-seconds", type=int, default=None, help="兜底轮询间隔秒；完整跑收集+转存+整理的兜底（默认 3600）")

    list_share = subparsers.add_parser("list-share", help="List files in a 115 share")

    list_share.add_argument("share_code")
    list_share.add_argument("receive_code", nargs="?", default="")

    save_share = subparsers.add_parser("save-share", help="Receive all top-level share files")
    save_share.add_argument("share_code")
    save_share.add_argument("receive_code", nargs="?", default="")
    save_share.add_argument("--target-cid", type=int, default=None)

    list_folder = subparsers.add_parser("list-folder", help="List files in a 115 folder")
    list_folder.add_argument("cid", nargs="?", type=int, default=0)

    return parser


def _metadata_from_item(item: dict) -> OrganizeMetadata | None:
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        return OrganizeMetadata(
            title=str(metadata["title"]),
            year=metadata.get("year"),
            kind=str(metadata["kind"]),
            season=metadata.get("season"),
            episode=metadata.get("episode"),
            region_primary=_optional_str(metadata.get("region_primary")),
            region_candidates=_tuple_of_strings(metadata.get("region_candidates")),
            region_category=_optional_str(metadata.get("region_category")),
            region_source=_optional_str(metadata.get("region_source")),
            region_confidence=str(metadata.get("region_confidence", "low")),
        )
    if "title" in item and "kind" in item:
        return OrganizeMetadata(
            title=str(item["title"]),
            year=item.get("year"),
            kind=str(item["kind"]),
            region_primary=_optional_str(item.get("region_primary")),
            region_candidates=_tuple_of_strings(item.get("region_candidates")),
            region_category=_optional_str(item.get("region_category")),
            region_source=_optional_str(item.get("region_source")),
            region_confidence=str(item.get("region_confidence", "low")),
        )
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _load_organize_items(path: Path) -> tuple[list[dict], dict[int, OrganizeMetadata]]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("items_json_file must contain a JSON list")

    metadata_by_file_id: dict[int, OrganizeMetadata] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("items_json_file list entries must be JSON objects")
        metadata = _metadata_from_item(item)
        if metadata is not None:
            metadata_by_file_id[int(item["id"])] = metadata
    return items, metadata_by_file_id


class _FakeTmdbResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class _FakeTmdbClient:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        if isinstance(payload, list):
            self._responses = [_FakeTmdbResponse(item, status_code=status_code) for item in payload]
        else:
            self._responses = [_FakeTmdbResponse(payload, status_code=status_code)]

    def get(self, _url: str, *, headers: dict[str, str], params: dict[str, Any]) -> _FakeTmdbResponse:
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def _print_movie_metadata(metadata: OrganizeMetadata | None) -> None:
    if metadata is None:
        return
    values = [
        metadata.title,
        "" if metadata.year is None else str(metadata.year),
        metadata.kind,
    ]
    if metadata.region_primary is not None or metadata.region_candidates:
        values.extend(
            [
                metadata.region_primary or "",
                ",".join(metadata.region_candidates),
                metadata.region_category or "",
                metadata.region_source or "",
                metadata.region_confidence,
            ]
        )
    print("\t".join(values))


def _resolve_tmdb_movie(args: argparse.Namespace) -> None:
    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        resolver = TmdbMovieResolver(
            TmdbConfig(bearer_token="offline-test-token", language=""),
            client=_FakeTmdbClient(payload),
        )
        _print_movie_metadata(resolver.resolve_movie(args.query, year=args.year))
        return

    tmdb_token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    if not tmdb_token:
        print("TMDB_BEARER_TOKEN is required for resolve-tmdb-movie", file=sys.stderr)
        raise SystemExit(2)

    settings = AppSettings.from_yaml()
    if settings.tmdb is None:
        print("TMDB_BEARER_TOKEN is required for resolve-tmdb-movie", file=sys.stderr)
        raise SystemExit(2)

    resolver = TmdbMovieResolver(settings.tmdb)
    _print_movie_metadata(resolver.resolve_movie(args.query, year=args.year))


def _resolve_tmdb_multi(args: argparse.Namespace) -> None:
    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        resolver = TmdbMultiResolver(
            TmdbConfig(bearer_token="offline-test-token", language=""),
            client=_FakeTmdbClient(payload),
        )
        _print_movie_metadata(resolver.resolve_multi(args.query, year=args.year))
        return

    tmdb_token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    if not tmdb_token:
        print("TMDB_BEARER_TOKEN is required for resolve-tmdb-multi", file=sys.stderr)
        raise SystemExit(2)

    settings = AppSettings.from_yaml()
    if settings.tmdb is None:
        print("TMDB_BEARER_TOKEN is required for resolve-tmdb-multi", file=sys.stderr)
        raise SystemExit(2)

    resolver = TmdbMultiResolver(settings.tmdb)
    _print_movie_metadata(resolver.resolve_multi(args.query, year=args.year))


def _load_dry_run_messages(path: Path) -> list[dict[str, Any]]:
    messages = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(messages, list):
        raise ValueError("messages-json must contain a JSON list")
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("messages-json list entries must be JSON objects")
    return messages


def _run_dry_run_backend(args: argparse.Namespace) -> None:
    messages = _load_dry_run_messages(Path(args.messages_json))
    repository = QueueRepository(Path(args.db_file))
    repository.init_schema()
    notifier = InMemoryNotifier()
    service = DryRunBackendService(
        repository=repository,
        matcher=SubscriptionMatcher(
            [
                SubscriptionRule(
                    id="dry-run",
                    name="Dry Run",
                    pattern=args.include_keyword,
                )
            ]
        ),
        transfer_storage=FakeTransferStorage(),
        organize_storage=FakeOrganizeStorage(items=[{"id": 31, "name": "raw.mkv", "is_dir": False}]),
        metadata_resolver=FakeMetadataResolver({31: OrganizeMetadata(title="Movie", year=2024, kind="movie")}),
        organize_rule=OrganizeRule(media_library_root_cid=100),
        notifier=notifier,
        staging_cid=args.staging_cid,
    )
    summary = service.run_messages(messages)
    values = {
        "collect_enqueued": summary.collect_enqueued,
        "collect_processed": summary.collect_processed,
        "transfer_processed": summary.transfer_processed,
        "organize_moved": summary.organize_moved,
        "notification_count": summary.notification_count,
        "errors": ",".join(summary.errors),
    }
    print("\t".join(f"{key}={value}" for key, value in values.items()))


def _subscription_service(db_path: str) -> SubscriptionService:
    queue_repository = QueueRepository(Path(db_path))
    queue_repository.init_schema()
    subscription_repository = SubscriptionRepository(Path(db_path))
    subscription_repository.init_schema()
    return SubscriptionService(subscription_repository)


def _print_subscription_rule(record: SubscriptionRuleRecord) -> None:
    print(
        "\t".join(
            [
                f"id={record.id}",
                f"name={record.name}",
                f"pattern={record.pattern}",
                f"enabled={str(record.enabled).lower()}",
            ]
        )
    )


def _print_subscription_test_result(result: SubscriptionTestResult) -> None:
    values = [
        f"matched={str(result.matched).lower()}",
        f"rule_id={'' if result.rule_id is None else result.rule_id}",
        f"rule_name={'' if result.rule_name is None else result.rule_name}",
        f"matched_keywords={','.join(result.matched_keywords)}",
    ]
    print("\t".join(values))


def _handle_subscription_error(exc: Exception) -> None:
    if isinstance(exc, SubscriptionRuleNotFoundError):
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    if isinstance(exc, ValueError):
        print(f"invalid subscription pattern: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise exc


def _run_subscription_list(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    for record in service.list_rules():
        _print_subscription_rule(record)


def _run_subscription_create(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    try:
        _print_subscription_rule(
            service.create_rule(name=args.name, pattern=args.pattern, enabled=not args.disabled)
        )
    except Exception as exc:
        _handle_subscription_error(exc)


def _run_subscription_enable(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    try:
        _print_subscription_rule(service.enable_rule(args.rule_id))
    except Exception as exc:
        _handle_subscription_error(exc)


def _run_subscription_disable(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    try:
        _print_subscription_rule(service.disable_rule(args.rule_id))
    except Exception as exc:
        _handle_subscription_error(exc)


def _run_subscription_delete(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    deleted = service.delete_rule(args.rule_id)
    print(f"deleted={str(deleted).lower()}\tid={args.rule_id}")


def _run_subscription_test(args: argparse.Namespace) -> None:
    service = _subscription_service(args.db_path)
    try:
        if args.rule_id is not None:
            result = service.test_match(args.rule_id, args.text)
        elif args.pattern:
            result = service.test_pattern(pattern=args.pattern, text=args.text)
        else:
            print("subscription-test requires --rule-id or --pattern", file=sys.stderr)
            raise SystemExit(2)
        _print_subscription_test_result(result)
    except Exception as exc:
        _handle_subscription_error(exc)


def _run_subscription_process(args: argparse.Namespace) -> None:
    queue_repository = QueueRepository(Path(args.db_path))
    queue_repository.init_schema()
    subscription_repository = SubscriptionRepository(Path(args.db_path))
    subscription_repository.init_schema()
    processor = SubscriptionProcessor(
        queue_repository=queue_repository,
        subscription_repository=subscription_repository,
        staging_cid=AppSettings.from_yaml().transfer_cid or None,
    )
    summary = processor.process(limit=args.limit)
    values = {
        "scanned": summary.scanned,
        "matched": summary.matched,
        "created": summary.created,
        "skipped": summary.skipped,
        "errors": ",".join(summary.errors),
    }
    print("\t".join(f"{key}={value}" for key, value in values.items()))


def _runtime_factory_from_args(args: argparse.Namespace) -> RuntimeFactory:
    return RuntimeFactory(db_path=Path(args.db_path), settings=AppSettings.from_yaml())


def _print_runtime_status(status: Any) -> None:
    queue_counts = getattr(status, "queue_counts", None)
    collect_counts = getattr(queue_counts, "collect_queue", {}) if queue_counts is not None else {}
    transfer_counts = getattr(queue_counts, "transfer_queue", {}) if queue_counts is not None else {}
    organizer = getattr(status, "organizer", None)
    organizer_counts = getattr(organizer, "counts", {}) if organizer is not None else {}
    components = getattr(status, "components", []) or []
    component_summary = ",".join(f"{component.name}:{component.status}" for component in components)
    print(
        "\t".join(
            [
                f"desired_state={status.desired_state}",
                f"effective_state={status.effective_state}",
                f"control_plane_only={str(status.control_plane_only).lower()}",
                f"collect_pending={int(collect_counts.get('PENDING', 0))}",
                f"transfer_pending={int(transfer_counts.get('PENDING', 0))}",
                f"organizer_running={int(organizer_counts.get('RUNNING', 0))}",
                f"components={component_summary}",
            ]
        )
    )


def _print_runtime_control_result(result: Any) -> None:
    _print_runtime_status(result)
    print(f"action={result.action}\tchanged={str(result.changed).lower()}")


def _print_runtime_tick_result(result: Any) -> None:
    print(
        "\t".join(
            [
                f"core={result.core}",
                f"status={result.status}",
                f"processed={result.processed}",
                f"succeeded={result.succeeded}",
                f"skipped={result.skipped}",
                f"failed={result.failed}",
                f"error={result.error or ''}",
            ]
        )
    )


def _run_runtime_status(args: argparse.Namespace) -> None:
    factory = _runtime_factory_from_args(args)
    _print_runtime_status(factory.build_runtime_control_service().status())


def _run_runtime_start(args: argparse.Namespace) -> None:
    factory = _runtime_factory_from_args(args)
    _print_runtime_control_result(factory.build_runtime_control_service().start())


def _run_runtime_stop(args: argparse.Namespace) -> None:
    factory = _runtime_factory_from_args(args)
    _print_runtime_control_result(factory.build_runtime_control_service().stop())


def _run_runtime_worker(args: argparse.Namespace) -> None:
    factory = _runtime_factory_from_args(args)
    runtime = EventDrivenRuntime(factory=factory)
    settings = getattr(factory, "settings", None)
    if settings is not None and hasattr(settings, "rank_refresh_interval_seconds"):
        runtime._rank_refresh_interval_seconds = settings.rank_refresh_interval_seconds
    if args.tick_seconds is not None:
        runtime._interval_seconds = args.tick_seconds
    if args.sweep_seconds is not None:
        runtime._sweep_interval_seconds = args.sweep_seconds
    results = runtime.run_once() if args.once else runtime.run_until_stopped(max_ticks=args.max_ticks)
    for result in results:
        _print_runtime_tick_result(result)
    ticks_value = 1 if args.once else (args.max_ticks if args.max_ticks is not None else "")
    print(f"ticks={ticks_value}\tresult_count={len(results)}")

def _run_organize_once(args: argparse.Namespace) -> None:
    settings = AppSettings.from_yaml()
    if settings.p115 is None:
        print("P115_COOKIES is required for organize-run-once", file=sys.stderr)
        raise SystemExit(2)
    if settings.tmdb is None:
        print("TMDB_BEARER_TOKEN is required for organize-run-once", file=sys.stderr)
        raise SystemExit(2)

    staging_cid = args.staging_cid if args.staging_cid is not None else settings.transfer_cid
    repository = OrganizeRepository(Path(args.db_path))
    repository.init_schema()
    storage = Storage115Service(settings.p115)
    tmdb_resolver = TmdbMultiResolver(settings.tmdb)
    service = OrganizeRunService(
        repository=repository,
        storage=storage,
        rule=OrganizeRule(
            media_library_root_cid=args.media_library_root_cid,
        ),
        metadata_resolver=lambda item: tmdb_resolver.resolve_multi(str(_get_item_name(item))),
    )
    result = service.run_once(staging_cid)
    print(
        "\t".join(
            [
                f"run_id={result.run_id}",
                f"status={result.status}",
                f"scanned={result.scanned_count}",
                f"planned={result.planned_count}",
                f"moved={result.success_count}",
                f"errors={result.failed_count}",
            ]
        )
    )


def _get_item_name(item: Any) -> Any:
    if isinstance(item, dict):
        return item.get("name", "")
    return getattr(item, "name", "")



def _build_telegram_fetcher(html_file: str):

    if not html_file:
        return None

    html_path = Path(html_file)

    def fetch_html_file(_url: str) -> str:
        return html_path.read_text(encoding="utf-8")

    return fetch_html_file


class _TelegramWebMessageFetcher:
    def __init__(self, *, html_file: str, limit: int) -> None:
        self._html_file = html_file
        self._limit = limit

    def fetch_messages(self, source_id: str, cursor: int | None = None):
        normalized_source_id = source_id.strip().lstrip("@")
        if self._html_file:
            html = Path(self._html_file).read_text(encoding="utf-8")
        else:
            url = f"https://t.me/s/{quote(normalized_source_id)}?limit={self._limit}"
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=30) as response:
                html = response.read().decode("utf-8", errors="replace")
        return parse_telegram_public_channel_html(str(html), normalized_source_id)


class _QueueRepositoryCollectionAdapter:
    def __init__(self, repository: QueueRepository) -> None:
        self._repository = repository

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    @property
    def enqueued(self) -> dict[tuple[str, str, str], object]:
        return {
            (record.source_type, record.source_id, record.message_id): record
            for record in self._repository.list_collect_queue()
        }


def _status_for_cli(status: str | None) -> str:
    return (status or "unknown").lower()


def _print_telegram_collection_result(result: TelegramCollectionResult) -> None:
    print(
        "\t".join(
            [
                f"source_type={result.source_type}",
                f"source_id={result.source_id}",
                f"scanned={result.scanned}",
                f"parsed_shares={result.parsed_shares}",
                f"enqueued={result.enqueued}",
                f"skipped_existing={result.skipped_existing}",
                f"cursor={'' if result.cursor is None else result.cursor}",
                f"status={_status_for_cli(result.status)}",
            ]
        )
    )


def _run_collect_tg_web_incremental(args: argparse.Namespace) -> None:
    repository = QueueRepository(Path(args.db_path))
    repository.init_schema()
    source_id = args.channel.strip().lstrip("@")
    service = TelegramCollectionService(
        repository=_QueueRepositoryCollectionAdapter(repository),
        fetcher=_TelegramWebMessageFetcher(html_file=args.html_file, limit=args.limit),
        source_type="telegram_web",
        source_id=source_id,
    )
    _print_telegram_collection_result(service.poll_once())


def _run_tg_collector_status(args: argparse.Namespace) -> None:
    repository = QueueRepository(Path(args.db_path))
    repository.init_schema()
    source_id = args.channel.strip().lstrip("@")
    cursor = repository.get_collector_cursor(source_type="telegram_web", source_id=source_id)
    print(
        "\t".join(
            [
                "source_type=telegram_web",
                f"source_id={source_id}",
                f"cursor={cursor.last_seen_message_id if cursor is not None and cursor.last_seen_message_id is not None else ''}",
                f"last_status={_status_for_cli(cursor.last_status if cursor is not None else None)}",
                f"last_error={cursor.last_error if cursor is not None and cursor.last_error is not None else ''}",
            ]
        )
    )


def main() -> None:
    args = build_parser().parse_args()

    setup_logging(console_level=logging.WARNING)

    if args.command == "parse-share-text":
        for share in parse_115_shares(args.text):
            print(f"{share.share_code}\t{share.receive_code}\t{share.share_url}")
        return

    if args.command == "collect-tg-web-history":
        collector = TelegramWebCollector(fetcher=_build_telegram_fetcher(args.html_file))
        shares = asyncio.run(collector.collect_history(args.channel, limit=args.limit))
        for share in shares:
            print(
                f"{share.source_type}\t{share.source_id}\t{share.message_id}\t"
                f"{share.share_code}\t{share.receive_code}\t{share.share_url}"
            )
        return

    if args.command == "collect-tg-web-incremental":
        _run_collect_tg_web_incremental(args)
        return

    if args.command == "tg-collector-status":
        _run_tg_collector_status(args)
        return

    if args.command == "plan-organize-json":
        items, metadata_by_file_id = _load_organize_items(Path(args.items_json_file))
        rule = OrganizeRule(
            media_library_root_cid=args.media_library_root_cid,
        )
        for plan in build_organize_plans(items, metadata_by_file_id, rule):
            print(
                f"{plan.file_id}\t{plan.original_name}\t{plan.new_name}\t"
                f"{plan.target_parent_cid}\t{plan.target_folder_name}"
            )
        return

    if args.command == "resolve-tmdb-movie":
        _resolve_tmdb_movie(args)
        return

    if args.command == "resolve-tmdb-multi":
        _resolve_tmdb_multi(args)
        return

    if args.command == "dry-run-backend":
        _run_dry_run_backend(args)
        return

    if args.command == "subscription-list":
        _run_subscription_list(args)
        return

    if args.command == "subscription-create":
        _run_subscription_create(args)
        return

    if args.command == "subscription-enable":
        _run_subscription_enable(args)
        return

    if args.command == "subscription-disable":
        _run_subscription_disable(args)
        return

    if args.command == "subscription-delete":
        _run_subscription_delete(args)
        return

    if args.command == "subscription-test":
        _run_subscription_test(args)
        return

    if args.command == "subscription-process":
        _run_subscription_process(args)
        return

    if args.command == "runtime-status":
        _run_runtime_status(args)
        return

    if args.command == "runtime-start":
        _run_runtime_start(args)
        return

    if args.command == "runtime-stop":
        _run_runtime_stop(args)
        return

    if args.command == "runtime-worker":
        _run_runtime_worker(args)
        return

    if args.command == "organize-run-once":
        _run_organize_once(args)
        return

    settings = AppSettings.from_yaml()

    service = Storage115Service(settings.p115)

    if args.command == "list-share":
        for item in service.list_share(args.share_code, args.receive_code):
            print(f"{item.id}\t{'DIR' if item.is_dir else 'FILE'}\t{item.name}")
    elif args.command == "save-share":
        target_cid = args.target_cid if args.target_cid is not None else settings.transfer_cid
        print(service.save_share(args.share_code, args.receive_code, target_cid=target_cid))
    elif args.command == "list-folder":
        for item in service.list_folder(args.cid):
            print(f"{item.id}\t{'DIR' if item.is_dir else 'FILE'}\t{item.name}")


if __name__ == "__main__":
    main()
