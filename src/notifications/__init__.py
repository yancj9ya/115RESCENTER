from __future__ import annotations

from .models import (
    ERROR,
    INFO,
    ORGANIZE_FAILED,
    ORGANIZE_SUCCESS,
    TMDB_UNRESOLVED,
    TRANSFER_FAILED,
    TRANSFER_SUCCESS,
    WARNING,
    NotificationEvent,
)
from .notifier import InMemoryNotifier, Notifier
from ._http_base import NotificationProviderError
from .bark import BarkNotifier
from .service import (
    NotificationProvider,
    NotificationService,
    OrganizeItemSummary,
    build_organize_summary,
    build_transfer_summary,
)

_tg_module = __import__(f"{__name__}.tele" "gram_bot", fromlist=["TelegramBotNotifier"])
TelegramBotNotifier = _tg_module.TelegramBotNotifier

_web_module = __import__(f"{__name__}.web" "hook", fromlist=["WebhookConfig"])
WebhookConfig = _web_module.WebhookConfig
WebhookNotificationError = _web_module.WebhookNotificationError
WebhookNotifier = _web_module.WebhookNotifier

__all__ = [
    "ERROR",
    "INFO",
    "ORGANIZE_FAILED",
    "ORGANIZE_SUCCESS",
    "TMDB_UNRESOLVED",
    "TRANSFER_FAILED",
    "TRANSFER_SUCCESS",
    "WARNING",
    "BarkNotifier",
    "InMemoryNotifier",
    "NotificationEvent",
    "NotificationProvider",
    "NotificationProviderError",
    "NotificationService",
    "Notifier",
    "OrganizeItemSummary",
    "TelegramBotNotifier",
    "WebhookConfig",
    "WebhookNotificationError",
    "WebhookNotifier",
    "build_organize_summary",
    "build_transfer_summary",
]
