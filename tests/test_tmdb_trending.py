from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any


@dataclass
class _StubResponse:
    status_code: int
    payload: Any

    def json(self) -> Any:
        return self.payload


class _StubClient:
    def __init__(self, responses: dict[str, _StubResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> _StubResponse:
        self.calls.append((url, dict(params), dict(headers)))
        if url not in self._responses:
            raise AssertionError(f"unexpected TMDB url: {url}")
        return self._responses[url]


def _config() -> Any:
    from src.organizing.tmdb import TmdbConfig

    return TmdbConfig(bearer_token="token", language="zh-CN")


_BASE = "https://api.themoviedb.org/3"


class TmdbTrendingTest(unittest.TestCase):
    def test_trending_tv_week_uses_media_type_and_name_fields(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            f"{_BASE}/trending/tv/week": _StubResponse(
                200,
                {
                    "results": [
                        {
                            "id": 10,
                            "media_type": "tv",
                            "name": "剧 X",
                            "original_name": "Show X",
                            "first_air_date": "2025-03-01",
                            "overview": "desc",
                            "poster_path": "/x.jpg",
                        }
                    ]
                },
            )
        }
        client = _StubClient(responses)
        service = TmdbDiscoveryService(_config(), client=client)

        results = service.fetch_trending("trending_tv_week")

        self.assertEqual(client.calls[0][0], f"{_BASE}/trending/tv/week")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tmdb_id, 10)
        self.assertEqual(results[0].kind, "tv")
        self.assertEqual(results[0].title, "剧 X")
        self.assertEqual(results[0].original_title, "Show X")
        self.assertEqual(results[0].year, 2025)
        self.assertEqual(results[0].poster_path, "/x.jpg")

    def test_trending_movie_week_uses_media_type_and_title_fields(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            f"{_BASE}/trending/movie/week": _StubResponse(
                200,
                {
                    "results": [
                        {
                            "id": 20,
                            "media_type": "movie",
                            "title": "电影 Y",
                            "original_title": "Movie Y",
                            "release_date": "2024-06-15",
                            "poster_path": "/y.jpg",
                        }
                    ]
                },
            )
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))

        results = service.fetch_trending("trending_movie_week")

        self.assertEqual(results[0].kind, "movie")
        self.assertEqual(results[0].title, "电影 Y")
        self.assertEqual(results[0].year, 2024)

    def test_tv_on_the_air_defaults_kind_to_tv(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            f"{_BASE}/tv/on_the_air": _StubResponse(
                200,
                {
                    "results": [
                        {
                            "id": 30,
                            "name": "在播剧",
                            "original_name": "On Air",
                            "first_air_date": "2026-01-10",
                        }
                    ]
                },
            )
        }
        client = _StubClient(responses)
        service = TmdbDiscoveryService(_config(), client=client)

        results = service.fetch_trending("tv_on_the_air")

        self.assertEqual(client.calls[0][0], f"{_BASE}/tv/on_the_air")
        self.assertEqual(results[0].kind, "tv")
        self.assertEqual(results[0].title, "在播剧")
        self.assertEqual(results[0].year, 2026)

    def test_tv_popular_defaults_kind_to_tv(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            f"{_BASE}/tv/popular": _StubResponse(
                200,
                {"results": [{"id": 40, "name": "热门剧", "first_air_date": "2022-09-09"}]},
            )
        }
        client = _StubClient(responses)
        service = TmdbDiscoveryService(_config(), client=client)

        results = service.fetch_trending("tv_popular")

        self.assertEqual(client.calls[0][0], f"{_BASE}/tv/popular")
        self.assertEqual(results[0].kind, "tv")
        self.assertEqual(results[0].title, "热门剧")

    def test_trending_honours_limit(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            f"{_BASE}/tv/popular": _StubResponse(
                200,
                {
                    "results": [
                        {"id": i, "name": f"t{i}", "first_air_date": "2020-01-01"}
                        for i in range(1, 6)
                    ]
                },
            )
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))

        results = service.fetch_trending("tv_popular", limit=2)

        self.assertEqual([r.tmdb_id for r in results], [1, 2])

    def test_trending_rejects_invalid_list_key(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        service = TmdbDiscoveryService(_config(), client=_StubClient({}))
        with self.assertRaises(ValueError):
            service.fetch_trending("not_a_list")

    def test_trending_rejects_non_positive_limit(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        service = TmdbDiscoveryService(_config(), client=_StubClient({}))
        with self.assertRaises(ValueError):
            service.fetch_trending("tv_popular", limit=0)

    def test_trending_credential_failure_propagates(self) -> None:
        from src.organizing.tmdb import TmdbCredentialError
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {f"{_BASE}/tv/popular": _StubResponse(401, {})}
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))
        with self.assertRaises(TmdbCredentialError):
            service.fetch_trending("tv_popular")


if __name__ == "__main__":
    unittest.main()
