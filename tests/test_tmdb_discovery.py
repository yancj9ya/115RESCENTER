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


class TmdbDiscoverySearchTest(unittest.TestCase):
    def test_search_multi_returns_movie_and_tv_results(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/search/multi": _StubResponse(
                200,
                {
                    "results": [
                        {
                            "id": 1,
                            "media_type": "movie",
                            "title": "电影 A",
                            "original_title": "Movie A",
                            "release_date": "2024-01-01",
                            "overview": "desc",
                            "poster_path": "/a.jpg",
                        },
                        {
                            "id": 2,
                            "media_type": "tv",
                            "name": "剧集 B",
                            "original_name": "Series B",
                            "first_air_date": "2023-05-20",
                            "overview": "",
                            "poster_path": None,
                        },
                        {"id": 3, "media_type": "person", "name": "Actor"},
                    ]
                },
            )
        }
        client = _StubClient(responses)
        service = TmdbDiscoveryService(_config(), client=client)

        results = service.search_multi("query")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tmdb_id, 1)
        self.assertEqual(results[0].kind, "movie")
        self.assertEqual(results[0].title, "电影 A")
        self.assertEqual(results[0].original_title, "Movie A")
        self.assertEqual(results[0].year, 2024)
        self.assertEqual(results[0].poster_path, "/a.jpg")
        self.assertEqual(results[1].tmdb_id, 2)
        self.assertEqual(results[1].kind, "tv")
        self.assertEqual(results[1].year, 2023)
        self.assertIsNone(results[1].poster_path)

    def test_search_multi_honours_limit(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/search/multi": _StubResponse(
                200,
                {
                    "results": [
                        {"id": i, "media_type": "movie", "title": f"t{i}", "release_date": "2020-01-01"}
                        for i in range(1, 6)
                    ]
                },
            )
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))

        results = service.search_multi("query", limit=2)

        self.assertEqual([r.tmdb_id for r in results], [1, 2])

    def test_search_multi_rejects_blank_query(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        service = TmdbDiscoveryService(_config(), client=_StubClient({}))
        with self.assertRaises(ValueError):
            service.search_multi("   ")

    def test_search_multi_credential_failure_propagates(self) -> None:
        from src.organizing.tmdb import TmdbCredentialError
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/search/multi": _StubResponse(401, {}),
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))
        with self.assertRaises(TmdbCredentialError):
            service.search_multi("query")


class TmdbDiscoveryAliasTest(unittest.TestCase):
    def test_collect_aliases_for_movie_merges_official_and_alternative_titles(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/movie/42": _StubResponse(
                200,
                {
                    "id": 42,
                    "title": "三体",
                    "original_title": "The Three-Body Problem",
                    "release_date": "2024-03-21",
                },
            ),
            "https://api.themoviedb.org/3/movie/42/alternative_titles": _StubResponse(
                200,
                {
                    "titles": [
                        {"iso_3166_1": "US", "title": "Three-Body"},
                        {"iso_3166_1": "JP", "title": "三体問題"},
                        {"iso_3166_1": "CN", "title": "三体"},
                    ]
                },
            ),
        }
        client = _StubClient(responses)
        service = TmdbDiscoveryService(_config(), client=client)

        bundle = service.collect_aliases("movie", 42)

        self.assertEqual(bundle.tmdb_id, 42)
        self.assertEqual(bundle.kind, "movie")
        self.assertEqual(bundle.title, "三体")
        self.assertEqual(bundle.original_title, "The Three-Body Problem")
        self.assertEqual(bundle.year, 2024)
        self.assertEqual(
            bundle.aliases,
            ("三体", "The Three-Body Problem", "Three-Body", "三体問題"),
        )

    def test_collect_aliases_for_tv_uses_results_block_and_name_fields(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/tv/108545": _StubResponse(
                200,
                {
                    "id": 108545,
                    "name": "三体 (剧集)",
                    "original_name": "Three-Body",
                    "first_air_date": "2023-01-15",
                },
            ),
            "https://api.themoviedb.org/3/tv/108545/alternative_titles": _StubResponse(
                200,
                {"results": [{"iso_3166_1": "US", "title": "3 Body Problem"}]},
            ),
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))

        bundle = service.collect_aliases("tv", 108545)

        self.assertEqual(bundle.year, 2023)
        self.assertEqual(
            bundle.aliases,
            ("三体 (剧集)", "Three-Body", "3 Body Problem"),
        )

    def test_collect_aliases_rejects_invalid_kind_or_id(self) -> None:
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        service = TmdbDiscoveryService(_config(), client=_StubClient({}))
        with self.assertRaises(ValueError):
            service.collect_aliases("person", 1)
        with self.assertRaises(ValueError):
            service.collect_aliases("movie", 0)

    def test_collect_aliases_retryable_failure_propagates(self) -> None:
        from src.organizing.tmdb import TmdbRetryableError
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        responses = {
            "https://api.themoviedb.org/3/movie/42": _StubResponse(503, {}),
        }
        service = TmdbDiscoveryService(_config(), client=_StubClient(responses))
        with self.assertRaises(TmdbRetryableError):
            service.collect_aliases("movie", 42)


class TmdbDiscoveryTransportErrorTest(unittest.TestCase):
    def test_search_multi_maps_transport_error_to_retryable(self) -> None:
        import httpx

        from src.organizing.tmdb import TmdbRetryableError
        from src.organizing.tmdb_discovery import TmdbDiscoveryService

        class _DisconnectingClient:
            def get(self, *_args: Any, **_kwargs: Any) -> Any:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

        service = TmdbDiscoveryService(_config(), client=_DisconnectingClient())
        with self.assertRaises(TmdbRetryableError):
            service.search_multi("query")


if __name__ == "__main__":
    unittest.main()
