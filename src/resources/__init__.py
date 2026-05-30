"""State-only resource configuration models and repositories."""

from .models import TelegramWebChannelRecord
from .repository import TelegramWebChannelRepository
from .service import TelegramWebChannelService

__all__ = [
    "TelegramWebChannelRecord",
    "TelegramWebChannelRepository",
    "TelegramWebChannelService",
]
