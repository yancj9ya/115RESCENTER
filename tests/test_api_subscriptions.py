from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.schemas import (
    SubscriptionCreateRequest,
    SubscriptionDeleteResponse,
    SubscriptionListResponse,
    SubscriptionProcessRequest,
    SubscriptionProcessResponse,
    SubscriptionResponse,
    SubscriptionTestRequest,
    SubscriptionTestResponse,
    SubscriptionUpdateRequest,
)
from src.config.settings import AppSettings
from src.queue.models import ShareLink
from src.queue.repository import QueueRepository
from src.subscriptions.repository import SubscriptionRepository

try:
    from src.api.app import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    CREATE_APP_IMPORT_ERROR = import_error
else:
    CREATE_APP_IMPORT_ERROR = None


class SubscriptionApiContractSchemaTest(unittest.TestCase):
    def test_subscription_response_has_exact_v1_rule_fields(self) -> None:
        payload = SubscriptionResponse(
            id=1,
            name="Movies 1080p",
            pattern="1080p",
            enabled=True,
            created_at="2026-05-27T10:00:00",
            updated_at="2026-05-27T10:00:00",
        ).model_dump()

        self.assertEqual(
            payload,
            {
                "id": 1,
                "name": "Movies 1080p",
                "pattern": "1080p",
                "enabled": True,
                "created_at": "2026-05-27T10:00:00",
                "updated_at": "2026-05-27T10:00:00",
                "tmdb_id": None,
                "tmdb_kind": None,
                "year": None,
                "require_year_match": True,
                "aliases": [],
                "poster_path": None,
            },
        )
        self.assertNotIn("target_cid", payload)
        self.assertNotIn("auth", payload)

    def test_subscription_request_and_summary_schema_contracts_are_explicit(self) -> None:
        create_payload = SubscriptionCreateRequest(name="Movies", pattern="1080p", enabled=True).model_dump()
        update_payload = SubscriptionUpdateRequest(name=None, pattern="4k", enabled=False).model_dump()
        test_payload = SubscriptionTestRequest(pattern="S\\d{2}E\\d{2}", text="Show S01E02").model_dump()
        process_payload = SubscriptionProcessRequest(limit=100).model_dump()
        list_response = SubscriptionListResponse(items=[]).model_dump()
        test_response = SubscriptionTestResponse(matched=True).model_dump()
        process_response = SubscriptionProcessResponse(
            scanned=1,
            matched=1,
            created=1,
            skipped=0,
            errors=[],
        ).model_dump()

        self.assertEqual(
            create_payload,
            {
                "name": "Movies",
                "pattern": "1080p",
                "enabled": True,
                "tmdb_id": None,
                "tmdb_kind": None,
                "year": None,
                "require_year_match": True,
                "aliases": [],
                "poster_path": None,
            },
        )
        self.assertEqual(
            update_payload,
            {
                "name": None,
                "pattern": "4k",
                "enabled": False,
                "tmdb_id": None,
                "tmdb_kind": None,
                "year": None,
                "require_year_match": None,
                "aliases": None,
                "poster_path": None,
            },
        )
        self.assertEqual(test_payload, {"pattern": "S\\d{2}E\\d{2}", "text": "Show S01E02"})
        self.assertEqual(process_payload, {"limit": 100})
        self.assertEqual(list_response, {"items": []})
        self.assertEqual(test_response, {"matched": True})
        self.assertEqual(process_response, {"scanned": 1, "matched": 1, "created": 1, "skipped": 0, "errors": []})

    def test_frozen_api_model_prevents_contract_mutation(self) -> None:
        response = SubscriptionResponse(
            id=1,
            name="Movies 1080p",
            pattern="1080p",
            enabled=True,
            created_at="2026-05-27T10:00:00",
            updated_at="2026-05-27T10:00:00",
        )

        with self.assertRaises(ValidationError):
            response.name = "Changed"  # type: ignore[misc]


