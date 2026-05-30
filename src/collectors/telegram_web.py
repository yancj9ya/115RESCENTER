from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote
from urllib.request import Request, urlopen

from .shares import CollectedShare, parse_115_shares

logger = logging.getLogger(__name__)


Fetcher = Callable[[str], str | Awaitable[str]]


@dataclass(frozen=True)
class TelegramWebMessage:
    channel: str
    message_id: str
    text: str
    published_at: datetime | None = None


class TelegramWebCollector:
    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetcher = fetcher or _fetch_url

    async def collect_history(self, channel: str, limit: int = 20) -> list[CollectedShare]:
        normalized_channel = channel.strip().lstrip("@")
        logger.info(f"开始采集 Telegram 频道: @{normalized_channel}, 限制: {limit} 条消息")

        url = self._build_history_url(normalized_channel, limit)
        logger.debug(f"请求 URL: {url}")

        html = self._fetcher(url)
        if inspect.isawaitable(html):
            html = await html

        messages = parse_telegram_public_channel_html(str(html), normalized_channel)
        logger.info(f"解析到 {len(messages)} 条消息")

        collected: list[CollectedShare] = []
        seen_share_urls: set[str] = set()

        for message in sorted(messages, key=lambda message: int(message.message_id)):
            shares_in_message = list(parse_115_shares(message.text))
            if shares_in_message:
                logger.debug(f"消息 {message.message_id} 包含 {len(shares_in_message)} 个分享链接")

            for share in shares_in_message:
                if share.share_url in seen_share_urls:
                    logger.debug(f"跳过重复链接: {share.share_url}")
                    continue
                seen_share_urls.add(share.share_url)
                logger.info(f"采集到分享链接: {share.share_url} (消息 {message.message_id})")
                collected.append(
                    CollectedShare(
                        share_code=share.share_code,
                        receive_code=share.receive_code,
                        share_url=share.share_url,
                        source_type="telegram_web",
                        source_id=message.channel,
                        message_id=message.message_id,
                        message_text=message.text,
                        published_at=message.published_at,
                    )
                )

        logger.info(f"采集完成: @{normalized_channel}, 共采集到 {len(collected)} 个分享链接")
        return collected

    @staticmethod
    def _build_history_url(channel: str, limit: int) -> str:
        return f"https://t.me/s/{quote(channel)}?limit={limit}"


def parse_telegram_public_channel_html(html: str, channel: str) -> list[TelegramWebMessage]:
    parser = _TelegramPublicChannelParser(channel)
    parser.feed(html)
    parser.close()
    return parser.messages


PageFetcher = Callable[[int | None], list[TelegramWebMessage]]

_DEFAULT_MAX_PAGES = 20


def paginate_after(
    fetch_page: PageFetcher,
    *,
    cursor: int,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> list[TelegramWebMessage]:
    """从 cursor 向后逐页翻 t.me/s ``?after=<id>``，汇总 > cursor 的全部新消息。

    ``fetch_page(after)`` 返回 message_id > after 的最近一页（约 20 条）。每页取最大 id
    作为下一页的 after，直到：页为空、最大 id 不再前进（防错误源死循环）、或达到 ``max_pages``。
    结果按 message_id 去重（页间重叠时）。冷启动（cursor 为空）不走此函数。
    """
    collected: dict[int, TelegramWebMessage] = {}
    after: int = cursor
    for _page in range(max_pages):
        page = fetch_page(after)
        if not page:
            break
        page_max = after
        for message in page:
            mid = _message_id_int(message)
            if mid is None:
                continue
            collected.setdefault(mid, message)
            if mid > page_max:
                page_max = mid
        if page_max <= after:
            # 最大 id 未前进：源行为异常或已到顶，停止以防死循环
            break
        after = page_max
    return [collected[mid] for mid in sorted(collected)]


def _message_id_int(message: TelegramWebMessage) -> int | None:
    try:
        return int(message.message_id)
    except (TypeError, ValueError):
        return None


class _TelegramPublicChannelParser(HTMLParser):
    def __init__(self, channel: str) -> None:
        super().__init__(convert_charrefs=True)
        self._channel = channel
        self._current: dict[str, object] | None = None
        self._message_depth = 0
        self._in_text_depth = 0
        self.messages: list[TelegramWebMessage] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())

        if tag == "div" and "tgme_widget_message" in classes:
            data_post = attrs_dict.get("data-post") or ""
            message_id = data_post.rsplit("/", 1)[-1] if data_post else ""
            self._current = {
                "message_id": message_id if message_id.isdecimal() else "",
                "text_parts": [],
                "published_at": None,
            }
            self._message_depth = 1
            return

        if self._current is None:
            return

        self._message_depth += 1

        if tag == "div" and "tgme_widget_message_text" in classes:
            self._in_text_depth = 1
            return

        if self._in_text_depth:
            self._in_text_depth += 1
            if tag in {"br", "p", "div"}:
                self._append_text("\n")

        if tag == "time":
            published_at = _parse_datetime(attrs_dict.get("datetime") or "")
            self._current["published_at"] = published_at

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if self._in_text_depth:
            self._in_text_depth -= 1

        self._message_depth -= 1
        if self._message_depth <= 0:
            text = "".join(self._current["text_parts"]).strip()  # type: ignore[index]
            message_id = str(self._current["message_id"])
            if message_id:
                self.messages.append(
                    TelegramWebMessage(
                        channel=self._channel,
                        message_id=message_id,
                        text=text,
                        published_at=self._current["published_at"],  # type: ignore[arg-type]
                    )
                )
            self._current = None
            self._message_depth = 0

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._in_text_depth:
            self._append_text(data)

    def _append_text(self, text: str) -> None:
        if self._current is None:
            return
        text_parts = self._current["text_parts"]
        if isinstance(text_parts, list):
            text_parts.append(text)


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")
