from __future__ import annotations

import unittest
from typing import Any

from src.organizing import (
    MEDIA_KIND_MOVIE,
    MEDIA_KIND_SERIES,
    OrganizeMetadata,
    TmdbConfig,
    TmdbCredentialError,
    TmdbMovieResolver,
    TmdbMultiResolver,
    TmdbRetryableError,
)
from src.organizing.tmdb import TmdbError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> FakeResponse:
        self.requests.append({"url": url, "headers": headers, "params": params})
        return self.response


class FakeSequenceClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> FakeResponse:
        self.requests.append({"url": url, "headers": headers, "params": params})
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


class TmdbMovieResolverTest(unittest.TestCase):
    def make_resolver(self, response: FakeResponse) -> tuple[TmdbMovieResolver, FakeClient]:
        client = FakeClient(response)
        config = TmdbConfig(bearer_token="token", base_url="https://example.test/3")
        return TmdbMovieResolver(config, client=client), client

    def test_resolve_movie_sends_request_url_headers_and_params(self) -> None:
        resolver, client = self.make_resolver(
            FakeResponse(200, {"results": [{"title": "电影", "release_date": "2024-01-02"}]})
        )

        metadata = resolver.resolve_movie("query", year=2024)

        self.assertEqual(metadata, OrganizeMetadata(title="电影", year=2024, kind=MEDIA_KIND_MOVIE))
        self.assertEqual(len(client.requests), 1)
        request = client.requests[0]
        self.assertEqual(request["url"], "https://example.test/3/search/movie")
        self.assertEqual(
            request["headers"],
            {"Authorization": "Bearer token", "Accept": "application/json"},
        )
        self.assertEqual(request["params"], {"query": "query", "language": "zh-CN", "year": 2024})

    def test_resolve_movie_uses_first_result_metadata(self) -> None:
        resolver, _client = self.make_resolver(
            FakeResponse(
                200,
                {
                    "results": [
                        {"title": "First", "release_date": "1999-12-31"},
                        {"title": "Second", "release_date": "2020-01-01"},
                    ]
                },
            )
        )

        metadata = resolver.resolve_movie("movie")

        self.assertEqual(metadata, OrganizeMetadata(title="First", year=1999, kind=MEDIA_KIND_MOVIE))

    def test_resolve_movie_fetches_detail_for_region_metadata(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [{"id": 42, "title": "国产片", "release_date": "2024-01-02"}]}),
                FakeResponse(
                    200,
                    {
                        "production_countries": [
                            {"iso_3166_1": "CN", "name": "China"},
                            {"iso_3166_1": "HK", "name": "Hong Kong"},
                        ],
                        "production_companies": [{"origin_country": "US"}],
                    },
                ),
            ]
        )
        config = TmdbConfig(bearer_token="token", base_url="https://example.test/3")
        resolver = TmdbMovieResolver(config, client=client)

        metadata = resolver.resolve_movie("movie")

        self.assertEqual(
            metadata,
            OrganizeMetadata(
                title="国产片",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                tmdb_id=42,
                region_primary="CN",
                region_candidates=("CN", "HK"),
                region_category="国产",
                region_source="production_countries",
                region_confidence="high",
            ),
        )
        self.assertEqual([request["url"] for request in client.requests], [
            "https://example.test/3/search/movie",
            "https://example.test/3/movie/42",
        ])
        self.assertEqual(client.requests[1]["params"], {"language": "zh-CN"})

    def test_resolve_movie_falls_back_to_detail_production_company_country(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [{"id": 7, "title": "Studio Movie", "release_date": "2020-01-01"}]}),
                FakeResponse(200, {"production_countries": [], "production_companies": [{"origin_country": "JP"}]}),
            ]
        )
        resolver = TmdbMovieResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_movie("movie")

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.region_primary, "JP")
        self.assertEqual(metadata.region_candidates, ("JP",))
        self.assertEqual(metadata.region_category, "日韩")
        self.assertEqual(metadata.region_source, "production_companies")
        self.assertEqual(metadata.region_confidence, "medium")

        resolver, _client = self.make_resolver(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "title": "国产片",
                            "release_date": "2024-01-02",
                            "production_countries": [
                                {"iso_3166_1": "CN", "name": "China"},
                                {"iso_3166_1": "HK", "name": "Hong Kong"},
                            ],
                            "production_companies": [{"origin_country": "US"}],
                        }
                    ]
                },
            )
        )

        metadata = resolver.resolve_movie("movie")

        self.assertEqual(
            metadata,
            OrganizeMetadata(
                title="国产片",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                region_primary="CN",
                region_candidates=("CN", "HK"),
                region_category="国产",
                region_source="production_countries",
                region_confidence="high",
            ),
        )

    def test_resolve_movie_falls_back_to_production_company_country(self) -> None:
        resolver, _client = self.make_resolver(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "title": "Studio Movie",
                            "release_date": "2020-01-01",
                            "production_countries": [],
                            "production_companies": [{"origin_country": "JP"}],
                        }
                    ]
                },
            )
        )

        metadata = resolver.resolve_movie("movie")

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.region_primary, "JP")
        self.assertEqual(metadata.region_candidates, ("JP",))
        self.assertEqual(metadata.region_category, "日韩")
        self.assertEqual(metadata.region_source, "production_companies")
        self.assertEqual(metadata.region_confidence, "medium")

    def test_resolve_movie_uses_search_summary_when_result_has_no_numeric_id(self) -> None:
        resolver, client = self.make_resolver(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "not-numeric",
                            "title": "Summary Movie",
                            "release_date": "2024-01-02",
                            "production_countries": [{"iso_3166_1": "KR", "name": "South Korea"}],
                        }
                    ]
                },
            )
        )

        metadata = resolver.resolve_movie("movie")

        self.assertEqual(len(client.requests), 1)
        self.assertEqual(
            metadata,
            OrganizeMetadata(
                title="Summary Movie",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                region_primary="KR",
                region_candidates=("KR",),
                region_category="日韩",
                region_source="production_countries",
                region_confidence="high",
            ),
        )

    def test_resolve_movie_uses_unknown_region_when_detail_has_no_region(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [{"id": 99, "title": "No Region", "release_date": "2024-01-02"}]}),
                FakeResponse(200, {"production_countries": [], "production_companies": []}),
            ]
        )
        resolver = TmdbMovieResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_movie("movie")

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertIsNone(metadata.region_primary)
        self.assertEqual(metadata.region_candidates, ())
        self.assertIsNone(metadata.region_category)
        self.assertIsNone(metadata.region_source)
        self.assertEqual(metadata.region_confidence, "low")

        for result in ({"title": "Invalid", "release_date": "not-a-date"}, {"title": "Missing"}):
            resolver, _client = self.make_resolver(FakeResponse(200, {"results": [result]}))

            metadata = resolver.resolve_movie("movie")

            self.assertIsNotNone(metadata)
            assert metadata is not None
            self.assertIsNone(metadata.year)

    def test_resolve_movie_raises_value_error_for_empty_query(self) -> None:
        resolver, _client = self.make_resolver(FakeResponse(200, {"results": []}))

        with self.assertRaises(ValueError):
            resolver.resolve_movie("   ")

    def test_resolve_movie_raises_credential_error_for_401(self) -> None:
        resolver, _client = self.make_resolver(FakeResponse(401, {"status_message": "bad token"}))

        with self.assertRaises(TmdbCredentialError):
            resolver.resolve_movie("movie")

    def test_resolve_movie_raises_retryable_error_for_429_500_and_503(self) -> None:
        for status_code in (429, 500, 503):
            resolver, _client = self.make_resolver(FakeResponse(status_code, {}))

            with self.assertRaises(TmdbRetryableError):
                resolver.resolve_movie("movie")

    def test_resolve_movie_raises_tmdb_error_for_other_non_200(self) -> None:
        resolver, _client = self.make_resolver(FakeResponse(404, {}))

        with self.assertRaises(TmdbError):
            resolver.resolve_movie("movie")

    def test_resolve_movie_omits_year_param_when_not_provided(self) -> None:
        resolver, client = self.make_resolver(FakeResponse(200, {"results": []}))

        resolver.resolve_movie("query")

        self.assertEqual(client.requests[0]["params"], {"query": "query", "language": "zh-CN"})

    def test_resolve_movie_omits_empty_language_param(self) -> None:
        client = FakeClient(FakeResponse(200, {"results": []}))
        config = TmdbConfig(bearer_token="token", language="", base_url="https://example.test/3")
        resolver = TmdbMovieResolver(config, client=client)

        resolver.resolve_movie("query", year=2024)

        self.assertEqual(client.requests[0]["params"], {"query": "query", "year": 2024})

    def test_tmdb_symbols_are_exported_from_package(self) -> None:
        import src.organizing as organizing

        self.assertIs(organizing.TmdbConfig, TmdbConfig)
        self.assertIs(organizing.TmdbMovieResolver, TmdbMovieResolver)
        self.assertIs(organizing.TmdbError, TmdbError)
        self.assertIs(organizing.TmdbCredentialError, TmdbCredentialError)
        self.assertIs(organizing.TmdbRetryableError, TmdbRetryableError)


