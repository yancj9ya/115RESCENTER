from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from src.collectors import CollectedShare
from src.notifications import Notifier
from src.organizing.models import OrganizeRule
from src.processors.collect_queue import CollectQueueProcessor
from src.processors.fakes import (
    notify_organize_failure,
    notify_organize_success,
    notify_transfer_failure,
    notify_transfer_success,
)
from src.processors.organize_folder import OrganizeFolderProcessor
from src.processors.transfer_queue import TransferQueueProcessor
from src.queue import ShareLink
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher


@dataclass(frozen=True)
class DryRunBackendSummary:
    collect_enqueued: int
    collect_processed: int
    transfer_processed: int
    organize_scanned: int
    organize_planned: int
    organize_moved: int
    notification_count: int
    errors: tuple[str, ...] = field(default_factory=tuple)


class DryRunBackendService:
    def __init__(
        self,
        repository: QueueRepository,
        matcher: SubscriptionMatcher,
        transfer_storage: Any,
        organize_storage: Any,
        metadata_resolver: Any,
        organize_rule: OrganizeRule,
        notifier: Notifier,
        max_attempts: int = 3,
        staging_cid: int = 0,
    ) -> None:
        self._repository = repository
        self._matcher = matcher
        self._transfer_storage = transfer_storage
        self._organize_storage = organize_storage
        self._metadata_resolver = metadata_resolver
        self._organize_rule = organize_rule
        self._notifier = notifier
        self._max_attempts = max_attempts
        self._staging_cid = staging_cid

    def run_messages(self, messages: list[CollectedShare | Mapping[str, Any]]) -> DryRunBackendSummary:
        shares = [self._coerce_collected_share(message) for message in messages]
        return self.run_collected_shares(shares)

    def run_collected_shares(self, shares: list[CollectedShare]) -> DryRunBackendSummary:
        errors: list[str] = []
        notification_count = 0
        collect_enqueued = 0

        for share in shares:
            self._repository.enqueue_collected_message(
                source_type=share.source_type,
                source_id=share.source_id,
                message_id=share.message_id,
                message_url=self._message_url_for(share),
                message_text=share.message_text,
                published_at=self._serialize_published_at(share.published_at),
                shares=[
                    ShareLink(
                        share_code=share.share_code,
                        receive_code=share.receive_code,
                        share_url=share.share_url,
                    )
                ],
            )
            collect_enqueued += 1

        collect_processor = CollectQueueProcessor(self._repository, self._matcher, staging_cid=self._staging_cid)
        collect_processed = 0
        while True:
            result = collect_processor.process_next_collect()
            if not result.claimed:
                break
            collect_processed += 1
            if result.error:
                errors.append(result.error)

        transfer_processor = TransferQueueProcessor(
            self._repository,
            self._transfer_storage,
            max_attempts=self._max_attempts,
        )
        transfer_processed = 0
        while True:
            result = transfer_processor.process_next_transfer()
            if not result.claimed:
                break
            transfer_processed += 1
            transfer_record = self._find_transfer_record(result.transfer_id)
            if transfer_record is not None:
                if result.error:
                    errors.append(result.error)
                    notification_count += self._notify_transfer_failure(transfer_record.share_code, transfer_record.staging_cid, result.error)
                else:
                    notification_count += self._notify_transfer_success(transfer_record.share_code, transfer_record.staging_cid)

        organize_result = OrganizeFolderProcessor(
            self._organize_storage,
            self._organize_rule,
            self._metadata_resolver,
        ).process_folder(self._staging_cid)

        if organize_result.errors:
            for item_error in organize_result.errors:
                errors.append(item_error.error)
                notification_count += self._notify_organize_failure(item_error.file_id, item_error.error)
        else:
            notification_count += self._notify_organize_success(self._staging_cid)

        return DryRunBackendSummary(
            collect_enqueued=collect_enqueued,
            collect_processed=collect_processed,
            transfer_processed=transfer_processed,
            organize_scanned=organize_result.scanned_count,
            organize_planned=organize_result.planned_count,
            organize_moved=organize_result.moved_count,
            notification_count=notification_count,
            errors=tuple(errors),
        )

    def _coerce_collected_share(self, message: CollectedShare | Mapping[str, Any]) -> CollectedShare:
        if isinstance(message, CollectedShare):
            return message
        return CollectedShare(**dict(message))

    def _message_url_for(self, share: CollectedShare) -> str:
        source_type = share.source_type
        if source_type == "tg_web":
            return f"https://t.me/s/{share.source_id}/{share.message_id}"
        return share.share_url

    def _serialize_published_at(self, published_at: datetime | None) -> str | None:
        if published_at is None:
            return None
        return published_at.isoformat()

    def _find_transfer_record(self, transfer_id: int | None) -> Any | None:
        if transfer_id is None:
            return None
        for record in self._repository.list_transfer_queue():
            if record.id == transfer_id:
                return record
        return None

    def _notify_transfer_success(self, share_code: str, staging_cid: int) -> int:
        notify_transfer_success(self._notifier, share_code, staging_cid)
        return 1

    def _notify_transfer_failure(self, share_code: str, staging_cid: int, error: str) -> int:
        notify_transfer_failure(self._notifier, share_code, staging_cid, error)
        return 1

    def _notify_organize_success(self, file_id: int) -> int:
        notify_organize_success(self._notifier, file_id, "process_folder")
        return 1

    def _notify_organize_failure(self, file_id: int, error: str) -> int:
        notify_organize_failure(self._notifier, file_id, "process_folder", error)
        return 1


__all__ = ["DryRunBackendService", "DryRunBackendSummary"]
