from __future__ import annotations

import unittest

from src.collectors.tencent_ranks import (
    TencentRankItem,
    TencentRankCollector,
    clean_title,
)

# 精简版真实 v.qq.com/biu/ranks/ HTML：两个榜单区块（电视剧 channel=2、电影 channel=1）。
# 真实页面把属性里的 = & 转义成 &#x3D; &amp;，fixture 沿用该形态以守住实体还原这个回归点。
# 每个区块前有 <div class="mod_rank_title"><h3 class="title">名</h3>... link_more href 带 channel=N。
# 每条 <li> 的 <a title="片名"> + href ?q=<编码片名>。
_SAMPLE_HTML = """
<div class="mod_rank">
  <div class="mod_rank_title"><h3 class="title">热搜</h3>
    <div class="title_action"><a class="link_more" href="/biu/ranks/?t&#x3D;hotsearch&amp;channel&#x3D;0">更多</a></div>
  </div>
  <div class="mod_rank_list"><ol class="hotlist">
    <li class="item" key="0"><a href="//v.qq.com/x/search/?q&#x3D;%E7%83%AD%E6%90%9C%E8%AF%8D&amp;stag&#x3D;12" title="热搜词"><span class="name">热搜词</span></a></li>
  </ol></div>

  <div class="mod_rank_title"><h3 class="title">电视剧</h3>
    <div class="title_action"><a class="link_more" href="/biu/ranks/?t&#x3D;hotsearch&amp;channel&#x3D;2">更多</a></div>
  </div>
  <div class="mod_rank_list"><ol class="hotlist">
    <li class="item" key="0"><a href="//v.qq.com/x/search/?q&#x3D;%E4%B8%BB%E8%A7%92&amp;stag&#x3D;12" title="主角"><span class="name">主角</span></a></li>
    <li class="item" key="1"><a href="//v.qq.com/x/search/?q&#x3D;%E5%A5%94%E8%B7%91%E5%90%A7&amp;stag&#x3D;12" title="奔跑吧 第10季"><span class="name">奔跑吧 第10季</span></a></li>
    <li class="item" key="2"><a href="//v.qq.com/x/search/?q&#x3D;%E5%B0%8F%E7%8C%AA%E4%BD%A9%E5%A5%87&amp;stag&#x3D;12" title="小猪佩奇 第11季[普通话版]"><span class="name">小猪佩奇 第11季[普通话版]</span></a></li>
  </ol></div>

  <div class="mod_rank_title"><h3 class="title">电影</h3>
    <div class="title_action"><a class="link_more" href="/biu/ranks/?t&#x3D;hotsearch&amp;channel&#x3D;1">更多</a></div>
  </div>
  <div class="mod_rank_list"><ol class="hotlist">
    <li class="item" key="0"><a href="//v.qq.com/x/search/?q&#x3D;%E7%96%AF%E7%8B%82%E5%8A%A8%E7%89%A9%E5%9F%8E2&amp;stag&#x3D;12" title="疯狂动物城2"><span class="name">疯狂动物城2</span></a></li>
  </ol></div>
</div>
"""


class CleanTitleTest(unittest.TestCase):
    def test_strips_season_suffix(self) -> None:
        self.assertEqual(clean_title("奔跑吧 第10季"), "奔跑吧")

    def test_strips_bracketed_version_note(self) -> None:
        self.assertEqual(clean_title("小猪佩奇 第11季[普通话版]"), "小猪佩奇")

    def test_strips_chinese_numeral_season(self) -> None:
        self.assertEqual(clean_title("剑来 第二季"), "剑来")

    def test_keeps_plain_title(self) -> None:
        self.assertEqual(clean_title("主角"), "主角")

    def test_keeps_trailing_arabic_sequel_number(self) -> None:
        # 电影续集编号是片名一部分，不能剥（疯狂动物城2 ≠ 疯狂动物城）
        self.assertEqual(clean_title("疯狂动物城2"), "疯狂动物城2")


class TencentRankCollectorTest(unittest.TestCase):
    def test_fetch_channel_returns_tv_items(self) -> None:
        collector = TencentRankCollector(fetcher=lambda _url: _SAMPLE_HTML)
        items = collector.fetch_channel("tv")

        self.assertEqual([item.rank for item in items], [1, 2, 3])
        self.assertEqual(items[0].title, "主角")
        self.assertEqual(items[0].raw_title, "主角")
        self.assertEqual(items[1].title, "奔跑吧")
        self.assertEqual(items[1].raw_title, "奔跑吧 第10季")
        self.assertEqual(items[2].title, "小猪佩奇")
        self.assertTrue(all(isinstance(item, TencentRankItem) for item in items))

    def test_fetch_channel_returns_movie_items(self) -> None:
        collector = TencentRankCollector(fetcher=lambda _url: _SAMPLE_HTML)
        items = collector.fetch_channel("movie")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "疯狂动物城2")

    def test_fetch_channel_respects_limit(self) -> None:
        collector = TencentRankCollector(fetcher=lambda _url: _SAMPLE_HTML)
        items = collector.fetch_channel("tv", limit=2)

        self.assertEqual(len(items), 2)

    def test_fetch_channel_rejects_unknown_channel(self) -> None:
        collector = TencentRankCollector(fetcher=lambda _url: _SAMPLE_HTML)
        with self.assertRaises(ValueError):
            collector.fetch_channel("documentary")

    def test_fetch_channel_rejects_non_positive_limit(self) -> None:
        collector = TencentRankCollector(fetcher=lambda _url: _SAMPLE_HTML)
        with self.assertRaises(ValueError):
            collector.fetch_channel("tv", limit=0)


if __name__ == "__main__":
    unittest.main()
