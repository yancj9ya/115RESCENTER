from __future__ import annotations

import re
from typing import Final

_FORBIDDEN_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r'[\\/:*?"<>|]')


def compose_movie_filename(*, title: str, year: int | None, extinfo: str, extension: str) -> str:
    base = _safe_title(title)
    if year is not None:
        base = f"{base}（{int(year)}）"
    extinfo_part = _normalise_extinfo(extinfo)
    suffix = _normalise_extension(extension)
    if extinfo_part:
        body = f"{base}.{extinfo_part}"
    else:
        body = base
    if suffix:
        return f"{body}.{suffix}"
    return body


def compose_tv_filename(
    *,
    title: str,
    year: int | None,
    season: int | None,
    episode: int,
    extinfo: str,
    extension: str,
) -> str:
    base = _safe_title(title)
    season_num = 1 if season is None else int(season)
    episode_num = int(episode)

    # 格式：标题.年份.S01E25.第25集.技术信息.扩展名
    parts = [base]

    # 添加年份
    if year is not None:
        parts.append(str(int(year)))

    # 添加季集号
    season_token = f"S{season_num:02d}"
    episode_token = f"E{episode_num:02d}" if episode_num < 100 else f"E{episode_num:03d}"
    parts.append(f"{season_token}{episode_token}")

    # 添加集数标题
    parts.append(f"第{episode_num}集")

    # 添加技术信息
    extinfo_part = _normalise_extinfo(extinfo)
    if extinfo_part:
        parts.append(extinfo_part)

    # 组合文件名
    body = ".".join(parts)

    # 添加扩展名
    suffix = _normalise_extension(extension)
    if suffix:
        return f"{body}.{suffix}"
    return body


def _safe_title(title: str) -> str:
    cleaned = _FORBIDDEN_CHARS_PATTERN.sub("", str(title))
    return cleaned.strip()


def _normalise_extinfo(extinfo: str) -> str:
    cleaned = str(extinfo).strip(". ")
    return cleaned


def _normalise_extension(extension: str) -> str:
    cleaned = str(extension).strip(". ").lower()
    return cleaned


__all__ = [
    "compose_movie_filename",
    "compose_tv_filename",
]
