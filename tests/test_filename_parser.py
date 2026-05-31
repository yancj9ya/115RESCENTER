from __future__ import annotations

import unittest


class FilenameEpisodeParsingTest(unittest.TestCase):
    def test_extracts_season_and_episode_from_s01e02(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Show.Name.S01E02.1080p.WEB-DL.x264.mkv")

        self.assertIsNotNone(result.episode)
        assert result.episode is not None
        self.assertEqual(result.episode.season, 1)
        self.assertEqual(result.episode.episode, 2)

    def test_extracts_lowercase_s01e02(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("show name s01e02 ep.mkv")

        assert result.episode is not None
        self.assertEqual((result.episode.season, result.episode.episode), (1, 2))

    def test_extracts_dot_separated_1x02(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Show.1x02.WEB.mkv")

        assert result.episode is not None
        self.assertEqual((result.episode.season, result.episode.episode), (1, 2))

    def test_extracts_chinese_episode_marker(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("剧名.第08集.1080p.mp4")

        assert result.episode is not None
        self.assertEqual(result.episode.episode, 8)

    def test_no_episode_returns_none_for_movie(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Movie.Title.2024.1080p.BluRay.mkv")

        self.assertIsNone(result.episode)


class FilenameTagExtractionTest(unittest.TestCase):
    def test_extracts_resolution_codec_and_dynamic_range(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Movie.2024.2160p.UHD.BluRay.HDR10.HEVC.Atmos.mkv")

        self.assertEqual(result.tags.resolution, "2160p")
        self.assertEqual(result.tags.codec, "HEVC")
        self.assertEqual(result.tags.dynamic_range, "HDR10")
        self.assertIn("Atmos", result.tags.extras)

    def test_extracts_1080p_with_x264(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Show.S01E01.1080p.WEB-DL.x264.mp4")

        self.assertEqual(result.tags.resolution, "1080p")
        self.assertEqual(result.tags.codec, "x264")

    def test_extracts_chinese_subtitle_marker(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("剧名.S01E02.1080p.中字.mkv")

        self.assertIn("中字", result.tags.extras)

    def test_no_recognised_tags_returns_empty(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Plain.Title.mkv")

        self.assertIsNone(result.tags.resolution)
        self.assertIsNone(result.tags.codec)
        self.assertEqual(result.tags.extras, ())


class FilenameCategoryHintTest(unittest.TestCase):
    def test_detects_anime_keyword(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("[字幕组] 动画 第01话 [1080p].mkv")

        self.assertEqual(result.category_hint, "anime")

    def test_detects_variety_keyword(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("综艺.节目.20240101.E10.1080p.mp4")

        self.assertEqual(result.category_hint, "variety")

    def test_detects_documentary_keyword(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Documentary.Earth.2024.2160p.mkv")

        self.assertEqual(result.category_hint, "documentary")

    def test_unrecognised_returns_none(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Random.File.mkv")

        self.assertIsNone(result.category_hint)


class FilenameExtinfoCompositionTest(unittest.TestCase):
    def test_composes_extinfo_from_tags(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Movie.2024.2160p.HDR10.HEVC.Atmos.mkv")

        self.assertEqual(result.tags.compose_extinfo(), "2160p.HDR10.HEVC.Atmos")

    def test_compose_extinfo_keeps_unique_order(self) -> None:
        from src.organizing.filename_parser import parse_filename

        result = parse_filename("Show.S01E02.1080p.WEB-DL.x264.中字.mkv")

        composed = result.tags.compose_extinfo()
        self.assertTrue(composed.startswith("1080p.x264"))
        self.assertIn("中字", composed)


class ExtractMediaTitleTest(unittest.TestCase):
    def test_strips_bit_depth_variants_hyphen_space_and_plain(self) -> None:
        from src.organizing.filename_parser import extract_media_title

        # 位深三种写法都应被剥离，不能把 "10 bit" 残留进标题
        self.assertEqual(
            extract_media_title("一人之下.2016.S00E02.第2集.2160p.SDR.H.265.10-bit.24fps.AAC 2.0-AISR.mkv"),
            "一人之下",
        )
        self.assertEqual(extract_media_title("Show.S01E01.1080p.10bit.x265.mkv"), "Show")
        self.assertEqual(extract_media_title("Foo.2020.720p.8 bit.HEVC.mkv"), "Foo")

    def test_strips_common_release_tags(self) -> None:
        from src.organizing.filename_parser import extract_media_title

        self.assertEqual(extract_media_title("大唐迷雾-S01E15.2160p.HDR10.HEVC.WEB-DL.mkv"), "大唐迷雾")
        self.assertEqual(extract_media_title("The Matrix (1999) 1080p BluRay x264.mkv"), "The Matrix")

    def test_title_stops_before_season_episode_marker(self) -> None:
        from src.organizing.filename_parser import extract_media_title

        self.assertEqual(
            extract_media_title("主角.2026.S01E38.第38集.2160p.WEB-DL.DV.H.265-XH.mkv"),
            "主角",
        )

    def test_strips_dovi_dolby_vision_shorthand(self) -> None:
        from src.organizing.filename_parser import extract_media_title

        self.assertEqual(
            extract_media_title(
                "英雄联盟：双城之战.2021.S01E07.第7集.2160p.UHD BluRay.DoVi.H.265 10bit.TrueHD 5.1-beAst.mkv"
            ),
            "英雄联盟：双城之战",
        )


class ParseFolderNameTest(unittest.TestCase):
    def test_extracts_title_year_and_tmdb_id(self) -> None:
        from src.organizing.filename_parser import parse_folder_name

        result = parse_folder_name("英雄联盟：双城之战 (2021) {tmdb-94605}")

        self.assertEqual(result.title, "英雄联盟：双城之战")
        self.assertEqual(result.year, 2021)
        self.assertEqual(result.tmdb_id, 94605)

    def test_extracts_title_from_fullwidth_year_parentheses(self) -> None:
        from src.organizing.filename_parser import parse_folder_name

        result = parse_folder_name("大唐迷雾（2026）")

        self.assertEqual(result.title, "大唐迷雾")
        self.assertEqual(result.year, 2026)
        self.assertIsNone(result.tmdb_id)

    def test_plain_title_has_no_year_or_id(self) -> None:
        from src.organizing.filename_parser import parse_folder_name

        result = parse_folder_name("The Matrix")

        self.assertEqual(result.title, "The Matrix")
        self.assertIsNone(result.year)
        self.assertIsNone(result.tmdb_id)


class IsSeasonFolderNameTest(unittest.TestCase):
    def test_detects_season_folder_variants(self) -> None:
        from src.organizing.filename_parser import is_season_folder_name

        for name in ("S01", "s1", "Season 1", "Season  12", "第1季", "第 02 季", "Specials", "special"):
            self.assertTrue(is_season_folder_name(name), name)

    def test_non_season_names_are_not_detected(self) -> None:
        from src.organizing.filename_parser import is_season_folder_name

        for name in ("英雄联盟：双城之战", "The Matrix", "Season Finale Show", "S01E02 raw.mkv"):
            self.assertFalse(is_season_folder_name(name), name)


if __name__ == "__main__":
    unittest.main()
