from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from p115client import P115Client

logger = logging.getLogger(__name__)


class Storage115Error(RuntimeError):
    """Raised when a 115 storage operation fails or returns an invalid response."""


@dataclass(frozen=True)
class Storage115Config:
    """Runtime options for constructing a 115 client."""

    cookies: str
    ensure_cookies: bool = False
    cache_home: Path | None = None


@dataclass(frozen=True)
class Storage115Item:
    """Normalized file/folder item returned by 115 APIs."""

    id: int | str
    name: str
    is_dir: bool
    parent_id: int | str | None = None
    size: int | None = None
    raw: Any = None


class Storage115Service:
    """Stable business-facing wrapper around p115client.

    The rest of the project should depend on this service instead of p115client's
    raw response details, so later API quirks can be handled in one place.
    """

    def __init__(
        self,
        config: Storage115Config | None = None,
        client: "P115Client | None" = None,
        *,
        fs: Any | None = None,
        share_fs_factory: Any | None = None,
    ) -> None:
        if client is None:
            if config is None:
                raise Storage115Error("Storage115Service requires a config or client")
            self._prepare_cache_home(config.cache_home)
            from p115client import P115Client

            client = P115Client(cookies=config.cookies, ensure_cookies=config.ensure_cookies)

        if fs is None:
            from p115client.fs import P115FileSystem

            fs = P115FileSystem(client)

        self.client = client
        self.fs = fs
        self._share_fs_factory = share_fs_factory

    def list_share(self, share_code: str, receive_code: str = "", cid: int | str = "") -> list[Storage115Item]:
        share_fs = self._share_fs(share_code, receive_code)
        items = share_fs.readdir(int(cid) if str(cid).isdigit() else cid or 0)
        return [self._normalize_item(item) for item in items]

    def save_share(
        self,
        share_code: str,
        receive_code: str = "",
        target_cid: int = 0,
        ids: Iterable[int | str] | int | str | None = None,
    ) -> dict[str, Any]:
        logger.info(f"开始转存分享: share_code={share_code}, target_cid={target_cid}")

        receive_ids = ids if ids is not None else [item.id for item in self.list_share(share_code, receive_code)]
        if isinstance(receive_ids, (str, int)):
            receive_ids = [receive_ids]
        receive_ids = list(receive_ids)

        if not receive_ids:
            logger.error(f"转存失败: 没有可转存的文件 (share_code={share_code})")
            raise Storage115Error("No share file ids to receive")

        logger.info(f"转存文件数量: {len(receive_ids)}, IDs: {receive_ids}")
        result = self._share_fs(share_code, receive_code).receive(receive_ids, to_pid=target_cid)
        self._ensure_success(result, "save share")
        logger.info(f"转存成功: share_code={share_code}, 文件数: {len(receive_ids)}")
        return result

    def list_folder(self, cid: int | str = 0) -> list[Storage115Item]:
        items = self.fs.readdir(cid)
        return [self._normalize_item(item) for item in items]

    def rename_file(self, file_id: int | str, new_name: str) -> Any:
        if not new_name.strip():
            raise Storage115Error("New file name cannot be empty")
        return self.fs.rename(file_id, new_name)

    def move_file(self, file_id: int | str, target_cid: int | str) -> Any:
        return self.fs.move(file_id, target_cid)

    def delete_file(self, file_id: int | str) -> Any:
        return self.fs.delete(file_id)

    def ensure_folder(self, parent_cid: int | str, name: str) -> Storage115Item:
        if not name.strip():
            raise Storage115Error("Folder name cannot be empty")

        for item in self.list_folder(parent_cid):
            if item.is_dir and item.name == name:
                return item

        created = self.fs.mkdir(parent_cid, name)
        return self._normalize_item(created)

    def ensure_dir(self, parent_cid: int | str, name: str) -> int:
        cleaned = str(name).strip()
        if not cleaned:
            raise Storage115Error("Folder name cannot be empty")
        parent_int = int(parent_cid)
        cache = self._ensure_dir_cache_dict()
        key = (parent_int, cleaned)
        if key in cache:
            return cache[key]
        item = self.ensure_folder(parent_int, cleaned)
        try:
            cid_int = int(item.id)
        except (TypeError, ValueError) as exc:
            raise Storage115Error(f"ensure_dir got non-integer id: {item.id!r}") from exc
        cache[key] = cid_int
        return cid_int

    def reset_ensure_dir_cache(self) -> None:
        self._ensure_dir_cache_dict().clear()

    def _ensure_dir_cache_dict(self) -> dict[tuple[int, str], int]:
        cache = getattr(self, "_ensure_dir_cache", None)
        if cache is None:
            cache = {}
            self._ensure_dir_cache = cache
        return cache

    def _share_fs(self, share_code: str, receive_code: str = "") -> Any:
        if not share_code.strip():
            raise Storage115Error("share_code cannot be empty")
        if self._share_fs_factory is not None:
            return self._share_fs_factory(share_code.strip(), receive_code or None)
        from p115client.fs import P115ShareFileSystem

        return P115ShareFileSystem(self.client, share_code.strip(), receive_code or None)

    @staticmethod
    def _prepare_cache_home(cache_home: Path | None) -> None:
        if cache_home is None:
            return
        cache_home.mkdir(parents=True, exist_ok=True)
        os.environ["USERPROFILE"] = str(cache_home)

    @classmethod
    def _normalize_item(cls, item: Any) -> Storage115Item:
        raw = item
        item_id = cls._get_first(item, "id", "fid", "file_id", "cid")
        name = cls._get_first(item, "name", "n", "file_name")
        is_dir = cls._detect_is_dir(item)
        parent_id = cls._get_first(item, "parent_id", "pid", "cid", default=None)
        size = cls._get_first(item, "size", "s", default=None)

        if item_id is None or name is None:
            raise Storage115Error(f"Cannot normalize 115 item: {item!r}")

        return Storage115Item(
            id=item_id,
            name=str(name),
            is_dir=is_dir,
            parent_id=parent_id,
            size=int(size) if str(size).isdigit() else None,
            raw=raw,
        )

    @staticmethod
    def _get_first(item: Any, *keys: str, default: Any = None) -> Any:
        for key in keys:
            if isinstance(item, dict) and key in item:
                return item[key]
            if hasattr(item, key):
                return getattr(item, key)
        return default

    @classmethod
    def _detect_is_dir(cls, item: Any) -> bool:
        for key in ("is_dir", "is_directory", "isdir"):
            value = cls._get_first(item, key, default=None)
            if value is not None:
                return bool(value)
        if cls._get_first(item, "fid", "file_id", default=None) is None and cls._get_first(item, "cid", default=None) is not None:
            return True
        type_value = str(cls._get_first(item, "type", "file_category", default="")).lower()
        return type_value in {"folder", "dir", "directory", "0"}

    @staticmethod
    def _ensure_success(response: dict[str, Any], action: str) -> None:
        if not isinstance(response, dict):
            raise Storage115Error(f"Invalid response while trying to {action}: {response!r}")
        state = response.get("state", response.get("success", True))
        if state in {False, 0, "0", "false", "False"}:
            message = response.get("error") or response.get("msg") or response.get("message") or response
            raise Storage115Error(f"Failed to {action}: {message}")
