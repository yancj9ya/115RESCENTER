from __future__ import annotations

import unittest

from src.organizing import (
    MEDIA_KIND_MOVIE,
    MEDIA_KIND_SERIES,
    MEDIA_KIND_UNKNOWN,
    OrganizeMetadata,
    OrganizeRule,
    build_organize_plan,
    build_organize_plans,
)


class OrganizingPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = OrganizeRule(media_library_root_cid=900)

    def test_movie_metadata_produces_three_level_segments_and_movie_filename(self) -> None:
        item = {"id": 11, "name": "源文件.2160p.HEVC.mkv", "is_dir": False}
        metadata = OrganizeMetadata(
            title="三体",
            year=2024,
            kind=MEDIA_KIND_MOVIE,
            region_category="国产",
            tmdb_id=12345,
        )

        plan = build_organize_plan(item, metadata, self.rule)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.file_id, 11)
        self.assertEqual(plan.target_parent_cid, 900)
        self.assertEqual(plan.target_folder_segments, ("电影", "国产", "三体（2024）{tmdb-12345}"))
        self.assertEqual(plan.new_name, "三体（2024）.2160p.HEVC.mkv")
        self.assertEqual(plan.metadata, metadata)

    def test_series_metadata_appends_season_segment_and_tv_filename(self) -> None:
        item = {"id": 21, "name": "Show.S01E03.1080p.WEB-DL.mkv", "is_dir": False}
        metadata = OrganizeMetadata(
            title="鱿鱼游戏",
            year=2021,
            kind=MEDIA_KIND_SERIES,
            region_category="日韩",
            tmdb_id=93405,
            season=1,
            episode=3,
        )

        plan = build_organize_plan(item, metadata, self.rule)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.target_parent_cid, 900)
        self.assertEqual(
            plan.target_folder_segments,
            ("剧集", "日韩", "鱿鱼游戏（2021）{tmdb-93405}", "S01"),
        )
        self.assertEqual(plan.new_name, "鱿鱼游戏.2021.S01E03.第3集.1080p.WEB-DL.mkv")

    def test_series_uses_parsed_episode_when_metadata_lacks_it(self) -> None:
        item = {"id": 22, "name": "Show.S02E10.mkv", "is_dir": False}
        metadata = OrganizeMetadata(
            title="Show",
            year=2022,
            kind=MEDIA_KIND_SERIES,
            region_category="欧美",
            tmdb_id=42,
        )

        plan = build_organize_plan(item, metadata, self.rule)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.new_name, "Show.2022.S02E10.第10集.mkv")
        self.assertEqual(plan.target_folder_segments[-1], "S02")

    def test_documentary_genre_routes_under_documentary_category(self) -> None:
        item = {"id": 31, "name": "Doc.mkv", "is_dir": False}
        metadata = OrganizeMetadata(
            title="地球脉动",
            year=2016,
            kind=MEDIA_KIND_SERIES,
            region_category="欧美",
            tmdb_id=555,
            genre_ids=(99,),
            season=1,
            episode=1,
        )

        plan = build_organize_plan(item, metadata, self.rule)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.target_folder_segments[0], "纪录片")

    def test_unknown_metadata_returns_none_and_skips_file(self) -> None:
        item = {"id": 41, "name": "Original Name.avi", "is_dir": False}

        plan_without = build_organize_plan(item, None, self.rule)

        self.assertIsNone(plan_without)

    def test_directory_items_return_none(self) -> None:
        item = {"id": 50, "name": "Season 1", "is_dir": True}
        metadata = OrganizeMetadata(title="Title", year=2024, kind=MEDIA_KIND_MOVIE)

        plan = build_organize_plan(item, metadata, self.rule)

        self.assertIsNone(plan)

    def test_build_organize_plans_skips_directories_and_uses_metadata_by_id(self) -> None:
        items = [
            {"id": 21, "name": "Movie File.mkv", "is_dir": False},
            {"id": 22, "name": "Keep Me.mp4", "is_dir": False},
            {"id": 23, "name": "Folder", "is_dir": True},
            {"id": 24, "name": "Episode.S01E02.avi", "is_dir": False},
        ]
        metadata_by_file_id = {
            21: OrganizeMetadata(
                title="Title",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                region_category="欧美",
                tmdb_id=7,
            ),
            24: OrganizeMetadata(
                title="Series Title",
                year=2023,
                kind=MEDIA_KIND_SERIES,
                region_category="欧美",
                tmdb_id=8,
                season=1,
                episode=2,
            ),
        }

        plans = build_organize_plans(items, metadata_by_file_id, self.rule)

        self.assertEqual([plan.file_id for plan in plans], [21, 24])
        self.assertTrue(all(plan.target_parent_cid == 900 for plan in plans))
        self.assertEqual(plans[0].new_name, "Title（2024）.mkv")
        self.assertEqual(plans[1].new_name, "Series Title.2023.S01E02.第2集.avi")


if __name__ == "__main__":
    unittest.main()
