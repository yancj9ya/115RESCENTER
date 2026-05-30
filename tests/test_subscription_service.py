from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.subscriptions.repository import SubscriptionRepository
from src.subscriptions.service import SubscriptionRuleNotFoundError, SubscriptionService


class SubscriptionServiceTest(unittest.TestCase):
    def _service(self, tmp_dir: str) -> SubscriptionService:
        repository = SubscriptionRepository(Path(tmp_dir) / "subscriptions.db")
        repository.init_schema()
        return SubscriptionService(repository)

    def test_create_rejects_invalid_regex_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            with self.assertRaises(ValueError):
                service.create_rule(name="Bad", pattern="[", enabled=True)

            self.assertEqual(service.list_rules(), [])

    def test_update_rejects_invalid_regex_and_preserves_stored_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            created = service.create_rule(name="Movies", pattern="1080p", enabled=True)

            with self.assertRaises(ValueError):
                service.update_rule(created.id, pattern="[")

            stored = service.get_rule(created.id)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.pattern, "1080p")

    def test_duplicate_names_are_allowed_and_distinguished_by_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            first = service.create_rule(name="Movies", pattern="1080p", enabled=True)
            second = service.create_rule(name="Movies", pattern="2160p", enabled=True)

            self.assertEqual(first.name, second.name)
            self.assertNotEqual(first.id, second.id)
            self.assertEqual([rule.id for rule in service.list_rules()], [first.id, second.id])

    def test_get_update_and_delete_not_found_behavior_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            self.assertIsNone(service.get_rule(404))
            self.assertIsNone(service.update_rule(404, name="Missing"))
            self.assertFalse(service.delete_rule(404))
            with self.assertRaises(SubscriptionRuleNotFoundError):
                service.enable_rule(404)
            with self.assertRaises(SubscriptionRuleNotFoundError):
                service.disable_rule(404)

    def test_enable_and_disable_toggle_existing_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            created = service.create_rule(name="Movies", pattern="1080p", enabled=True)

            disabled = service.disable_rule(created.id)
            enabled = service.enable_rule(created.id)

            self.assertFalse(disabled.enabled)
            self.assertTrue(enabled.enabled)

    def test_match_sample_text_returns_true_for_case_insensitive_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            rule = service.create_rule(name="Movies", pattern="1080p", enabled=True)

            result = service.test_match(rule.id, "MOVIE 1080P")

            self.assertTrue(result.matched)
            self.assertEqual(result.rule_id, rule.id)
            self.assertEqual(result.rule_name, "Movies")
            self.assertEqual(result.matched_keywords, ["1080p"])

    def test_match_sample_text_returns_false_for_nonmatching_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)
            rule = service.create_rule(name="Movies", pattern="1080p", enabled=True)

            result = service.test_match(rule.id, "MOVIE 720P")

            self.assertFalse(result.matched)
            self.assertEqual(result.rule_id, rule.id)
            self.assertEqual(result.rule_name, "Movies")
            self.assertEqual(result.matched_keywords, [])

    def test_ad_hoc_match_does_not_require_persistence_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = self._service(tmp_dir)

            matched = service.test_pattern(pattern="1080p", text="MOVIE 1080P")
            not_matched = service.test_pattern(pattern="1080p", text="MOVIE 720P")

            self.assertTrue(matched.matched)
            self.assertFalse(not_matched.matched)
            self.assertEqual(service.list_rules(), [])


if __name__ == "__main__":
    unittest.main()