class TmdbMultiResolverTest(unittest.TestCase):
    def test_resolve_multi_fetches_movie_detail_and_returns_movie_metadata(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [{"id": 42, "media_type": "movie", "title": "Movie", "release_date": "2024-02-03"}]}),
                FakeResponse(200, {"production_countries": [{"iso_3166_1": "US", "name": "United States"}]}),
            ]
        )
        resolver = TmdbMultiResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_multi("Movie", year=2024)

        self.assertEqual(
            metadata,
            OrganizeMetadata(
                title="Movie",
                year=2024,
                kind=MEDIA_KIND_MOVIE,
                tmdb_id=42,
                region_primary="US",
                region_candidates=("US",),
                region_category="欧美",
                region_source="production_countries",
                region_confidence="high",
            ),
        )
        self.assertEqual([request["url"] for request in client.requests], [
            "https://example.test/3/search/multi",
            "https://example.test/3/movie/42",
        ])
        self.assertEqual(client.requests[0]["params"], {"query": "Movie", "language": "zh-CN", "year": 2024})

    def test_resolve_multi_fetches_tv_detail_and_returns_series_metadata_for_zhu_yu(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [{"id": 279388, "media_type": "tv", "name": "逐玉", "first_air_date": "2026-03-06"}]}),
                FakeResponse(
                    200,
                    {
                        "origin_country": ["CN"],
                        "production_countries": [{"iso_3166_1": "CN", "name": "China"}],
                        "networks": [{"name": "iQiyi", "origin_country": "CN"}],
                    },
                ),
            ]
        )
        resolver = TmdbMultiResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_multi("逐玉")

        self.assertEqual(
            metadata,
            OrganizeMetadata(
                title="逐玉",
                year=2026,
                kind=MEDIA_KIND_SERIES,
                tmdb_id=279388,
                region_primary="CN",
                region_candidates=("CN",),
                region_category="国产",
                region_source="origin_country",
                region_confidence="high",
            ),
        )
        self.assertEqual([request["url"] for request in client.requests], [
            "https://example.test/3/search/multi",
            "https://example.test/3/tv/279388",
        ])

    def test_resolve_multi_tv_carries_genre_ids_from_search_and_detail(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [
                    {"id": 7, "media_type": "tv", "name": "动画剧", "first_air_date": "2025-01-01", "genre_ids": [16, 10759]},
                ]}),
                FakeResponse(200, {"origin_country": ["JP"], "genres": [{"id": 16, "name": "动画"}, {"id": 35, "name": "喜剧"}]}),
            ]
        )
        resolver = TmdbMultiResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_multi("动画剧")

        assert metadata is not None
        # 搜索结果的 genre_ids 与详情的 genres 合并去重，供分类器判定动画/综艺/纪录片
        self.assertEqual(metadata.genre_ids, (16, 10759, 35))
        self.assertEqual(metadata.tmdb_id, 7)

    def test_resolve_multi_movie_carries_genre_ids(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(200, {"results": [
                    {"id": 9, "media_type": "movie", "title": "纪录电影", "release_date": "2024-01-01", "genre_ids": [99]},
                ]}),
                FakeResponse(200, {"production_countries": [{"iso_3166_1": "US"}]}),
            ]
        )
        resolver = TmdbMultiResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_multi("纪录电影")

        assert metadata is not None
        self.assertEqual(metadata.genre_ids, (99,))
        self.assertEqual(metadata.tmdb_id, 9)

    def test_resolve_multi_skips_person_and_uses_next_supported_result(self) -> None:
        client = FakeSequenceClient(
            [
                FakeResponse(
                    200,
                    {
                        "results": [
                            {"id": 1, "media_type": "person", "name": "Actor"},
                            {"id": 2, "media_type": "tv", "name": "Series", "first_air_date": "2025-01-01"},
                        ]
                    },
                ),
                FakeResponse(200, {"origin_country": ["KR"]}),
            ]
        )
        resolver = TmdbMultiResolver(TmdbConfig(bearer_token="token", base_url="https://example.test/3"), client=client)

        metadata = resolver.resolve_multi("Series")

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata.kind, MEDIA_KIND_SERIES)
        self.assertEqual(metadata.title, "Series")
        self.assertEqual(metadata.region_category, "日韩")

    def test_resolve_multi_returns_none_for_empty_or_unsupported_results(self) -> None:
        for payload in ({"results": []}, {"results": [{"id": 1, "media_type": "person", "name": "Actor"}]}):
            resolver, _client = self.make_multi_resolver(FakeResponse(200, payload))

            self.assertIsNone(resolver.resolve_multi("missing"))

    def test_resolve_multi_raises_value_error_for_empty_query(self) -> None:
        resolver, _client = self.make_multi_resolver(FakeResponse(200, {"results": []}))

        with self.assertRaises(ValueError):
            resolver.resolve_multi("   ")

    def test_multi_symbols_are_exported_from_package(self) -> None:
        import src.organizing as organizing

        self.assertIs(organizing.TmdbMultiResolver, TmdbMultiResolver)

    def make_multi_resolver(self, response: FakeResponse) -> tuple["TmdbMultiResolver", FakeClient]:
        client = FakeClient(response)
        config = TmdbConfig(bearer_token="token", base_url="https://example.test/3")
        return TmdbMultiResolver(config, client=client), client


if __name__ == "__main__":
    unittest.main()
