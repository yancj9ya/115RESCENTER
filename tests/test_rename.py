from __future__ import annotations

import unittest


class MovieRenameTemplateTest(unittest.TestCase):
    def test_movie_with_year_and_extinfo(self) -> None:
        from src.organizing.rename import compose_movie_filename

        result = compose_movie_filename(
            title="三体",
            year=2024,
            extinfo="2160p.HDR10.HEVC",
            extension="mkv",
        )

        self.assertEqual(result, "三体（2024）.2160p.HDR10.HEVC.mkv")

    def test_movie_without_extinfo(self) -> None:
        from src.organizing.rename import compose_movie_filename

        result = compose_movie_filename(title="Inception", year=2010, extinfo="", extension="mkv")

        self.assertEqual(result, "Inception（2010）.mkv")

    def test_movie_without_year(self) -> None:
        from src.organizing.rename import compose_movie_filename

        result = compose_movie_filename(title="Lost Movie", year=None, extinfo="1080p", extension="mp4")

        self.assertEqual(result, "Lost Movie.1080p.mp4")

    def test_movie_extension_normalised_to_lowercase(self) -> None:
        from src.organizing.rename import compose_movie_filename

        result = compose_movie_filename(title="Movie", year=2024, extinfo="", extension="MKV")

        self.assertEqual(result, "Movie（2024）.mkv")


class TvRenameTemplateTest(unittest.TestCase):
    def test_tv_with_season_episode_and_extinfo(self) -> None:
        from src.organizing.rename import compose_tv_filename

        result = compose_tv_filename(
            title="三体",
            year=2024,
            season=1,
            episode=3,
            extinfo="1080p.WEB-DL.x264",
            extension="mkv",
        )

        self.assertEqual(result, "三体.2024.S01E03.第3集.1080p.WEB-DL.x264.mkv")

    def test_tv_default_season_when_none(self) -> None:
        from src.organizing.rename import compose_tv_filename

        result = compose_tv_filename(
            title="Show",
            year=None,
            season=None,
            episode=8,
            extinfo="",
            extension="mp4",
        )

        self.assertEqual(result, "Show.S01E08.第8集.mp4")

    def test_tv_pads_double_digits(self) -> None:
        from src.organizing.rename import compose_tv_filename

        result = compose_tv_filename(
            title="Show",
            year=2026,
            season=12,
            episode=120,
            extinfo="1080p",
            extension="mkv",
        )

        self.assertEqual(result, "Show.2026.S12E120.第120集.1080p.mkv")


class IllegalCharacterSanitisationTest(unittest.TestCase):
    def test_movie_title_strips_illegal_chars(self) -> None:
        from src.organizing.rename import compose_movie_filename

        result = compose_movie_filename(
            title='三体/外?传:第一<部>"|*',
            year=2024,
            extinfo="",
            extension="mkv",
        )

        for forbidden in ("/", "?", ":", "<", ">", '"', "|", "*", "\\"):
            self.assertNotIn(forbidden, result)
        self.assertTrue(result.endswith(".mkv"))

    def test_tv_title_strips_illegal_chars(self) -> None:
        from src.organizing.rename import compose_tv_filename

        result = compose_tv_filename(
            title="Show: Test/Series",
            year=2024,
            season=1,
            episode=2,
            extinfo="",
            extension="mkv",
        )

        self.assertNotIn(":", result)
        self.assertNotIn("/", result)


if __name__ == "__main__":
    unittest.main()
