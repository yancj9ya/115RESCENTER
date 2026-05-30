from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.collectors.telegram_web import TelegramWebCollector


class TelegramWebCollectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_history_extracts_115_links_from_public_channel_html(self) -> None:
        html = """
        <div class="tgme_widget_message" data-post="movie_channel/101">
          <div class="tgme_widget_message_text js-message_text">
            新资源 https://115.com/s/abc123?password=xy9z
          </div>
          <time datetime="2026-05-26T08:30:00+00:00"></time>
        </div>
        """

        collector = TelegramWebCollector(fetcher=lambda _url: html)
        shares = await collector.collect_history("movie_channel", limit=20)

        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].share_code, "abc123")
        self.assertEqual(shares[0].receive_code, "xy9z")
        self.assertEqual(shares[0].share_url, "https://115.com/s/abc123?password=xy9z")
        self.assertEqual(shares[0].source_type, "telegram_web")
        self.assertEqual(shares[0].source_id, "movie_channel")
        self.assertEqual(shares[0].message_id, "101")
        self.assertIn("新资源", shares[0].message_text)
        self.assertEqual(shares[0].published_at, datetime(2026, 5, 26, 8, 30, tzinfo=timezone.utc))

    async def test_collect_history_deduplicates_same_share_across_messages(self) -> None:
        html = """
        <div class="tgme_widget_message" data-post="movie_channel/101">
          <div class="tgme_widget_message_text js-message_text">https://115.com/s/dup123</div>
        </div>
        <div class="tgme_widget_message" data-post="movie_channel/102">
          <div class="tgme_widget_message_text js-message_text">再次发布 https://115.com/s/dup123</div>
        </div>
        """

        collector = TelegramWebCollector(fetcher=lambda _url: html)
        shares = await collector.collect_history("movie_channel")

        self.assertEqual([share.message_id for share in shares], ["101"])
        self.assertEqual([share.share_code for share in shares], ["dup123"])

    async def test_collect_history_orders_shares_by_numeric_message_id(self) -> None:
        html = """
        <div class="tgme_widget_message" data-post="movie_channel/103">
          <div class="tgme_widget_message_text js-message_text">第三条 https://115.com/s/order103</div>
        </div>
        <div class="tgme_widget_message" data-post="movie_channel/101">
          <div class="tgme_widget_message_text js-message_text">第一条 https://115.com/s/order101</div>
        </div>
        <div class="tgme_widget_message" data-post="movie_channel/102">
          <div class="tgme_widget_message_text js-message_text">第二条 https://115.com/s/order102</div>
        </div>
        """

        collector = TelegramWebCollector(fetcher=lambda _url: html)
        shares = await collector.collect_history("movie_channel")

        self.assertEqual([share.message_id for share in shares], ["101", "102", "103"])
        self.assertEqual(
            [share.share_url for share in shares],
            [
                "https://115.com/s/order101",
                "https://115.com/s/order102",
                "https://115.com/s/order103",
            ],
        )

    async def test_collect_history_deduplicates_same_share_within_one_message(self) -> None:
        html = """
        <div class="tgme_widget_message" data-post="movie_channel/104">
          <div class="tgme_widget_message_text js-message_text">
            https://115.com/s/same104 再贴一次 https://115.com/s/same104
          </div>
        </div>
        """

        collector = TelegramWebCollector(fetcher=lambda _url: html)
        shares = await collector.collect_history("movie_channel")

        self.assertEqual(len(shares), 1)
        self.assertEqual([share.message_id for share in shares], ["104"])
        self.assertEqual([share.share_url for share in shares], ["https://115.com/s/same104"])

    async def test_collect_history_skips_messages_with_missing_or_malformed_message_id(self) -> None:
        html = """
        <div class="tgme_widget_message">
          <div class="tgme_widget_message_text js-message_text">缺少 ID https://115.com/s/missingid</div>
        </div>
        <div class="tgme_widget_message" data-post="movie_channel/not-a-number">
          <div class="tgme_widget_message_text js-message_text">坏 ID https://115.com/s/badid</div>
        </div>
        <div class="tgme_widget_message" data-post="movie_channel/105">
          <div class="tgme_widget_message_text js-message_text">有效 ID https://115.com/s/good105</div>
        </div>
        """

        collector = TelegramWebCollector(fetcher=lambda _url: html)
        shares = await collector.collect_history("movie_channel")

        self.assertEqual([share.message_id for share in shares], ["105"])
        self.assertEqual([share.share_url for share in shares], ["https://115.com/s/good105"])
        self.assertTrue(all(share.message_id and share.message_id.isdecimal() for share in shares))

    async def test_collect_history_uses_t_me_public_history_url(self) -> None:
        requested_urls: list[str] = []

        def fetcher(url: str) -> str:
            requested_urls.append(url)
            return ""

        collector = TelegramWebCollector(fetcher=fetcher)
        await collector.collect_history("@movie_channel", limit=50)

        self.assertEqual(requested_urls, ["https://t.me/s/movie_channel?limit=50"])


if __name__ == "__main__":
    unittest.main()
