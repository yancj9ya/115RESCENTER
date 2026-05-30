from __future__ import annotations

import html as _html
import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], str | Awaitable[str]]

_RANKS_URL = "https://v.qq.com/biu/ranks/"

# 前端 channel 标识 → 腾讯 channel id（来自榜单页 link_more 的 ?channel=N）
_CHANNELS: dict[str, str] = {
    "tv": "2",       # 电视剧
    "movie": "1",    # 电影
    "variety": "10", # 综艺
    "cartoon": "3",  # 动漫
}

# 剥季号/期号：匹配片名尾部的 " 第N季"/"第N期"（N 为阿拉伯或中文数字）及其后的方括号版本注。
_SEASON_RE = re.compile(r"\s*第[0-9一二三四五六七八九十百零]+[季期].*$")
# 剥独立的尾部方括号注（如 "[普通话版]"），用于无季号但带版本注的片名。
_BRACKET_RE = re.compile(r"\s*[\[【][^\]】]*[\]】]\s*$")

# 单个榜单标题块：捕获 link_more 的 channel id，作为该块后续 hotlist 的归属。
_TITLE_RE = re.compile(
    r'<div class="mod_rank_title">.*?<a class="link_more"[^>]*?channel=(\d+)',
    re.S,
)
# 紧随标题块的列表：一个 hotlist 的全部 li。
_LIST_RE = re.compile(r'<ol class="hotlist">(.*?)</ol>', re.S)
# 单条 li 的 a 标签 title 属性。
_ITEM_RE = re.compile(r'<li\b[^>]*>.*?<a\b[^>]*\btitle="([^"]*)"', re.S)


@dataclass(frozen=True)
class TencentRankItem:
    rank: int
    title: str
    raw_title: str


def clean_title(raw: str) -> str:
    title = _html.unescape(raw).strip()
    title = _SEASON_RE.sub("", title)
    title = _BRACKET_RE.sub("", title)
    return title.strip()


class TencentRankCollector:
    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher = fetcher or _fetch_url

    def fetch_channel(self, channel: str, *, limit: int = 10) -> list[TencentRankItem]:
        channel_id = _CHANNELS.get(channel)
        if channel_id is None:
            raise ValueError(f"channel must be one of {sorted(_CHANNELS)}")
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit}")

        html = self._fetcher(_RANKS_URL)
        if inspect.isawaitable(html):
            raise TypeError("TencentRankCollector requires a synchronous fetcher")

        # 真实页面把属性里的 = & 转义成 &#x3D; &amp;，先整体还原实体再正则匹配。
        decoded = _html.unescape(str(html))
        block = _extract_channel_block(decoded, channel_id)
        if block is None:
            logger.warning(f"腾讯榜单页未找到频道 channel={channel_id} ({channel}) 的区块")
            return []

        items: list[TencentRankItem] = []
        for raw_title in _ITEM_RE.findall(block):
            cleaned = clean_title(raw_title)
            if not cleaned:
                continue
            items.append(
                TencentRankItem(
                    rank=len(items) + 1,
                    title=cleaned,
                    raw_title=_html.unescape(raw_title).strip(),
                )
            )
            if len(items) >= limit:
                break
        return items


def _extract_channel_block(html: str, channel_id: str) -> str | None:
    # 找到该 channel 的标题块位置，再取其后紧邻的第一个 hotlist。
    for match in _TITLE_RE.finditer(html):
        if match.group(1) != channel_id:
            continue
        list_match = _LIST_RE.search(html, match.end())
        if list_match is None:
            return None
        return list_match.group(1)
    return None


def _fetch_url(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310 - 固定 https 目标
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")
