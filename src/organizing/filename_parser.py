from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

CategoryHint = Literal["anime", "variety", "documentary"]


_EPISODE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"[Ss](?P<s>\d{1,2})[Ee](?P<e>\d{1,3})"),
    re.compile(r"(?<!\d)(?P<s>\d{1,2})x(?P<e>\d{1,3})(?!\d)", re.IGNORECASE),
    re.compile(r"第\s*(?P<e>\d{1,3})\s*[集话話]"),
    re.compile(r"\bE[Pp]?\s*(?P<e>\d{1,3})\b"),
)

_RESOLUTION_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![A-Za-z0-9])(2160p|1440p|1080p|720p|480p)(?![A-Za-z0-9])", re.IGNORECASE)
_CODEC_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![A-Za-z0-9])(x265|x264|H\.?265|H\.?264|HEVC|AVC|AV1)(?![A-Za-z0-9])", re.IGNORECASE)
_DYNAMIC_RANGE_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"(?<![A-Za-z0-9])Dolby\.?Vision(?![A-Za-z0-9])", re.IGNORECASE), "DolbyVision"),
    (re.compile(r"(?<![A-Za-z0-9])DoVi(?![A-Za-z0-9])", re.IGNORECASE), "DolbyVision"),
    (re.compile(r"(?<![A-Za-z0-9])HDR10\+(?![A-Za-z0-9])", re.IGNORECASE), "HDR10+"),
    (re.compile(r"(?<![A-Za-z0-9])HDR10(?![A-Za-z0-9])", re.IGNORECASE), "HDR10"),
    (re.compile(r"(?<![A-Za-z0-9])HDR(?![A-Za-z0-9])", re.IGNORECASE), "HDR"),
    (re.compile(r"(?<![A-Za-z0-9])SDR(?![A-Za-z0-9])", re.IGNORECASE), "SDR"),
)
_EXTRA_TAG_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"(?<![A-Za-z0-9])Atmos(?![A-Za-z0-9])", re.IGNORECASE), "Atmos"),
    (re.compile(r"(?<![A-Za-z0-9])DTS-HD(?![A-Za-z0-9])", re.IGNORECASE), "DTS-HD"),
    (re.compile(r"(?<![A-Za-z0-9])DTS(?![A-Za-z0-9])", re.IGNORECASE), "DTS"),
    (re.compile(r"(?<![A-Za-z0-9])TrueHD(?![A-Za-z0-9])", re.IGNORECASE), "TrueHD"),
    (re.compile(r"(?<![A-Za-z0-9])BluRay(?![A-Za-z0-9])", re.IGNORECASE), "BluRay"),
    (re.compile(r"(?<![A-Za-z0-9])WEB-DL(?![A-Za-z0-9])", re.IGNORECASE), "WEB-DL"),
    (re.compile(r"(?<![A-Za-z0-9])WEBRip(?![A-Za-z0-9])", re.IGNORECASE), "WEBRip"),
    (re.compile(r"(?<![A-Za-z0-9])REMUX(?![A-Za-z0-9])", re.IGNORECASE), "REMUX"),
    (re.compile(r"(?<![A-Za-z0-9])UHD(?![A-Za-z0-9])", re.IGNORECASE), "UHD"),
    (re.compile(r"中字"), "中字"),
    (re.compile(r"国语"), "国语"),
    (re.compile(r"双语"), "双语"),
    (re.compile(r"原盘"), "原盘"),
)

_CATEGORY_KEYWORDS: Final[tuple[tuple[CategoryHint, tuple[str, ...]], ...]] = (
    ("anime", ("anime", "动画", "动漫", "話", "字幕组", "字幕組")),
    ("variety", ("variety", "综艺", "综艺节目", "綜藝")),
    ("documentary", ("documentary", "纪录片", "紀錄片", "纪实")),
)

_CANONICAL_CODECS: Final[dict[str, str]] = {
    "h.265": "HEVC",
    "h265": "HEVC",
    "hevc": "HEVC",
    "x265": "x265",
    "h.264": "AVC",
    "h264": "AVC",
    "avc": "AVC",
    "x264": "x264",
    "av1": "AV1",
}


@dataclass(frozen=True)
class EpisodeInfo:
    season: int | None
    episode: int


@dataclass(frozen=True)
class FilenameTags:
    resolution: str | None = None
    codec: str | None = None
    dynamic_range: str | None = None
    extras: tuple[str, ...] = field(default_factory=tuple)

    def compose_extinfo(self) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        for token in (self.resolution, self.dynamic_range, self.codec, *self.extras):
            if token and token not in seen:
                seen.add(token)
                parts.append(token)
        return ".".join(parts)


