from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.collectors import CollectedShare
from src.queue import CollectQueueRecord, ShareLink, TransferRuleContext, TransferSourceMessage
from src.queue.repository import QueueRepository
from src.subscriptions.matcher import SubscriptionMatcher, SubscriptionRule
from src.subscriptions.repository import SubscriptionRepository
from src.subscriptions.transfer_plan import build_transfer_plans

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubscriptionProcessSummary:
    scanned: int = 0
    matched: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class SubscriptionProcessor:
    def __init__(
        self,
        queue_repository: QueueRepository,
        subscription_repository: SubscriptionRepository,
        staging_cid: int | None,
    ) -> None:
        self._queue_repository = queue_repository
        self._subscription_repository = subscription_repository
        self._staging_cid = staging_cid

    def process(self, limit: int = 100) -> SubscriptionProcessSummary:
        if self._staging_cid is None:
            logger.error("订阅处理失败: 未配置中转目录 (P115_TRANSFER_CID)")
            return SubscriptionProcessSummary(errors=["staging cid is required; set P115_TRANSFER_CID"])

        logger.info(f"开始订阅处理: limit={limit}, staging_cid={self._staging_cid}")
        rules = self._load_enabled_rules()
        logger.info(f"加载了 {len(rules)} 条启用的订阅规则")

        try:
            matcher = SubscriptionMatcher(rules)
        except Exception as exc:
            logger.error(f"订阅匹配器初始化失败: {exc}")
            return SubscriptionProcessSummary(errors=[str(exc)])

        remaining = max(limit, 0)
        scanned = 0
        matched = 0
        created = 0
        skipped = 0
        errors: list[str] = []
        existing_transfer_keys = self._existing_transfer_keys()

        while scanned < remaining:
            record = self._queue_repository.claim_next_collect()
            if record is None:
                break

            scanned += 1
            logger.debug(f"处理收集记录 #{record.id}: {record.message_id} ({len(record.shares_json)} 个分享)")

            try:
                matches = []
                for share in record.shares_json:
                    share_matches = matcher.match_share(self._collected_share_from_record(record, share))
                    matches.extend(share_matches)
                    if share_matches:
                        logger.info(f"分享链接匹配成功: {share.share_url}, 匹配 {len(share_matches)} 条规则")

                plans = build_transfer_plans(matches, self._staging_cid)
                if not plans:
                    self._queue_repository.mark_collect_skipped(record.id)
                    skipped += 1
                    logger.debug(f"跳过收集记录 #{record.id}: 无匹配规则")
                    continue

                source_message = TransferSourceMessage(
                    collect_id=record.id,
                    source_type=record.source_type,
                    source_id=record.source_id,
                    message_id=record.message_id,
                    message_url=record.message_url or "",
                    published_at=record.published_at,
                )

                plan_count = 0
                for plan in plans:
                    key = (plan.share_url, plan.staging_cid)
                    self._queue_repository.enqueue_transfer_task(
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
                    if key not in existing_transfer_keys:
                        existing_transfer_keys.add(key)
                        created += 1
                        plan_count += 1

                self._queue_repository.mark_collect_success(record.id)
                matched += 1
                logger.info(f"收集记录处理成功 #{record.id}: 创建 {plan_count} 个转存任务")
            except Exception as exc:
                error = str(exc)
                self._queue_repository.mark_collect_failed(record.id, error)
                errors.append(error)
                logger.error(f"收集记录处理失败 #{record.id}: {error}", exc_info=True)

        logger.info(f"订阅处理完成: 扫描={scanned}, 匹配={matched}, 创建={created}, 跳过={skipped}, 失败={len(errors)}")
        return SubscriptionProcessSummary(
            scanned=scanned,
            matched=matched,
            created=created,
            skipped=skipped,
            errors=errors,
        )

    def _load_enabled_rules(self) -> list[SubscriptionRule]:
        return [
            SubscriptionRule(
                id=str(record.id),
                name=record.name,
                pattern=record.pattern,
                enabled=record.enabled,
                tmdb_id=record.tmdb_id,
                aliases=record.aliases,
            )
            for record in self._subscription_repository.list_rules()
            if record.enabled
        ]

    def _existing_transfer_keys(self) -> set[tuple[str, int]]:
        return {(record.share_url, record.staging_cid) for record in self._queue_repository.list_transfer_queue()}

    def _collected_share_from_record(self, record: CollectQueueRecord, share: ShareLink) -> CollectedShare:
        return CollectedShare(
            share_code=share.share_code,
            receive_code=share.receive_code,
            share_url=share.share_url,
            source_type=record.source_type,
            source_id=record.source_id,
            message_id=record.message_id,
            message_text=record.message_text,
            published_at=record.published_at,
        )
