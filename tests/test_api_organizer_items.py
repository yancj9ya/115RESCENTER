from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.organizing.repository import OrganizeRepository


class OrganizerItemsApiTest(unittest.TestCase):
    def _client(self, db_path: Path) -> TestClient:
        app = create_app(db_path=db_path, settings=None)
        return TestClient(app)

    def _seed(self, db_path: Path) -> None:
        repo = OrganizeRepository(db_path)
        repo.init_schema()
        run = repo.create_run(staging_cid=9001)
        success_item = repo.create_item(
            run.id, file_id=1, file_name="Movie.A.2026.mkv", status="PLANNED",
            target_cid=3001, target_path="国产/Movie A (2026)", new_name="Movie A (2026).mkv",
        )
        repo.mark_item_success(
            success_item.id, target_cid=3001, target_path="国产/Movie A (2026)",
            new_name="Movie A (2026).mkv", reason="matched", metadata={"title": "Movie A"},
        )
        skip_item = repo.create_item(
            run.id, file_id=2, file_name="Sisters.2020.S07.mkv", status="PLANNED",
            target_cid=None, target_path="综艺/乘风破浪的姐姐 (2020)",
        )
        repo.mark_item_skipped(skip_item.id, status="SKIPPED_DUPLICATE", reason="dup")
        dir_item = repo.create_item(
            run.id, file_id=3, file_name="Season 1", is_dir=True, status="PLANNED",
        )
        repo.mark_item_skipped(dir_item.id, status="SKIPPED_DIR", reason="directory recursed")
        repo.finish_run(run.id, planned_count=2, success_count=1, skipped_count=2, failed_count=0, status="PARTIAL_SUCCESS")

    def test_lists_items_across_runs_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            response = self._client(db_path).get("/log-center/organizer/items")

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 2)
        # directory items are excluded — organize records are file-only
        self.assertTrue(all(item["is_dir"] is False for item in items))
        self.assertNotIn("SKIPPED_DIR", [item["status"] for item in items])
        # newest (higher id) first
        self.assertEqual(items[0]["status"], "SKIPPED_DUPLICATE")
        self.assertEqual(items[0]["file_name"], "Sisters.2020.S07.mkv")
        self.assertEqual(items[1]["status"], "SUCCESS")

    def test_status_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            response = self._client(db_path).get("/log-center/organizer/items?status=SUCCESS")

        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "SUCCESS")

    def test_invalid_status_returns_422(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            response = self._client(db_path).get("/log-center/organizer/items?status=BOGUS")

        self.assertEqual(response.status_code, 422)

    def test_keyword_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            response = self._client(db_path).get("/log-center/organizer/items?keyword=Sisters")

        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["file_name"], "Sisters.2020.S07.mkv")

    def test_delete_single_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            client = self._client(db_path)
            target = client.get("/log-center/organizer/items").json()["items"][0]
            delete_response = client.delete(f"/log-center/organizer/items/{target['id']}")
            self.assertEqual(delete_response.status_code, 200)
            self.assertTrue(delete_response.json()["deleted"])
            remaining = client.get("/log-center/organizer/items").json()["items"]
            self.assertEqual(len(remaining), 1)
            self.assertNotIn(target["id"], [item["id"] for item in remaining])

    def test_delete_missing_item_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            response = self._client(db_path).delete("/log-center/organizer/items/999999")

        self.assertEqual(response.status_code, 404)

    def test_delete_all_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "api.db"
            self._seed(db_path)
            client = self._client(db_path)
            delete_response = client.delete("/log-center/organizer/items")
            self.assertEqual(delete_response.status_code, 200)
            # all 3 seeded items (incl. directory) removed
            self.assertEqual(delete_response.json()["deleted"], 3)
            remaining = client.get("/log-center/organizer/items").json()["items"]
            self.assertEqual(len(remaining), 0)


if __name__ == "__main__":
    unittest.main()
