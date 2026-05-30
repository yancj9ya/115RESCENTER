from __future__ import annotations

import unittest


class TmdbCategoryFromGenresTest(unittest.TestCase):
    def test_movie_with_documentary_genre_returns_documentary(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="movie", genre_ids=(99,), title_hint=None)

        self.assertEqual(result, "documentary")

    def test_movie_with_animation_genre_returns_anime(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="movie", genre_ids=(16,), title_hint=None)

        self.assertEqual(result, "anime")

    def test_tv_with_animation_genre_returns_anime(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(16,), title_hint=None)

        self.assertEqual(result, "anime")

    def test_tv_with_reality_genre_returns_variety(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(10764,), title_hint=None)

        self.assertEqual(result, "variety")

    def test_tv_with_talk_genre_returns_variety(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(10767,), title_hint=None)

        self.assertEqual(result, "variety")

    def test_tv_with_documentary_genre_returns_documentary(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(99,), title_hint=None)

        self.assertEqual(result, "documentary")

    def test_movie_without_special_genre_returns_movie(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="movie", genre_ids=(28,), title_hint=None)

        self.assertEqual(result, "movie")

    def test_tv_without_special_genre_returns_tv(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(18,), title_hint=None)

        self.assertEqual(result, "tv")


class TmdbCategoryFilenameHintFallbackTest(unittest.TestCase):
    def test_filename_anime_hint_overrides_plain_tv(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(), title_hint="anime")

        self.assertEqual(result, "anime")

    def test_filename_variety_hint_overrides_plain_tv(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="tv", genre_ids=(), title_hint="variety")

        self.assertEqual(result, "variety")

    def test_filename_documentary_hint_overrides_plain_movie(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="movie", genre_ids=(), title_hint="documentary")

        self.assertEqual(result, "documentary")

    def test_genre_takes_precedence_over_filename_hint(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind="movie", genre_ids=(99,), title_hint="anime")

        self.assertEqual(result, "documentary")

    def test_unknown_kind_returns_movie(self) -> None:
        from src.organizing.categorizer import categorize_tmdb_media

        result = categorize_tmdb_media(kind=None, genre_ids=(), title_hint=None)

        self.assertEqual(result, "movie")


if __name__ == "__main__":
    unittest.main()
