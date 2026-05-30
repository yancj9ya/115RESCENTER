from __future__ import annotations

import pathlib
import unittest
from dataclasses import FrozenInstanceError

from src.notifications import (
    ERROR,
    INFO,
    ORGANIZE_FAILED,
    ORGANIZE_SUCCESS,
    TMDB_UNRESOLVED,
    TRANSFER_FAILED,
    TRANSFER_SUCCESS,
    WARNING,
    InMemoryNotifier,
    NotificationEvent,
    Notifier,
)


class FakeWebhookResponse:
    def __init__(self, status_code: int = 200, text: str = "OK") -> None:
        self.status_code = status_code
        self.text = text


class FakeWebhookClient:
    def __init__(self, response: FakeWebhookResponse | None = None) -> None:
        self.response = response or FakeWebhookResponse()
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeWebhookResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


class NotificationsTest(unittest.TestCase):
    def test_notification_event_fields_default_context_and_frozen(self) -> None:
        event = NotificationEvent(
            event_type=TRANSFER_SUCCESS,
            severity=INFO,
            title="Transfer complete",
            message="Saved share files.",
        )

        self.assertEqual(event.event_type, "transfer_success")
        self.assertEqual(event.severity, "info")
        self.assertEqual(event.title, "Transfer complete")
        self.assertEqual(event.message, "Saved share files.")
        self.assertEqual(event.context, {})

        with self.assertRaises(FrozenInstanceError):
            event.title = "Changed"  # type: ignore[misc]

    def test_default_context_is_not_shared_between_events(self) -> None:
        first = NotificationEvent(TRANSFER_SUCCESS, INFO, "First", "Message")
        second = NotificationEvent(TRANSFER_SUCCESS, INFO, "Second", "Message")

        first.context["share_code"] = "abc"

        self.assertEqual(first.context, {"share_code": "abc"})
        self.assertEqual(second.context, {})

    def test_constants_are_exported(self) -> None:
        self.assertEqual(INFO, "info")
        self.assertEqual(WARNING, "warning")
        self.assertEqual(ERROR, "error")
        self.assertEqual(TRANSFER_SUCCESS, "transfer_success")
        self.assertEqual(TRANSFER_FAILED, "transfer_failed")
        self.assertEqual(ORGANIZE_SUCCESS, "organize_success")
        self.assertEqual(ORGANIZE_FAILED, "organize_failed")
        self.assertEqual(TMDB_UNRESOLVED, "tmdb_unresolved")

    def test_in_memory_notifier_stores_events_in_order(self) -> None:
        notifier = InMemoryNotifier()
        first = NotificationEvent(TRANSFER_SUCCESS, INFO, "First", "Done")
        second = NotificationEvent(TRANSFER_FAILED, ERROR, "Second", "Failed")

        notifier.notify(first)
        notifier.notify(second)

        self.assertEqual(notifier.events, [first, second])

    def test_in_memory_events_returns_copy(self) -> None:
        notifier = InMemoryNotifier()
        event = NotificationEvent(ORGANIZE_SUCCESS, INFO, "Organized", "Done")
        notifier.notify(event)

        events = notifier.events
        events.append(NotificationEvent(ORGANIZE_FAILED, WARNING, "Other", "Skipped"))

        self.assertEqual(notifier.events, [event])

    def test_in_memory_notifier_satisfies_protocol(self) -> None:
        notifier: Notifier = InMemoryNotifier()
        event = NotificationEvent(TMDB_UNRESOLVED, WARNING, "Missing TMDB", "No match")

        notifier.notify(event)

        self.assertEqual(notifier.events, [event])  # type: ignore[attr-defined]

    def test_webhook_notifier_disabled_by_default_makes_no_client_calls(self) -> None:
        from src.notifications.webhook import WebhookConfig, WebhookNotifier

        client = FakeWebhookClient()
        notifier = WebhookNotifier(
            WebhookConfig(url="https://webhook.invalid/notify"),
            client=client,
        )
        event = NotificationEvent(TRANSFER_SUCCESS, INFO, "Done", "Saved")

        notifier.notify(event)

        self.assertEqual(client.calls, [])

    def test_webhook_notifier_posts_json_payload_with_timeout_and_auth_header(self) -> None:
        from src.notifications.webhook import WebhookConfig, WebhookNotifier

        client = FakeWebhookClient()
        notifier = WebhookNotifier(
            WebhookConfig(
                url="https://webhook.invalid/notify",
                enabled=True,
                token="secret-token",
                timeout=3.5,
            ),
            client=client,
        )
        event = NotificationEvent(
            event_type=TRANSFER_FAILED,
            severity=ERROR,
            title="Transfer failed",
            message="Could not save share.",
            context={"share_code": "abc123"},
        )

        notifier.notify(event)

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["url"], "https://webhook.invalid/notify")
        self.assertEqual(call["timeout"], 3.5)
        self.assertEqual(call["headers"], {"Authorization": "Bearer secret-token"})
        self.assertEqual(
            call["json"],
            {
                "event_type": "transfer_failed",
                "severity": "error",
                "title": "Transfer failed",
                "message": "Could not save share.",
                "context": {"share_code": "abc123"},
            },
        )

    def test_webhook_notifier_non_2xx_raises_without_leaking_token(self) -> None:
        from src.notifications.webhook import (
            WebhookConfig,
            WebhookNotificationError,
            WebhookNotifier,
        )

        client = FakeWebhookClient(FakeWebhookResponse(status_code=503, text="bad secret-token"))
        notifier = WebhookNotifier(
            WebhookConfig(
                url="https://webhook.invalid/notify",
                enabled=True,
                token="secret-token",
            ),
            client=client,
        )
        event = NotificationEvent(ORGANIZE_FAILED, ERROR, "Organize failed", "Webhook check")

        with self.assertRaises(WebhookNotificationError) as raised:
            notifier.notify(event)

        self.assertNotIn("secret-token", str(raised.exception))
        self.assertIn("503", str(raised.exception))

    def test_webhook_contract_exports_are_available_from_package(self) -> None:
        import src.notifications as notifications

        self.assertTrue(hasattr(notifications, "WebhookConfig"))
        self.assertTrue(hasattr(notifications, "WebhookNotifier"))
        self.assertTrue(hasattr(notifications, "WebhookNotificationError"))

    def test_notification_core_sources_have_no_forbidden_network_dependencies(self) -> None:
        forbidden = [
            "httpx",
            "requests",
            "telegram",
            "smtplib",
            "webhook",
            "P115_COOKIES",
            "TMDB_BEARER_TOKEN",
        ]
        source_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "notifications"
        network_modules = {"webhook.py", "telegram_bot.py", "bark.py"}
        core_paths = [path for path in source_dir.glob("*.py") if path.name not in network_modules]
        combined_source = "\n".join(path.read_text(encoding="utf-8") for path in core_paths)

        for term in forbidden:
            with self.subTest(term=term):
                self.assertNotIn(term, combined_source)

    def test_webhook_source_allows_httpx_but_no_other_forbidden_dependencies(self) -> None:
        forbidden = [
            "P115_COOKIES",
            "TMDB_BEARER_TOKEN",
            "telegram",
            "smtplib",
        ]
        webhook_path = pathlib.Path(__file__).resolve().parents[1] / "src" / "notifications" / "webhook.py"
        webhook_source = webhook_path.read_text(encoding="utf-8")

        for term in forbidden:
            with self.subTest(term=term):
                self.assertNotIn(term, webhook_source)


if __name__ == "__main__":
    unittest.main()
