from __future__ import annotations

import unittest

from src.collectors import CollectedShare
from src.subscriptions import SubscriptionMatcher, SubscriptionRule
from src.subscriptions.matcher import validate_subscription_pattern, validate_subscription_signals


class SubscriptionMatcherTest(unittest.TestCase):
    def test_regex_pattern_matches_episode_text(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="xy9z",
            share_url="https://115.com/s/abc123?password=xy9z",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_text="Show S01E02 https://115.com/s/abc123?password=xy9z",
        )
        rule = SubscriptionRule(
            id="rule-episode",
            name="Episode",
            pattern=r"S\d{2}E\d{2}",
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rule_id, "rule-episode")
        self.assertEqual(matches[0].rule_name, "Episode")
        self.assertEqual(matches[0].share, share)
        self.assertEqual(matches[0].matched_keywords, [r"S\d{2}E\d{2}"])

    def test_regex_matching_is_case_insensitive_by_default(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="",
            share_url="https://115.com/s/abc123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="102",
            message_text="MOVIE 1080P https://115.com/s/abc123",
        )
        rule = SubscriptionRule(
            id="rule-1080p",
            name="1080p",
            pattern="1080p",
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual([match.matched_keywords for match in matches], [["1080p"]])

    def test_disabled_rule_returns_no_matches(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="",
            share_url="https://115.com/s/abc123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="103",
            message_text="MOVIE 1080P https://115.com/s/abc123",
        )
        rule = SubscriptionRule(
            id="rule-1080p",
            name="1080p",
            pattern="1080p",
            enabled=False,
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(matches, [])

    def test_validation_rejects_invalid_and_blank_patterns(self) -> None:
        with self.assertRaises(ValueError):
            validate_subscription_pattern("[")

        with self.assertRaises(ValueError):
            validate_subscription_pattern("   ")

    def test_validation_rejects_overly_long_patterns(self) -> None:
        with self.assertRaises(ValueError):
            validate_subscription_pattern("a" * 501)

    def test_unicode_message_text_does_not_crash(self) -> None:
        share = CollectedShare(
            share_code="cn123",
            receive_code="",
            share_url="https://115.com/s/cn123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="104",
            message_text="庆余年 第二季 1080P 更新 https://115.com/s/cn123",
        )
        rule = SubscriptionRule(
            id="rule-qyn",
            name="庆余年",
            pattern="庆余年",
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual([match.rule_id for match in matches], ["rule-qyn"])

    def test_matches_multiple_rules_in_configured_order(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="",
            share_url="https://115.com/s/abc123",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="105",
            message_text="Show S01E02 1080P https://115.com/s/abc123",
        )
        rules = [
            SubscriptionRule(
                id="rule-episode",
                name="Episode",
                pattern=r"S\d{2}E\d{2}",
            ),
            SubscriptionRule(
                id="rule-1080p",
                name="1080p",
                pattern="1080p",
            ),
        ]

        matches = SubscriptionMatcher(rules).match_share(share)

        self.assertEqual([match.rule_id for match in matches], ["rule-episode", "rule-1080p"])
        self.assertEqual([match.share for match in matches], [share, share])
    def test_logs_searchable_text_preview_for_debugging(self) -> None:
        share = CollectedShare(
            share_code="abc123",
            receive_code="xy9z",
            share_url="https://115.com/s/abc123?password=xy9z",
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="101",
            message_text="Movie night\nwith newline",
        )

        with self.assertLogs("src.subscriptions.matcher", level="DEBUG") as captured:
            SubscriptionMatcher([]).match_share(share)

        logs = "\n".join(captured.output)
        self.assertIn("待匹配内容: Movie night with newline https://115.com/s/abc123?password=xy9z", logs)


class SubscriptionMatcherTmdbAndAliasTest(unittest.TestCase):
    def _share(self, *, text: str, url: str = "https://115.com/s/abc123") -> CollectedShare:
        return CollectedShare(
            share_code="abc123",
            receive_code="",
            share_url=url,
            source_type="telegram_web",
            source_id="movie_channel",
            message_id="200",
            message_text=text,
        )

    def test_tmdb_id_matches_with_digit_boundary(self) -> None:
        share = self._share(text="三体 三体 tmdb-108545 1080p")
        rule = SubscriptionRule(
            id="rule-tmdb",
            name="Three-Body",
            tmdb_id=108545,
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_keywords, ["tmdb:108545"])

    def test_tmdb_id_does_not_match_when_embedded_in_longer_digit_run(self) -> None:
        share = self._share(text="bitrate 1085451 file 1080p")
        rule = SubscriptionRule(
            id="rule-tmdb",
            name="Three-Body",
            tmdb_id=108545,
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(matches, [])

    def test_aliases_match_case_insensitively_and_collect_all_hits(self) -> None:
        share = self._share(text="THREE-body 1080p update")
        rule = SubscriptionRule(
            id="rule-aliases",
            name="Three-Body",
            aliases=("三体", "Three-Body", "3 Body Problem"),
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_keywords, ["Three-Body"])

    def test_pattern_still_matches_when_tmdb_and_aliases_absent(self) -> None:
        share = self._share(text="Show S01E02 https://115.com/s/abc123")
        rule = SubscriptionRule(
            id="rule-pattern",
            name="Episode",
            pattern=r"S\d{2}E\d{2}",
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_keywords, [r"S\d{2}E\d{2}"])

    def test_requires_matching_year_when_enabled(self) -> None:
        share = self._share(text="新版电影 2024 2160p")
        rule = SubscriptionRule(
            id="rule-year",
            name="新版电影",
            aliases=("新版电影",),
            year=2023,
        )

        self.assertEqual(SubscriptionMatcher([rule]).match_share(share), [])

    def test_matches_when_required_year_is_present(self) -> None:
        share = self._share(text="新版电影（2024）2160p")
        rule = SubscriptionRule(
            id="rule-year",
            name="新版电影",
            aliases=("新版电影",),
            year=2024,
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual([match.rule_id for match in matches], ["rule-year"])

    def test_year_check_can_be_disabled(self) -> None:
        share = self._share(text="新版电影 2024 2160p")
        rule = SubscriptionRule(
            id="rule-year-optional",
            name="新版电影",
            aliases=("新版电影",),
            year=2023,
            require_year_match=False,
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual([match.rule_id for match in matches], ["rule-year-optional"])

    def test_multiple_signals_in_one_rule_report_all_hits_in_priority_order(self) -> None:
        share = self._share(text="三体 108545 1080p")
        rule = SubscriptionRule(
            id="rule-multi",
            name="Three-Body",
            pattern="1080p",
            tmdb_id=108545,
            aliases=("三体",),
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_keywords, ["tmdb:108545", "三体", "1080p"])

    def test_rule_with_only_aliases_or_only_tmdb_id_is_valid(self) -> None:
        share = self._share(text="只匹配 别名 测试")

        aliases_only = SubscriptionRule(id="r1", name="aliases-only", aliases=("别名",))
        tmdb_only = SubscriptionRule(id="r2", name="tmdb-only", tmdb_id=42)
        share_with_id = self._share(text="标题 42 not-a-tmdb")

        self.assertEqual(
            [m.rule_id for m in SubscriptionMatcher([aliases_only]).match_share(share)],
            ["r1"],
        )
        self.assertEqual(
            [m.rule_id for m in SubscriptionMatcher([tmdb_only]).match_share(share_with_id)],
            ["r2"],
        )

    def test_disabled_rule_with_tmdb_or_alias_yields_no_match(self) -> None:
        share = self._share(text="三体 108545")
        rule = SubscriptionRule(
            id="rule-multi",
            name="Three-Body",
            tmdb_id=108545,
            aliases=("三体",),
            enabled=False,
        )

        self.assertEqual(SubscriptionMatcher([rule]).match_share(share), [])

    def test_blank_aliases_and_zero_tmdb_id_are_ignored(self) -> None:
        share = self._share(text="random text")
        rule = SubscriptionRule(
            id="rule-noisy",
            name="noisy",
            tmdb_id=0,
            aliases=("", "   "),
            pattern="random",
        )

        matches = SubscriptionMatcher([rule]).match_share(share)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_keywords, ["random"])


class SubscriptionSignalsValidationTest(unittest.TestCase):
    def test_validates_when_at_least_one_signal_is_present(self) -> None:
        validate_subscription_signals(pattern="1080p", tmdb_id=None, aliases=None)
        validate_subscription_signals(pattern=None, tmdb_id=42, aliases=None)
        validate_subscription_signals(pattern=None, tmdb_id=None, aliases=["三体"])

    def test_rejects_when_no_signal_is_present(self) -> None:
        with self.assertRaises(ValueError):
            validate_subscription_signals(pattern="", tmdb_id=None, aliases=None)
        with self.assertRaises(ValueError):
            validate_subscription_signals(pattern="   ", tmdb_id=None, aliases=["   ", ""])

    def test_invalid_pattern_propagates(self) -> None:
        with self.assertRaises(ValueError):
            validate_subscription_signals(pattern="[", tmdb_id=42, aliases=None)


if __name__ == "__main__":
    unittest.main()
