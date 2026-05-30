from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.settings import AppSettings


class FastApiCorsTest(unittest.TestCase):
    def build_client(self) -> TestClient:
        return TestClient(
            create_app(
                settings=AppSettings(
                    api_cors_origins=(
                        "https://allowed.example",
                        "http://localhost:5173",
                    )
                )
            )
        )

    def test_preflight_allows_configured_origin(self) -> None:
        client = self.build_client()

        response = client.options(
            "/health",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "https://allowed.example")
        self.assertEqual(response.headers.get("access-control-allow-methods"), "GET, POST, PATCH, DELETE, OPTIONS")
        self.assertEqual(response.headers.get("access-control-allow-headers"), "Accept, Accept-Language, Content-Language, Content-Type")

    def test_preflight_disallowed_origin_does_not_match_allow_origin_header(self) -> None:
        client = self.build_client()

        response = client.options(
            "/health",
            headers={
                "Origin": "https://blocked.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "https://blocked.example")

    def test_health_get_still_returns_ok_with_origin_header(self) -> None:
        client = self.build_client()

        response = client.get(
            "/health",
            headers={"Origin": "https://allowed.example"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers.get("access-control-allow-origin"), "https://allowed.example")


if __name__ == "__main__":
    unittest.main()
