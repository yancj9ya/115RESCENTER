from __future__ import annotations

import unittest

from src.storage.service115 import Storage115Service


class FakeP115Client:
    pass


class FakeP115FileSystem:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def readdir(self, cid: int | str = 0) -> list[dict[str, object]]:
        self.calls.append(("readdir", cid))
        return [
            {"id": "10", "name": "Movie.mkv", "is_dir": False, "parent_id": "900", "size": "123"},
            {"id": "11", "name": "Folder", "is_dir": True, "parent_id": "900"},
        ]

    def rename(self, file_id: int | str, name: str) -> dict[str, object]:
        self.calls.append(("rename", {"id": file_id, "name": name}))
        return {"state": True}

    def move(self, file_id: int | str, target_cid: int | str) -> dict[str, object]:
        self.calls.append(("move", {"id": file_id, "target_cid": target_cid}))
        return {"state": True}

    def mkdir(self, parent_cid: int | str, name: str) -> dict[str, object]:
        self.calls.append(("mkdir", {"parent_cid": parent_cid, "name": name}))
        return {"id": "31", "name": name, "is_dir": True, "parent_id": parent_cid}


class FakeP115ShareFileSystem:
    def __init__(self, calls: list[tuple[str, object]], share_code: str, receive_code: str | None) -> None:
        self.calls = calls
        self.share_code = share_code
        self.receive_code = receive_code
        self.calls.append(("share_init", {"share_code": share_code, "receive_code": receive_code}))

    def readdir(self, cid: int | str = 0) -> list[dict[str, object]]:
        self.calls.append(("share_readdir", cid))
        return [
            {"id": "20", "name": "Shared.mkv", "is_dir": False, "parent_id": cid, "size": "456"},
        ]

    def receive(self, ids: list[int | str], to_pid: int = 0) -> dict[str, object]:
        self.calls.append(("share_receive", {"ids": ids, "to_pid": to_pid}))
        return {"state": True, "ids": ids, "to_pid": to_pid}


class Storage115ServiceCompatibilityTest(unittest.TestCase):
    def make_service(self) -> tuple[Storage115Service, FakeP115FileSystem, list[tuple[str, object]]]:
        fs = FakeP115FileSystem()
        share_calls: list[tuple[str, object]] = []

        def share_factory(share_code: str, receive_code: str | None) -> FakeP115ShareFileSystem:
            return FakeP115ShareFileSystem(share_calls, share_code, receive_code)

        service = Storage115Service(client=FakeP115Client(), fs=fs, share_fs_factory=share_factory)
        return service, fs, share_calls

    def test_list_folder_uses_filesystem_readdir(self) -> None:
        service, fs, _ = self.make_service()

        items = service.list_folder(900)

        self.assertEqual(fs.calls, [("readdir", 900)])
        self.assertEqual(
            [(item.id, item.name, item.is_dir, item.size) for item in items],
            [("10", "Movie.mkv", False, 123), ("11", "Folder", True, None)],
        )

    def test_list_share_uses_share_filesystem_readdir(self) -> None:
        service, _, share_calls = self.make_service()

        items = service.list_share("swfu86g3wov", "fe00")

        self.assertEqual(
            share_calls,
            [
                ("share_init", {"share_code": "swfu86g3wov", "receive_code": "fe00"}),
                ("share_readdir", 0),
            ],
        )
        self.assertEqual([(item.id, item.name, item.is_dir, item.size) for item in items], [("20", "Shared.mkv", False, 456)])

    def test_save_share_uses_share_filesystem_receive(self) -> None:
        service, _, share_calls = self.make_service()

        result = service.save_share("swfu86g3wov", "fe00", target_cid=700, ids=[20, "21"])

        self.assertEqual(result["state"], True)
        self.assertEqual(
            share_calls,
            [
                ("share_init", {"share_code": "swfu86g3wov", "receive_code": "fe00"}),
                ("share_receive", {"ids": [20, "21"], "to_pid": 700}),
            ],
        )

    def test_rename_move_and_mkdir_use_filesystem_methods(self) -> None:
        service, fs, _ = self.make_service()

        service.rename_file(10, "New.mkv")
        service.move_file(10, 800)
        created = service.ensure_folder(900, "Created")

        self.assertEqual(
            fs.calls,
            [
                ("rename", {"id": 10, "name": "New.mkv"}),
                ("move", {"id": 10, "target_cid": 800}),
                ("readdir", 900),
                ("mkdir", {"parent_cid": 900, "name": "Created"}),
            ],
        )
        self.assertEqual((created.id, created.name, created.is_dir), ("31", "Created", True))

    def test_normalize_current_115_fid_cid_shapes(self) -> None:
        file_item = Storage115Service._normalize_item({"fid": "100", "n": "File.mkv", "s": "1024"})
        folder_item = Storage115Service._normalize_item({"cid": "200", "n": "Folder", "fc": 0})

        self.assertEqual((file_item.id, file_item.name, file_item.is_dir, file_item.size), ("100", "File.mkv", False, 1024))
        self.assertEqual((folder_item.id, folder_item.name, folder_item.is_dir, folder_item.size), ("200", "Folder", True, None))


if __name__ == "__main__":
    unittest.main()
