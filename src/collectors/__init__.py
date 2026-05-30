"""Resource collection helpers."""

from .shares import CollectedShare, ParsedShareLink, parse_115_shares
from .telegram_web import TelegramWebCollector, TelegramWebMessage, parse_telegram_public_channel_html

__all__ = [
    "CollectedShare",
    "ParsedShareLink",
    "TelegramWebCollector",
    "TelegramWebMessage",
    "parse_115_shares",
    "parse_telegram_public_channel_html",
]
