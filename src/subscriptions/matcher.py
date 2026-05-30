from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from re import Pattern

from src.collectors import CollectedShare

logger = logging.getLogger(__name__)


MAX_PATTERN_LENGTH = 500


@dataclass(frozen=True)
class SubscriptionRule:
    id: str
    name: str
    pattern: str = ""
    enabled: bool = True
    tmdb_id: int | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SubscriptionMatch:
    rule_id: str
    rule_name: str
    share: CollectedShare
    matched_keywords: list[str]


class SubscriptionMatcher:
    def __init__(self, rules: list[SubscriptionRule]) -> None:
        self._prepared = [(rule, _prepare_rule(rule)) for rule in rules]

    def match_share(self, share: CollectedShare) -> list[SubscriptionMatch]:
        matches: list[SubscriptionMatch] = []
        searchable_text = f"{share.message_text}\n{share.share_url}"
        searchable_lower = searchable_text.lower()

        logger.debug(f"匹配分享链接: {share.share_url}")

        for rule, prepared in self._prepared:
            if not rule.enabled:
                continue

            hits = _collect_hits(prepared, searchable_text, searchable_lower)
            if not hits:
                continue

            logger.info(f"匹配成功: 规则 '{rule.name}' (ID: {rule.id}), 关键词: {hits}, 链接: {share.share_url}")
            matches.append(
                SubscriptionMatch(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    share=share,
                    matched_keywords=hits,
                )
            )

        return matches


def validate_subscription_pattern(pattern: str) -> None:
    if not pattern.strip():
        raise ValueError("subscription pattern must not be empty")

    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"subscription pattern must be at most {MAX_PATTERN_LENGTH} characters")

    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"invalid subscription pattern: {exc}") from exc


def validate_subscription_signals(
    *,
    pattern: str | None,
    tmdb_id: int | None,
    aliases: tuple[str, ...] | list[str] | None,
) -> None:
    has_pattern = bool(pattern and pattern.strip())
    has_aliases = bool(aliases and any(str(a).strip() for a in aliases))
    has_tmdb = tmdb_id is not None
    if not (has_pattern or has_aliases or has_tmdb):
        raise ValueError("subscription rule must define at least one of pattern, tmdb_id, aliases")
    if has_pattern:
        validate_subscription_pattern(pattern or "")


@dataclass(frozen=True)
class _PreparedRule:
    pattern_regex: Pattern[str] | None
    pattern_source: str
    tmdb_id: int | None
    tmdb_regex: Pattern[str] | None
    aliases: tuple[str, ...]
    aliases_lower: tuple[str, ...]


def _prepare_rule(rule: SubscriptionRule) -> _PreparedRule:
    pattern_regex: Pattern[str] | None = None
    pattern_source = ""
    if rule.pattern and rule.pattern.strip():
        validate_subscription_pattern(rule.pattern)
        pattern_regex = re.compile(rule.pattern, re.IGNORECASE)
        pattern_source = rule.pattern

    tmdb_regex: Pattern[str] | None = None
    if rule.tmdb_id is not None and rule.tmdb_id > 0:
        tmdb_regex = re.compile(rf"(?<!\d){rule.tmdb_id}(?!\d)")

    cleaned_aliases: list[str] = []
    cleaned_lower: list[str] = []
    for alias in rule.aliases:
        stripped = str(alias).strip()
        if not stripped:
            continue
        cleaned_aliases.append(stripped)
        cleaned_lower.append(stripped.lower())

    return _PreparedRule(
        pattern_regex=pattern_regex,
        pattern_source=pattern_source,
        tmdb_id=rule.tmdb_id if rule.tmdb_id and rule.tmdb_id > 0 else None,
        tmdb_regex=tmdb_regex,
        aliases=tuple(cleaned_aliases),
        aliases_lower=tuple(cleaned_lower),
    )


def _collect_hits(prepared: _PreparedRule, text: str, text_lower: str) -> list[str]:
    hits: list[str] = []
    if prepared.tmdb_regex is not None and prepared.tmdb_regex.search(text):
        hits.append(f"tmdb:{prepared.tmdb_id}")
    for alias, alias_lower in zip(prepared.aliases, prepared.aliases_lower):
        if alias_lower and alias_lower in text_lower:
            hits.append(alias)
    if prepared.pattern_regex is not None and prepared.pattern_regex.search(text):
        hits.append(prepared.pattern_source)
    return hits