class FastApiSubscriptionEndpointContractTest(unittest.TestCase):
    def build_client(self, db_path: Path, settings: AppSettings | None = None) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app(db_path=db_path, settings=settings))

    def seed_matching_collect_item(
        self,
        db_path: Path,
        *,
        message_id: str = "101",
        share_code: str = "abc123",
        receive_code: str = "xy9z",
    ) -> QueueRepository:
        queue_repository = QueueRepository(db_path)
        queue_repository.init_schema()
        subscription_repository = SubscriptionRepository(db_path)
        subscription_repository.init_schema()
        if not subscription_repository.list_rules():
            subscription_repository.create_rule(name="Movies", pattern="Movie", enabled=True)
        share_url = f"https://115.com/s/{share_code}#{receive_code}"
        queue_repository.enqueue_collected_message(
            source_type="telegram_web",
            source_id="movie_channel",
            message_id=message_id,
            message_url=f"https://t.me/s/movie_channel/{message_id}",
            message_text=f"Movie release {share_url}",
            published_at=None,
            shares=[ShareLink(share_code=share_code, receive_code=receive_code, share_url=share_url)],
        )
        return queue_repository

    def test_subscription_list_endpoint_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "queue.db").get("/subscriptions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

    def test_subscription_create_get_patch_delete_endpoint_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "queue.db")
            created = client.post(
                "/subscriptions",
                json={"name": "Movies 1080p", "pattern": "1080p", "enabled": True},
            )

            self.assertIn(created.status_code, {200, 201})
            created_payload = created.json()
            self.assertEqual(
                set(created_payload),
                {"id", "name", "pattern", "enabled", "created_at", "updated_at", "tmdb_id", "tmdb_kind", "year", "require_year_match", "aliases", "poster_path"},
            )
            self.assertEqual(created_payload["name"], "Movies 1080p")
            self.assertEqual(created_payload["pattern"], "1080p")
            self.assertTrue(created_payload["enabled"])
            self.assertNotIn("target_cid", created_payload)
            self.assertNotIn("auth", created_payload)

            rule_id = created_payload["id"]
            fetched = client.get(f"/subscriptions/{rule_id}")
            patched = client.patch(f"/subscriptions/{rule_id}", json={"enabled": False})
            deleted = client.delete(f"/subscriptions/{rule_id}")

        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), created_payload)
        self.assertEqual(patched.status_code, 200)
        self.assertFalse(patched.json()["enabled"])
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(SubscriptionDeleteResponse(**deleted.json()).model_dump(), {"deleted": True})

    def test_subscription_test_endpoint_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "queue.db").post(
                "/subscriptions/test",
                json={"pattern": "S\\d{2}E\\d{2}", "text": "Show S01E02"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"matched": True})

    def test_subscription_process_endpoint_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = self.build_client(Path(tmp_dir) / "queue.db", settings=AppSettings()).post(
                "/subscriptions/process",
                json={"limit": 100},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("P115_TRANSFER_CID", response.json()["detail"])

    def test_subscription_invalid_regex_returns_422(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "queue.db")
            create_response = client.post(
                "/subscriptions",
                json={"name": "Broken", "pattern": "[", "enabled": True},
            )
            test_response = client.post(
                "/subscriptions/test",
                json={"pattern": "[", "text": "anything"},
            )

        self.assertEqual(create_response.status_code, 422)
        self.assertEqual(test_response.status_code, 422)

    def test_subscription_missing_id_returns_404_for_read_update_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = self.build_client(Path(tmp_dir) / "queue.db")
            fetched = client.get("/subscriptions/404")
            patched = client.patch("/subscriptions/404", json={"enabled": False})
            deleted = client.delete("/subscriptions/404")

        self.assertEqual(fetched.status_code, 404)
        self.assertEqual(patched.status_code, 404)
        self.assertEqual(deleted.status_code, 404)

    def test_subscription_process_endpoint_returns_summary_when_staging_cid_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = TestClient(
                create_app(db_path=Path(tmp_dir) / "queue.db", settings=AppSettings(transfer_cid=9001))
            ).post(
                "/subscriptions/process",
                json={"limit": 100},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"scanned", "matched", "created", "skipped", "errors"},
        )
        SubscriptionProcessResponse(**response.json())

    def test_subscription_process_endpoint_creates_one_transfer_candidate_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            queue_repository = self.seed_matching_collect_item(db_path)
            client = self.build_client(db_path, settings=AppSettings(transfer_cid=9001))

            first_response = client.post("/subscriptions/process", json={"limit": 100})
            first_transfer_records = queue_repository.list_transfer_queue()
            repeated_response = client.post("/subscriptions/process", json={"limit": 100})
            repeated_transfer_records = queue_repository.list_transfer_queue()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(
            first_response.json(),
            {"scanned": 1, "matched": 1, "created": 1, "skipped": 0, "errors": []},
        )
        self.assertEqual(len(first_transfer_records), 1)
        self.assertEqual(first_transfer_records[0].share_code, "abc123")
        self.assertEqual(first_transfer_records[0].receive_code, "xy9z")
        self.assertEqual(first_transfer_records[0].staging_cid, 9001)
        self.assertEqual(repeated_response.status_code, 200)
        self.assertEqual(
            repeated_response.json(),
            {"scanned": 0, "matched": 0, "created": 0, "skipped": 0, "errors": []},
        )
        self.assertEqual(len(repeated_transfer_records), 1)

    def test_subscription_process_endpoint_limit_scans_at_most_one_collect_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            queue_repository = self.seed_matching_collect_item(
                db_path,
                message_id="101",
                share_code="abc123",
                receive_code="xy9z",
            )
            self.seed_matching_collect_item(
                db_path,
                message_id="102",
                share_code="def456",
                receive_code="uv88",
            )
            response = self.build_client(db_path, settings=AppSettings(transfer_cid=9001)).post(
                "/subscriptions/process",
                json={"limit": 1},
            )
            transfer_records = queue_repository.list_transfer_queue()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"scanned": 1, "matched": 1, "created": 1, "skipped": 0, "errors": []},
        )
        self.assertEqual(len(transfer_records), 1)


