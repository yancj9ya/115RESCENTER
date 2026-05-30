from __future__ import annotations

from dataclasses import dataclass

from src.collectors import CollectedShare
from src.queue import SKIPPED, SUCCESS, TransferRuleContext, TransferSourceMessage
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher
from src.subscriptions.transfer_plan import build_transfer_plans


@dataclass(frozen=True)
class CollectQueueProcessResult:
    claimed: bool
    collect_id: int | None = None
    status: str | None = None
    transfer_count: int = 0
    error: str | None = None


class CollectQueueProcessor:
    def __init__(self, repository: QueueRepository, matcher: SubscriptionMatcher, staging_cid: int) -> None:
        self._repository = repository
        self._matcher = matcher
        self._staging_cid = staging_cid

    def process_next_collect(self) -> CollectQueueProcessResult:
        record = self._repository.claim_next_collect()
        if record is None:
            return CollectQueueProcessResult(claimed=False)

        try:
            matches = []
            for share in record.shares_json:
                collected_share = CollectedShare(
                    share_code=share.share_code,
                    receive_code=share.receive_code,
                    share_url=share.share_url,
                    source_type=record.source_type,
                    source_id=record.source_id,
                    message_id=record.message_id,
                    message_text=record.message_text,
                    published_at=None,
                )
                matches.extend(self._matcher.match_share(collected_share))

            plans = build_transfer_plans(matches, self._staging_cid)
            if not plans:
                self._repository.mark_collect_skipped(record.id)
                return CollectQueueProcessResult(claimed=True, collect_id=record.id, status=SKIPPED)

            source_message = TransferSourceMessage(
                collect_id=record.id,
                source_type=record.source_type,
                source_id=record.source_id,
                message_id=record.message_id,
                message_url=record.message_url or "",
                published_at=record.published_at,
            )
            for plan in plans:
                self._repository.enqueue_transfer_task(
                    share_code=plan.share_code,
                    receive_code=plan.receive_code,
                    share_url=plan.share_url,
                    staging_cid=plan.staging_cid,
                    matched_rule=TransferRuleContext(
                        rule_id=plan.rule_id,
                        rule_name=plan.rule_name,
                        matched_keywords=plan.matched_keywords,
                    ),
                    source_message=source_message,
                )

            self._repository.mark_collect_success(record.id)
            return CollectQueueProcessResult(
                claimed=True,
                collect_id=record.id,
                status=SUCCESS,
                transfer_count=len(plans),
            )
        except Exception as exc:
            error = str(exc)
            self._repository.mark_collect_failed(record.id, error)
            return CollectQueueProcessResult(claimed=True, collect_id=record.id, status="FAILED", error=error)
