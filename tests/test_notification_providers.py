from __future__ import annotations

import unittest

from src.notifications import (
    INFO,
    BarkNotifier,
    NotificationEvent,
    TelegramBotNotifier,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


class _RecordingClient:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return _FakeResponse(self.status_code)


def _event() -> NotificationEvent:
    return NotificationEvent(
        event_type="organize_success",
        severity=INFO,
        title="逐玉 入库",
        message="E1-E10",
    )


class TelegramBotNotifierTest(unittest.TestCase):
    def test_name_is_configurable(self) -> None:
        notifier = TelegramBotNotifier(name="tg1", bot_token="abc", chat_id="123")
        self.assertEqual(notifier.name, "tg1")

    def test_posts_to_telegram_send_message_endpoint(self) -> None:
        client = _RecordingClient()
        notifier = TelegramBotNotifier(name="tg1", bot_token="TOKEN", chat_id="999", client=client)

        notifier.notify(_event())

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["url"], "https://api.telegram.org/botTOKEN/sendMessage")
        payload = call["json"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["chat_id"], "999")
        self.assertIn("逐玉 入库", str(payload["text"]))
        self.assertIn("E1-E10", str(payload["text"]))

    def test_raises_on_non_2xx(self) -> None:
        client = _RecordingClient(status_code=500)
        notifier = TelegramBotNotifier(name="tg1", bot_token="TOKEN", chat_id="999", client=client)

        with self.assertRaises(Exception):
            notifier.notify(_event())


class BarkNotifierTest(unittest.TestCase):
    def test_name_is_configurable(self) -> None:
        notifier = BarkNotifier(name="bark1", device_key="KEY")
        self.assertEqual(notifier.name, "bark1")

    def test_posts_title_and_body_to_device_key(self) -> None:
        client = _RecordingClient()
        notifier = BarkNotifier(name="bark1", device_key="DEVICEKEY", client=client)

        notifier.notify(_event())

        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertTrue(str(call["url"]).startswith("https://api.day.app/DEVICEKEY"))
        payload = call["json"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["title"], "逐玉 入库")
        self.assertEqual(payload["body"], "E1-E10")

    def test_custom_server_url(self) -> None:
        client = _RecordingClient()
        notifier = BarkNotifier(
            name="bark1",
            device_key="DEVICEKEY",
            server_url="https://bark.example.com",
            client=client,
        )

        notifier.notify(_event())

        self.assertTrue(str(client.calls[0]["url"]).startswith("https://bark.example.com/DEVICEKEY"))

    def test_raises_on_non_2xx(self) -> None:
        client = _RecordingClient(status_code=404)
        notifier = BarkNotifier(name="bark1", device_key="KEY", client=client)

        with self.assertRaises(Exception):
            notifier.notify(_event())


if __name__ == "__main__":
    unittest.main()
