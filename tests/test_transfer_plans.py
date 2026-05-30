from __future__ import annotations

import unittest

from src.collectors import CollectedShare
from src.subscriptions import SubscriptionMatch
from src.subscriptions.transfer_plan import TransferPlan, build_transfer_plans


class TransferPlanTest(unittest.TestCase):
    def test_builds_transfer_plan_from_subscription_match(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="xy9z",
            share_url="https://115.com/s/abc123?password=xy9z",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_text="庆余年 https://115.com/s/abc123?password=xy9z",
        )
        match = SubscriptionMatch(
            rule_id="rule-qyn",
            rule_name="庆余年",
            share=share,
            matched_keywords=[r"庆余年|Joy of Life"],
        )

        plans = build_transfer_plans([match], staging_cid=12345)

        self.assertEqual(
            plans,
            [
                TransferPlan(
                    rule_id="rule-qyn",
                    rule_name="庆余年",
                    share_code="abc123",
                    receive_code="xy9z",
                    share_url="https://115.com/s/abc123?password=xy9z",
                    staging_cid=12345,
                    source_type="telegram_web",
                    source_id="movie_channel",
                    message_id="101",
                    matched_keywords=[r"庆余年|Joy of Life"],
                )
            ],
        )

    def test_deduplicates_same_rule_and_share_url_in_first_seen_order(self) -> None:
        share = CollectedShare(
            share_code="dup123",
            receive_code="",
            share_url="https://115.com/s/dup123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_text="庆余年 https://115.com/s/dup123",
        )
        duplicate_share = CollectedShare(
            share_code="dup123",
            receive_code="",
            share_url="https://115.com/s/dup123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="102",
            message_text="再次发布 庆余年 https://115.com/s/dup123",
        )
        matches = [
            SubscriptionMatch("rule-qyn", "庆余年", share, [r"庆余年|Joy of Life"]),
            SubscriptionMatch("rule-qyn", "庆余年", duplicate_share, [r"庆余年|Joy of Life"]),
        ]

        plans = build_transfer_plans(matches, staging_cid=12345)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].message_id, "101")
        self.assertEqual(plans[0].share_url, "https://115.com/s/dup123")
        self.assertEqual(plans[0].staging_cid, 12345)

    def test_keeps_same_share_for_different_rules(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="",
            share_url="https://115.com/s/abc123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_text="庆余年 4K https://115.com/s/abc123",
        )
        matches = [
            SubscriptionMatch("rule-qyn", "庆余年", share, [r"庆余年|Joy of Life"]),
            SubscriptionMatch("rule-4k", "4K", share, [r"4[Kk]|2160p"]),
        ]

        plans = build_transfer_plans(matches, staging_cid=9001)

        self.assertEqual([plan.rule_id for plan in plans], ["rule-qyn", "rule-4k"])
        self.assertEqual([plan.staging_cid for plan in plans], [9001, 9001])


if __name__ == "__main__":
    unittest.main()
