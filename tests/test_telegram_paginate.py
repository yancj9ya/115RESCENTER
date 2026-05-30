from __future__ import annotations

import unittest

from src.collectors.telegram_web import TelegramWebMessage, paginate_after


def _msg(mid: int) -> TelegramWebMessage:
    return TelegramWebMessage(channel="ch", message_id=str(mid), text=f"t{mid}")


class _PagedSource:
    """模拟 t.me/s ?after=<id> 行为：每次返回 > after 的最近一页（最多 page_size 条）。"""

    def __init__(self, all_ids: list[int], page_size: int = 20) -> None:
        self._all = sorted(all_ids)
        self._page_size = page_size
        self.calls: list[int | None] = []

    def fetch_page(self, after: int | None) -> list[TelegramWebMessage]:
        self.calls.append(after)
        pivot = after if after is not None else -1
        newer = [i for i in self._all if i > pivot]
        return [_msg(i) for i in newer[: self._page_size]]


class PaginateAfterTest(unittest.TestCase):
    def test_walks_forward_across_multiple_pages_until_exhausted(self) -> None:
        # cursor=100，频道有 100..165 共 65 条新消息，单页 20 → 需翻 4 页
        source = _PagedSource(list(range(101, 166)), page_size=20)

        messages = paginate_after(source.fetch_page, cursor=100, max_pages=20)

        ids = sorted(int(m.message_id) for m in messages)
        self.assertEqual(ids, list(range(101, 166)))
        # after 依次为 100,120,140,160；第 5 次返回空则停（这里 160 之后还有 161..165）
        self.assertEqual(source.calls[0], 100)
        self.assertTrue(all(messages))

    def test_stops_when_page_empty(self) -> None:
        source = _PagedSource(list(range(101, 106)), page_size=20)

        messages = paginate_after(source.fetch_page, cursor=100, max_pages=20)

        self.assertEqual(sorted(int(m.message_id) for m in messages), [101, 102, 103, 104, 105])
        # 第一页拿到 101..105，第二页 after=105 返回空 → 停
        self.assertEqual(source.calls, [100, 105])

    def test_respects_max_pages_cap(self) -> None:
        # 大量新消息，但上限 2 页 → 只取前 40 条
        source = _PagedSource(list(range(101, 401)), page_size=20)

        messages = paginate_after(source.fetch_page, cursor=100, max_pages=2)

        self.assertEqual(len(messages), 40)
        self.assertEqual(len(source.calls), 2)

    def test_stops_when_no_progress(self) -> None:
        # 防御：源若错误地反复返回同一批（最大 id 不前进），必须停而非死循环
        class _Stuck:
            def __init__(self) -> None:
                self.calls = 0

            def fetch_page(self, after: int | None) -> list[TelegramWebMessage]:
                self.calls += 1
                return [_msg(105), _msg(104)]

        stuck = _Stuck()
        messages = paginate_after(stuck.fetch_page, cursor=100, max_pages=20)

        # 第一页推进到 105，第二页最大仍是 105（无进展）→ 停
        self.assertEqual(stuck.calls, 2)
        self.assertTrue(len(messages) >= 2)

    def test_dedupes_overlapping_ids_across_pages(self) -> None:
        # 页间若有重叠（同一 id 出现两次），合并结果应去重
        pages = [[_msg(101), _msg(102)], [_msg(102), _msg(103)], []]

        def fetch_page(after: int | None) -> list[TelegramWebMessage]:
            return pages.pop(0) if pages else []

        messages = paginate_after(fetch_page, cursor=100, max_pages=20)

        ids = sorted(int(m.message_id) for m in messages)
        self.assertEqual(ids, [101, 102, 103])


if __name__ == "__main__":
    unittest.main()
