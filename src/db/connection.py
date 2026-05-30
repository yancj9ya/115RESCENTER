from __future__ import annotations

import sqlite3
from pathlib import Path

_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA foreign_keys=ON",
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    """统一的 SQLite 连接入口：开启 WAL、busy_timeout、外键约束。

    WAL 让读写并发不互相阻塞（API 进程与常驻 worker 进程同时访问同一库时尤其重要）；
    busy_timeout 在拿不到锁时自动重试而非立即抛 ``database is locked``。
    """
    connection = sqlite3.connect(db_path)
    for pragma in _PRAGMAS:
        connection.execute(pragma)
    return connection
