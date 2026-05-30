"""统一日志配置

提供三种日志输出方式：
1. 控制台输出
2. 文件输出（保存到根目录 logs/ 目录）
3. 内存缓存（供前端 API 读取）
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 内存日志缓存（最多保留最近 1000 条）
_log_buffer: list[dict[str, Any]] = []
_MAX_LOG_BUFFER_SIZE = 1000

# 文件日志行格式：2026-05-30 01:25:26 [INFO] logger.name [module.func:42] - message
_LOG_LINE_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>\w+)\] "
    r"(?P<logger>\S+) "
    r"\[(?P<module>[^.\]]+)\.(?P<function>[^:\]]+):(?P<line>\d+)\] - "
    r"(?P<message>.*)$"
)


def _log_dir() -> Path:
    return Path("logs")


def _current_log_file() -> Path:
    return _log_dir() / f"app_{datetime.now().strftime('%Y%m%d')}.log"


def parse_log_lines(lines: list[str]) -> list[dict[str, Any]]:
    """把日志文件的原始行解析为结构化条目。

    无法匹配行首格式的行（如 traceback 续行）会被并入上一条目的 message。
    """
    entries: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        match = _LOG_LINE_PATTERN.match(line)
        if match is None:
            if entries:
                entries[-1]["message"] += "\n" + line
            continue
        groups = match.groupdict()
        entries.append(
            {
                "timestamp": groups["timestamp"],
                "level": groups["level"],
                "logger": groups["logger"],
                "message": groups["message"],
                "module": groups["module"],
                "function": groups["function"],
                "line": int(groups["line"]),
            }
        )
    return entries


def read_log_entries(log_file: Path | None = None) -> list[dict[str, Any]]:
    """读取并解析当天日志文件的全部结构化条目；文件不存在时返回空列表。"""
    path = log_file if log_file is not None else _current_log_file()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        lines = handle.readlines()
    return parse_log_lines(lines)


class MemoryLogHandler(logging.Handler):
    """内存日志处理器，缓存日志供前端读取"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }

            _log_buffer.append(log_entry)

            # 保持缓冲区大小
            if len(_log_buffer) > _MAX_LOG_BUFFER_SIZE:
                _log_buffer.pop(0)

        except Exception:
            self.handleError(record)


def setup_logging(
    log_dir: str | Path = "logs",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> None:
    """配置日志系统

    Args:
        log_dir: 日志文件目录
        console_level: 控制台日志级别
        file_level: 文件日志级别
    """
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 日志文件名（按日期）
    log_file = log_path / f"app_{datetime.now().strftime('%Y%m%d')}.log"

    # 日志格式
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s [%(module)s.%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 1. 控制台处理器（输出到 stderr，避免污染 CLI 命令的 stdout 业务输出）
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 3. 内存处理器（供前端读取）
    memory_handler = MemoryLogHandler()
    memory_handler.setLevel(logging.DEBUG)
    memory_handler.setFormatter(file_formatter)
    root_logger.addHandler(memory_handler)

    # 设置第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    root_logger.info("=" * 80)
    root_logger.info("日志系统已初始化")
    root_logger.info(f"日志文件: {log_file.absolute()}")
    root_logger.info(f"控制台级别: {logging.getLevelName(console_level)}")
    root_logger.info(f"文件级别: {logging.getLevelName(file_level)}")
    root_logger.info("=" * 80)


def get_recent_logs(limit: int = 100, level: str | None = None) -> list[dict[str, Any]]:
    """获取最近的日志记录（从当天日志文件读取，跨进程共享）

    Args:
        limit: 返回的最大日志条数
        level: 过滤日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）

    Returns:
        日志记录列表
    """
    logs = read_log_entries()

    # 按级别过滤
    if level:
        logs = [log for log in logs if log["level"] == level.upper()]

    # 返回最近的 N 条
    return logs[-limit:]


def clear_log_buffer() -> None:
    """清空内存日志缓存"""
    _log_buffer.clear()


__all__ = [
    "setup_logging",
    "get_recent_logs",
    "clear_log_buffer",
    "parse_log_lines",
    "read_log_entries",
    "_current_log_file",
    "_log_buffer",
]