@dataclass(frozen=True)
class ParsedFilename:
    raw: str
    stem: str
    extension: str
    episode: EpisodeInfo | None
    tags: FilenameTags
    category_hint: CategoryHint | None


def parse_filename(name: str) -> ParsedFilename:
    raw = str(name)
    stem, extension = _split_extension(raw)
    episode = _parse_episode(stem)
    tags = _parse_tags(stem)
    category_hint = _parse_category_hint(stem)
    return ParsedFilename(
        raw=raw,
        stem=stem,
        extension=extension,
        episode=episode,
        tags=tags,
        category_hint=category_hint,
    )


def extract_tmdb_id(filename: str) -> int | None:
    """从文件名中提取 TMDB ID

    如果文件名包含 {tmdb-xxxxx} 标签，返回 TMDB ID；否则返回 None。

    示例：
    - "大唐迷雾.2026 - S01E15.{tmdb-289209}.mkv" -> 289209
    - "The Matrix (1999).mkv" -> None
    """
    match = re.search(r'\{tmdb-(\d+)\}', filename)
    if match:
        return int(match.group(1))
    return None


_SEASON_FOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:S\d{1,3}|Season\s*\d{1,3}|第\s*\d{1,3}\s*季|specials?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedFolderName:
    title: str
    year: int | None
    tmdb_id: int | None


def is_season_folder_name(name: str) -> bool:
    """判断文件夹名是否为季度命名（如 S01、Season 1、第1季、Specials），这类文件夹应跳过。"""
    return bool(_SEASON_FOLDER_PATTERN.match(str(name).strip()))


def parse_folder_name(name: str) -> ParsedFolderName:
    """从文件夹名分离剧名、年份、TMDB ID。

    示例：
    - "英雄联盟：双城之战 (2021) {tmdb-94605}" -> ParsedFolderName("英雄联盟：双城之战", 2021, 94605)
    - "大唐迷雾（2026）" -> ParsedFolderName("大唐迷雾", 2026, None)
    - "The Matrix" -> ParsedFolderName("The Matrix", None, None)
    """
    raw = str(name).strip()
    tmdb_id = extract_tmdb_id(raw)

    stem = re.sub(r"\{tmdb-\d+\}", "", raw)

    year: int | None = None
    year_match = re.search(r"[（(]\s*((?:19|20)\d{2})\s*[)）]", stem)
    if year_match is None:
        year_match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", stem)
    if year_match is not None:
        year = int(year_match.group(1))
        stem = stem[: year_match.start()] + stem[year_match.end():]

    stem = re.sub(r"[（(]\s*[)）]", " ", stem)
    stem = re.sub(r"[._]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .-_（）()")

    return ParsedFolderName(title=stem, year=year, tmdb_id=tmdb_id)


