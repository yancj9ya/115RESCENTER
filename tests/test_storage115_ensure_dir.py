from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any


@dataclass
class _FakeItem:
    file_id: int
    name: str
    is_dir: bool = True
    parent_id: int = 0


class _FakeFs:
    def __init__(self) -> None:
        self.mkdir_calls: list[tuple[int, str]] = []
        self.next_id = 1000

    def mkdir(self, parent_cid: int, name: str) -> dict[str, Any]:
        self.mkdir_calls.append((int(parent_cid), name))
        self.next_id += 1
        return {"file_id": self.next_id, "file_name": name, "parent_id": int(parent_cid), "is_dir": True}


class _FakeStorage:
    def __init__(self, existing: dict[int, list[_FakeItem]] | None = None) -> None:
        self._existing = {k: list(v) for k, v in (existing or {}).items()}
        self.fs = _FakeFs()
        self.list_calls: list[int] = []

    def list_folder(self, cid: int | str = 0):
        cid_int = int(cid)
        self.list_calls.append(cid_int)
        return self._existing.get(cid_int, [])


def _patched_service():
    from src.storage.service115 import Storage115Item, Storage115Service

    class _ServiceWithFakes(Storage115Service):
        def __init__(self, fake: _FakeStorage) -> None:
            self._fake = fake
            self._ensure_dir_cache: dict[tuple[int, str], int] = {}

        @property
        def fs(self):
            return self._fake.fs

        def list_folder(self, cid: int | str = 0):
            raw = self._fake.list_folder(cid)
            return [
                Storage115Item(id=item.file_id, name=item.name, is_dir=item.is_dir, parent_id=item.parent_id)
                for item in raw
            ]

    return _ServiceWithFakes


class EnsureDirCreatesAndCachesTest(unittest.TestCase):
    def test_ensure_dir_creates_when_missing_and_returns_cid(self) -> None:
        fake = _FakeStorage()
        service = _patched_service()(fake)

        cid = service.ensure_dir(100, "movies")

        self.assertEqual(cid, 1001)
        self.assertEqual(fake.fs.mkdir_calls, [(100, "movies")])

    def test_ensure_dir_caches_lookup_within_run(self) -> None:
        fake = _FakeStorage()
        service = _patched_service()(fake)

        cid1 = service.ensure_dir(100, "movies")
        cid2 = service.ensure_dir(100, "movies")

        self.assertEqual(cid1, cid2)
        self.assertEqual(len(fake.fs.mkdir_calls), 1)
        self.assertEqual(len(fake.list_calls), 1)

    def test_ensure_dir_returns_existing_cid_when_already_present(self) -> None:
        existing = {100: [_FakeItem(file_id=555, name="movies")]}
        fake = _FakeStorage(existing)
        service = _patched_service()(fake)

        cid = service.ensure_dir(100, "movies")

        self.assertEqual(cid, 555)
        self.assertEqual(fake.fs.mkdir_calls, [])

    def test_ensure_dir_rejects_blank_name(self) -> None:
        from src.storage.service115 import Storage115Error

        fake = _FakeStorage()
        service = _patched_service()(fake)

        with self.assertRaises(Storage115Error):
            service.ensure_dir(100, "   ")

    def test_ensure_dir_cache_keyed_by_parent_and_name(self) -> None:
        fake = _FakeStorage()
        service = _patched_service()(fake)

        cid_a = service.ensure_dir(100, "movies")
        cid_b = service.ensure_dir(200, "movies")
        cid_a2 = service.ensure_dir(100, "movies")

        self.assertNotEqual(cid_a, cid_b)
        self.assertEqual(cid_a, cid_a2)
        self.assertEqual(len(fake.fs.mkdir_calls), 2)


if __name__ == "__main__":
    unittest.main()
