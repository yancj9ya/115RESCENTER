from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from re import Match
import re
from urllib.parse import parse_qs, urlsplit


_SHARE_URL_RE = re.compile(r"https://(?:115|115cdn)\.com/s/[^\s<>'\"]+")


@dataclass(frozen=True)
class ParsedShareLink:
    share_code: str
    receive_code: str
    share_url: str


@dataclass(frozen=True)
class CollectedShare:
    share_code: str
    receive_code: str
    share_url: str
    source_type: str
    source_id: str
    message_id: str
    message_text: str
    published_at: datetime | None = None


def parse_115_shares(text: str) -> list[ParsedShareLink]:
    shares: list[ParsedShareLink] = []
    seen: set[str] = set()

    for match in _SHARE_URL_RE.finditer(text):
        share = _parse_share_match(match)
        if share.share_url in seen:
            continue
        seen.add(share.share_url)
        shares.append(share)

    return shares


def _parse_share_match(match: Match[str]) -> ParsedShareLink:
    share_url = match.group(0).rstrip(".,;，。；、)")
    parsed = urlsplit(share_url)
    share_code = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    receive_code = ""

    query_password = parse_qs(parsed.query).get("password", [])
    if query_password:
        receive_code = query_password[0]
    elif parsed.fragment:
        receive_code = parsed.fragment

    return ParsedShareLink(
        share_code=share_code,
        receive_code=receive_code,
        share_url=share_url,
    )