def extract_media_title(filename: str) -> str:
    """从文件名中提取媒体标题，用于 TMDB 搜索

    移除以下内容：
    - 文件扩展名
    - 年份（括号内或点号分隔）
    - 剧集信息（S01E02、第2集等）
    - 分辨率（1080p、2160p等）
    - 编码信息（x265、HEVC等）
    - 动态范围（HDR、DolbyVision等）
    - 来源标签（WEB-DL、BluRay等）
    - TMDB ID 标签（{tmdb-xxxxx}）
    - 其他技术标签

    示例：
    - "大唐迷雾.2026 - S01E15 - 第 15 集 - 2160p.WEB-DL.HDR10.HEVC.60fps.AAC 2.0.{tmdb-289209}.mkv"
      -> "大唐迷雾"
    - "The Matrix (1999) 1080p BluRay x264.mkv"
      -> "The Matrix"
    """
    # 移除文件扩展名
    stem, _ = _split_extension(filename)

    # 移除 TMDB ID 标签 {tmdb-xxxxx}
    stem = re.sub(r'\{tmdb-\d+\}', '', stem)

    # 移除 " - " 后面的所有内容（通常是剧集标题或技术信息）
    if ' - ' in stem:
        stem = stem.split(' - ')[0]

    # 移除剧集信息
    for pattern in _EPISODE_PATTERNS:
        stem = pattern.sub('', stem)

    # 移除分辨率
    stem = _RESOLUTION_PATTERN.sub('', stem)

    # 移除编码
    stem = _CODEC_PATTERN.sub('', stem)

    # 移除动态范围标签
    for pattern, _ in _DYNAMIC_RANGE_PATTERNS:
        stem = pattern.sub('', stem)

    # 移除其他技术标签
    for pattern, _ in _EXTRA_TAG_PATTERNS:
        stem = pattern.sub('', stem)

    # 移除常见的分隔符和技术信息
    # 移除帧率（60fps、24 fps 等，容忍前置分隔符）
    stem = re.sub(r'\d+\s*fps', '', stem, flags=re.IGNORECASE)

    # 移除位深（10bit、10-bit、10 bit 等，容忍连字符/空格分隔）
    stem = re.sub(r'\d+\s*[-_]?\s*bit', '', stem, flags=re.IGNORECASE)

    # 移除发布组标签（通常在末尾，格式如 -HDSWEB、-RARBG 等）
    stem = re.sub(r'-[A-Z0-9]+$', '', stem, flags=re.IGNORECASE)

    # 清理多余的空格、点号、下划线、连字符（在移除音频信息之前）
    stem = re.sub(r'[._\-]+', ' ', stem)
    stem = re.sub(r'\s+', ' ', stem)
    stem = stem.strip(' .-_')

    # 兜底：分隔符归一化后残留的孤立位深/帧率（如 "10 bit"、"24 fps"）
    stem = re.sub(r'\b\d+\s+(?:bit|fps)\b', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'\s+', ' ', stem).strip()

    # 移除音频信息（在清理分隔符之后）
    # 先处理复杂的音频格式，再处理简单的
    stem = re.sub(r'DTS HD MA \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DTS HD \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DTS\d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DTS \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'TrueHD \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DDP\d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DDP \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DD\+ \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'DD \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'AAC \d+\s+\d+', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'AC3 \d+\s+\d+', '', stem, flags=re.IGNORECASE)

    # 移除孤立的音频通道数（如 5 1、2 0、7 1 等，已被空格分隔）
    stem = re.sub(r'\b\d\s+\d\b', '', stem)

    # 移除孤立的 MA（来自 DTS-HD MA 的残留）
    stem = re.sub(r'\bMA\b', '', stem, flags=re.IGNORECASE)

    # 移除年份（括号内或独立的四位数字）
    stem = re.sub(r'\(\d{4}\)', '', stem)
    stem = re.sub(r'\b(19|20)\d{2}\b', '', stem)

    # 再次清理多余的空格
    stem = re.sub(r'\s+', ' ', stem)
    stem = stem.strip()

    # 移除括号（但保留内容）
    stem = re.sub(r'[()]', ' ', stem)
    stem = re.sub(r'\s+', ' ', stem)
    stem = stem.strip()

    return stem


def _split_extension(name: str) -> tuple[str, str]:
    if "." not in name:
        return name, ""
    base, _, ext = name.rpartition(".")
    if not base or len(ext) > 5:
        return name, ""
    return base, ext.lower()


def _parse_episode(stem: str) -> EpisodeInfo | None:
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        season_raw = match.groupdict().get("s")
        episode_raw = match.groupdict().get("e")
        if episode_raw is None:
            continue
        season = int(season_raw) if season_raw is not None else None
        episode = int(episode_raw)
        return EpisodeInfo(season=season, episode=episode)
    return None


def _parse_tags(stem: str) -> FilenameTags:
    resolution = _first_match(_RESOLUTION_PATTERN, stem, normaliser=str.lower)
    codec_raw = _first_match(_CODEC_PATTERN, stem)
    codec = _CANONICAL_CODECS.get(codec_raw.lower(), codec_raw) if codec_raw else None
    dynamic_range = _first_tagged_match(_DYNAMIC_RANGE_PATTERNS, stem)
    extras = _collect_tagged_matches(_EXTRA_TAG_PATTERNS, stem)
    return FilenameTags(
        resolution=resolution,
        codec=codec,
        dynamic_range=dynamic_range,
        extras=extras,
    )


def _parse_category_hint(stem: str) -> CategoryHint | None:
    lowered = stem.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword.lower() in lowered:
                return category
    return None


def _first_match(pattern: re.Pattern[str], stem: str, *, normaliser=None) -> str | None:
    match = pattern.search(stem)
    if not match:
        return None
    value = match.group(0)
    if normaliser is not None:
        value = normaliser(value)
    return value


def _first_tagged_match(patterns: tuple[tuple[re.Pattern[str], str], ...], stem: str) -> str | None:
    for pattern, label in patterns:
        if pattern.search(stem):
            return label
    return None


def _collect_tagged_matches(patterns: tuple[tuple[re.Pattern[str], str], ...], stem: str) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern, label in patterns:
        if pattern.search(stem) and label not in seen:
            seen.add(label)
            found.append(label)
    return tuple(found)


__all__ = [
    "CategoryHint",
    "EpisodeInfo",
    "FilenameTags",
    "ParsedFilename",
    "ParsedFolderName",
    "parse_filename",
    "parse_folder_name",
    "is_season_folder_name",
    "extract_media_title",
    "extract_tmdb_id",
]