class SubscriptionTmdbAwareEndpointTest(unittest.TestCase):
    def build_client(self, db_path: Path) -> TestClient:
        if create_app is None:
            raise unittest.SkipTest(f"src.api.app.create_app is not implemented yet: {CREATE_APP_IMPORT_ERROR}")
        return TestClient(create_app(db_path=db_path))

    def test_create_subscription_persists_tmdb_id_kind_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            response = client.post(
                "/subscriptions",
                json={
                    "name": "三体",
                    "pattern": "",
                    "enabled": True,
                    "tmdb_id": 108545,
                    "tmdb_kind": "tv",
                    "year": 2024,
                    "require_year_match": True,
                    "aliases": ["三体", "Three-Body", "3 Body Problem"],
                },
            )

            self.assertEqual(response.status_code, 201)
            payload = response.json()
            self.assertEqual(payload["tmdb_id"], 108545)
            self.assertEqual(payload["tmdb_kind"], "tv")
            self.assertEqual(payload["year"], 2024)
            self.assertTrue(payload["require_year_match"])
            self.assertEqual(payload["aliases"], ["三体", "Three-Body", "3 Body Problem"])

            fetched = client.get(f"/subscriptions/{payload['id']}").json()
            self.assertEqual(fetched["tmdb_id"], 108545)
            self.assertEqual(fetched["year"], 2024)
            self.assertTrue(fetched["require_year_match"])
            self.assertEqual(fetched["aliases"], ["三体", "Three-Body", "3 Body Problem"])

    def test_create_subscription_rejects_when_no_signals_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            response = client.post(
                "/subscriptions",
                json={"name": "Empty", "pattern": "", "enabled": True},
            )

        self.assertEqual(response.status_code, 422)

    def test_create_subscription_rejects_invalid_tmdb_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            response = client.post(
                "/subscriptions",
                json={
                    "name": "Bad",
                    "tmdb_id": 1,
                    "tmdb_kind": "person",
                    "aliases": [],
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_patch_subscription_updates_aliases_and_clears_tmdb_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            created = client.post(
                "/subscriptions",
                json={
                    "name": "三体",
                    "tmdb_id": 108545,
                    "tmdb_kind": "tv",
                    "year": 2024,
                    "require_year_match": True,
                    "aliases": ["三体", "Three-Body"],
                },
            ).json()

            patched = client.patch(
                f"/subscriptions/{created['id']}",
                json={"aliases": ["三体", "三体 (剧集)"]},
            )

            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["aliases"], ["三体", "三体 (剧集)"])
            self.assertEqual(patched.json()["tmdb_id"], 108545)
            self.assertEqual(patched.json()["year"], 2024)
            self.assertTrue(patched.json()["require_year_match"])

            patched2 = client.patch(
                f"/subscriptions/{created['id']}",
                json={"pattern": "三体", "tmdb_id": None, "year": None, "require_year_match": False, "aliases": []},
            )
            self.assertEqual(patched2.status_code, 200)
            self.assertIsNone(patched2.json()["tmdb_id"])
            self.assertIsNone(patched2.json()["year"])
            self.assertFalse(patched2.json()["require_year_match"])
            self.assertEqual(patched2.json()["aliases"], [])
            self.assertEqual(patched2.json()["pattern"], "三体")

    def test_patch_subscription_rejects_clearing_all_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            created = client.post(
                "/subscriptions",
                json={"name": "三体", "tmdb_id": 108545, "tmdb_kind": "tv", "aliases": ["三体"]},
            ).json()

            patched = client.patch(
                f"/subscriptions/{created['id']}",
                json={"pattern": "", "tmdb_id": None, "aliases": []},
            )

        self.assertEqual(patched.status_code, 422)

    def test_list_subscriptions_returns_tmdb_id_kind_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "queue.db"
            client = self.build_client(db_path)
            client.post(
                "/subscriptions",
                json={
                    "name": "三体",
                    "tmdb_id": 108545,
                    "tmdb_kind": "tv",
                    "year": 2024,
                    "require_year_match": True,
                    "aliases": ["三体", "Three-Body", "3 Body Problem"],
                },
            )
            client.post(
                "/subscriptions",
                json={
                    "name": "Inception",
                    "tmdb_id": 27205,
                    "tmdb_kind": "movie",
                    "year": 2010,
                    "require_year_match": False,
                    "aliases": ["盗梦空间", "Inception"],
                },
            )

            response = client.get("/subscriptions")

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 2)
        by_name = {item["name"]: item for item in items}
        self.assertEqual(by_name["三体"]["tmdb_kind"], "tv")
        self.assertEqual(by_name["三体"]["tmdb_id"], 108545)
        self.assertEqual(by_name["三体"]["year"], 2024)
        self.assertTrue(by_name["三体"]["require_year_match"])
        self.assertEqual(by_name["三体"]["aliases"], ["三体", "Three-Body", "3 Body Problem"])
        self.assertEqual(by_name["Inception"]["tmdb_kind"], "movie")
        self.assertEqual(by_name["Inception"]["year"], 2010)
        self.assertFalse(by_name["Inception"]["require_year_match"])
        self.assertEqual(by_name["Inception"]["aliases"], ["盗梦空间", "Inception"])


if __name__ == "__main__":
    unittest.main()
