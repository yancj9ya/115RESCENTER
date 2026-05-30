from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import INFO, ORGANIZE_SUCCESS, TRANSFER_SUCCESS, NotificationEvent


class NotificationProvider(Protocol):
    name: str

    def notify(self, event: NotificationEvent) -> None:
        ...


@dataclass(frozen=True)
class OrganizeItemSummary:
    """整理成功的单条入库记录，用于按 tmdb_id 汇总成一条通知。"""

    tmdb_id: int | None
    title: str
    season: int | None = None
    episode: int | None = None


class NotificationService:
    """通知工具类（无状态可复用）：按核心名分流到对应 provider，单 provider 失败隔离。"""

    def __init__(
        self,
        *,
        providers: list[NotificationProvider],
        routing: dict[str, list[str]],
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._routing = routing

    def notify(self, source: str, event: NotificationEvent) -> None:
        for provider_name in self._routing.get(source, []):
            provider = self._providers.get(provider_name)
            if provider is None:
                continue
            try:
                provider.notify(event)
            except Exception:
                # 单 provider 失败不影响其他 provider
                continue


def _format_episodes(episodes: list[int]) -> str:
    unique = sorted({ep for ep in episodes if ep is not None})
    if not unique:
        return ""
    runs: list[tuple[int, int]] = []
    start = prev = unique[0]
    for value in unique[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append((start, prev))
        start = prev = value
    runs.append((start, prev))
    parts = [f"E{lo}" if lo == hi else f"E{lo}-E{hi}" for lo, hi in runs]
    return ", ".join(parts)


def build_organize_summary(items: list[OrganizeItemSummary]) -> NotificationEvent | None:
    """把同一 tmdb_id 的多集合并成一行（如 "逐玉 入库 E1-E10"），整批一条通知。"""
    if not items:
        return None

    grouped: dict[object, list[OrganizeItemSummary]] = {}
    order: list[object] = []
    for item in items:
        key = item.tmdb_id if item.tmdb_id is not None else item.title
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)

    lines: list[str] = []
    for key in order:
        group = grouped[key]
        title = group[0].title
        episodes = [item.episode for item in group if item.episode is not None]
        episode_text = _format_episodes(episodes)
        if episode_text:
            lines.append(f"{title} 入库 {episode_text}")
        else:
            lines.append(f"{title} 入库")

    return NotificationEvent(
        event_type=ORGANIZE_SUCCESS,
        severity=INFO,
        title="整理入库完成",
        message="\n".join(lines),
    )


def build_transfer_summary(*, succeeded: int, failed: int) -> NotificationEvent | None:
    """转存整批跑完的汇总通知。"""
    if succeeded <= 0 and failed <= 0:
        return None
    message = f"成功 {succeeded} 条"
    if failed > 0:
        message += f"，失败 {failed} 条"
    return NotificationEvent(
        event_type=TRANSFER_SUCCESS,
        severity=INFO,
        title="转存完成",
        message=message,
    )
