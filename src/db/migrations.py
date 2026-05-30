from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from .connection import connect

Migration = Callable[[sqlite3.Connection], None]


def _migration_v1(connection: sqlite3.Connection) -> None:
    """基线 schema：纳入重构前已存在的全部表/索引/种子行。

    全部使用 ``IF NOT EXISTS`` / ``INSERT OR IGNORE``，对已存在的旧库重跑安全——
    这样老的 queue.db（user_version=0 但表已建）升到 v1 时不会报错。
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS collect_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            message_url TEXT,
            message_text TEXT NOT NULL,
            published_at TEXT,
            shares_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_type, source_id, message_id)
        );

        CREATE TABLE IF NOT EXISTS transfer_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_code TEXT NOT NULL,
            receive_code TEXT NOT NULL DEFAULT '',
            share_url TEXT NOT NULL,
            staging_cid INTEGER NOT NULL,
            matched_rules_json TEXT NOT NULL DEFAULT '[]',
            source_messages_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(share_url, staging_cid)
        );

        CREATE TABLE IF NOT EXISTS collector_cursors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            last_seen_message_id TEXT,
            last_poll_at TEXT,
            last_status TEXT NOT NULL,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_type, source_id)
        );

        CREATE TABLE IF NOT EXISTS subscription_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            tmdb_id INTEGER,
            tmdb_kind TEXT,
            aliases_json TEXT,
            poster_path TEXT
        );

        CREATE TABLE IF NOT EXISTS organize_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staging_cid INTEGER NOT NULL,
            status TEXT NOT NULL,
            planned_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS organize_run_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            is_dir INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            target_cid INTEGER,
            target_path TEXT,
            new_name TEXT,
            reason TEXT,
            error TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES organize_runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_organize_runs_status_id
            ON organize_runs(status, id);
        CREATE INDEX IF NOT EXISTS idx_organize_run_items_run_id_id
            ON organize_run_items(run_id, id);

        CREATE TABLE IF NOT EXISTS runtime_control (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            desired_state TEXT NOT NULL,
            started_at TEXT,
            stopped_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS runtime_components (
            name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            configured INTEGER NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            success INTEGER,
            error TEXT,
            tick_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS runtime_worker_heartbeats (
            worker_name TEXT PRIMARY KEY,
            component_name TEXT NOT NULL,
            status TEXT NOT NULL,
            pid INTEGER,
            error TEXT,
            heartbeat_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT OR IGNORE INTO runtime_control (id, desired_state, stopped_at)
        VALUES (1, 'stopped', CURRENT_TIMESTAMP);

        CREATE TABLE IF NOT EXISTS telegram_web_channels (
            channel TEXT PRIMARY KEY,
            display_name TEXT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            poll_interval_seconds INTEGER NOT NULL DEFAULT 1800,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _backfill_columns(
        connection,
        "subscription_rules",
        (
            ("tmdb_id", "INTEGER"),
            ("tmdb_kind", "TEXT"),
            ("aliases_json", "TEXT"),
            ("poster_path", "TEXT"),
        ),
    )


def _backfill_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[tuple[str, str], ...],
) -> None:
    """对已存在的老表补齐缺失的列（等价于重构前散落的动态 ALTER）。

    ``CREATE TABLE IF NOT EXISTS`` 不会修改已存在的表，所以从只有基础列的旧库
    升级时，要在这里把后来追加的列补上。
    """
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, column_type in columns:
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

def _migration_v2(connection: sqlite3.Connection) -> None:
    """手动触发跨进程桥：前端经 API 写入待处理触发，常驻 worker 每个 tick 拉取并转成进程内事件。

    事件总线是进程内的，API 进程发布不到 worker 进程的总线；DB 才是跨进程真相。
    一行=一次待处理的手动触发；worker 认领后置 consumed_at，避免重复触发。
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS runtime_manual_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'api',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consumed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runtime_manual_triggers_pending
            ON runtime_manual_triggers(consumed_at, id);
        """
    )


def _migration_v3(connection: sqlite3.Connection) -> None:
    """榜单缓存：后台每隔数小时刷新腾讯频道榜与 TMDB 榜单，整榜序列化后落库。

    前端只读这张表，避免实时抓取 + 逐项 TMDB 反查的等待。
    一行=一个榜单（source+key 复合主键），``items_json`` 存整榜 enriched 条目数组。
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rank_cache (
            source TEXT NOT NULL,
            key TEXT NOT NULL,
            items_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'ok',
            error TEXT,
            refreshed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source, key)
        );
        """
    )


# 顺序即版本：索引 0 -> 升到 user_version 1，索引 1 -> 升到 2 ...
_MIGRATIONS: tuple[Migration, ...] = (_migration_v1, _migration_v2, _migration_v3)


def migrate(db_path: str | Path) -> int:
    """把库升级到最新 schema 版本，返回升级后的 user_version。

    幂等：已是最新版本时不做任何事。基于 ``PRAGMA user_version`` 追踪进度，
    每个迁移在独立事务中执行，失败回滚且不推进版本号。
    """
    connection = connect(db_path)
    try:
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        target = len(_MIGRATIONS)
        for version in range(current, target):
            migration = _MIGRATIONS[version]
            try:
                migration(connection)
                connection.execute(f"PRAGMA user_version = {version + 1}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()
