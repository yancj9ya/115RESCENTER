from __future__ import annotations

from dataclasses import dataclass

from .matcher import SubscriptionMatch


@dataclass(frozen=True)
class TransferPlan:
    rule_id: str
    rule_name: str
    share_code: str
    receive_code: str
    share_url: str
    staging_cid: int
    source_type: str
    source_id: str
    message_id: str
    matched_keywords: list[str]


def build_transfer_plans(matches: list[SubscriptionMatch], staging_cid: int) -> list[TransferPlan]:
    plans: list[TransferPlan] = []
    seen: set[tuple[str, str]] = set()

    for match in matches:
        dedupe_key = (match.rule_id, match.share.share_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        plans.append(
            TransferPlan(
                rule_id=match.rule_id,
                rule_name=match.rule_name,
                share_code=match.share.share_code,
                receive_code=match.share.receive_code,
                share_url=match.share.share_url,
                staging_cid=staging_cid,
                source_type=match.share.source_type,
                source_id=match.share.source_id,
                message_id=match.share.message_id,
                matched_keywords=match.matched_keywords,
            )
        )

    return plans
