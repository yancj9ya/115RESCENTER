from __future__ import annotations

import unittest


class BuildTargetSegmentsTest(unittest.TestCase):
    def _movie_metadata(self, **overrides):
        from src.organizing.models import MEDIA_KIND_MOVIE, OrganizeMetadata

        base = dict(
            title="三体",
            year=2024,
            kind=MEDIA_KIND_MOVIE,
            region_category="国产",
            tmdb_id=12345,
            genre_ids=(),
        )
        base.update(overrides)
        return OrganizeMetadata(**base)

    def _series_metadata(self, **overrides):
        from src.organizing.models import MEDIA_KIND_SERIES, OrganizeMetadata

        base = dict(
            title="鱿鱼游戏",
            year=2021,
            kind=MEDIA_KIND_SERIES,
            region_category="日韩",
            tmdb_id=93405,
            genre_ids=(),
            season=2,
        )
        base.update(overrides)
        return OrganizeMetadata(**base)

    def test_movie_segments_have_three_levels(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata())

        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0], "电影")
        self.assertEqual(segments[1], "国产")
        self.assertEqual(segments[2], "三体（2024）{tmdb-12345}")

    def test_series_segments_include_season(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._series_metadata())

        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0], "剧集")
        self.assertEqual(segments[1], "日韩")
        self.assertEqual(segments[2], "鱿鱼游戏（2021）{tmdb-93405}")
        self.assertEqual(segments[3], "S02")

    def test_series_defaults_season_to_one_when_missing(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._series_metadata(season=None))

        self.assertEqual(segments[-1], "S01")

    def test_documentary_genre_overrides_kind(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(genre_ids=(99,)))

        self.assertEqual(segments[0], "纪录片")

    def test_animation_genre_overrides_kind(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._series_metadata(genre_ids=(16,)))

        self.assertEqual(segments[0], "动画")

    def test_variety_genre_overrides_kind(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._series_metadata(genre_ids=(10764,)))

        self.assertEqual(segments[0], "综艺")

    def test_category_hint_used_when_no_matching_genre(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        metadata = self._movie_metadata(category_hint="anime")
        segments = build_target_segments(metadata)

        self.assertEqual(segments[0], "动画")

    def test_parsed_hint_used_when_metadata_lacks_hint(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(), parsed_category_hint="documentary")

        self.assertEqual(segments[0], "纪录片")

    def test_missing_region_falls_back(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(region_category=None))

        self.assertEqual(segments[1], "未分类地区")

    def test_missing_year_drops_year_token(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(year=None))

        self.assertEqual(segments[2], "三体{tmdb-12345}")

    def test_missing_tmdb_id_drops_tmdb_token(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(tmdb_id=None))

        self.assertEqual(segments[2], "三体（2024）")

    def test_unsafe_title_chars_are_replaced(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(self._movie_metadata(title='Bad/Title*Name'))

        for forbidden in ("/", "*", "\\", ":", "?", "<", ">", '"', "|"):
            self.assertNotIn(forbidden, segments[2])

    def test_none_metadata_returns_fallback_segments(self) -> None:
        from src.organizing.tree_builder import build_target_segments

        segments = build_target_segments(None)

        self.assertEqual(segments, ("未识别", "未分类地区", "未识别"))


if __name__ == "__main__":
    unittest.main()
