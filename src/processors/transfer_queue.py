from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from src.queue import FAILED, PENDING, SUCCESS
from src.queue.repository import QueueRepository

logger = logging.getLogger(__name__)


class TransferStorage(Protocol):
    def save_share(self, share_code: str, receive_code: str = "", target_cid: int = 0, ids: object = None) -> dict:
        ...


@dataclass(frozen=True)
class TransferQueueProcessResult:
    claimed: bool
    transfer_id: int | None = None
    status: str | None = None
    error: str | None = None


class TransferQueueProcessor:
    def __init__(self, repository: QueueRepository, storage: TransferStorage, max_attempts: int = 3) -> None:
        self._repository = repository
        self._storage = storage
        self._max_attempts = max_attempts

    def process_next_transfer(self) -> TransferQueueProcessResult:
        record = self._repository.claim_next_transfer()
        if record is None:
            return TransferQueueProcessResult(claimed=False)

        logger.info(f"开始转存任务 #{record.id}: share_code={record.share_code}, staging_cid={record.staging_cid}")
        try:
            result = self._storage.save_share(record.share_code, record.receive_code, target_cid=record.staging_cid)
            self._repository.mark_transfer_success(record.id)
            logger.info(f"转存任务成功 #{record.id}: share_code={record.share_code}")
            return TransferQueueProcessResult(claimed=True, transfer_id=record.id, status=SUCCESS)
        except Exception as exc:
            error = str(exc)
            self._repository.mark_transfer_failed_or_retry(record.id, error, max_attempts=self._max_attempts)
            status = FAILED if record.attempt_count + 1 >= self._max_attempts else PENDING
            if status == FAILED:
                logger.error(f"转存任务失败 #{record.id} (已达最大重试次数 {self._max_attempts}): {error}", exc_info=True)
            else:
                logger.warning(f"转存任务失败 #{record.id} (尝试 {record.attempt_count + 1}/{self._max_attempts}): {error}")
            return TransferQueueProcessResult(claimed=True, transfer_id=record.id, status=status, error=error)
