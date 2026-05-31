from __future__ import annotations

from dataclasses import dataclass

from src.collectors import CollectedShare
from src.subscriptions.matcher import (
    SubscriptionMatcher,
    SubscriptionRule,
    validate_subscription_pattern,
    validate_subscription_signals,
)
from src.subscriptions.repository import _UNSET, SubscriptionRepository, SubscriptionRuleRecord, _Unset


class SubscriptionRuleNotFoundError(ValueError):
    def __init__(self, rule_id: int) -> None:
        super().__init__(f"subscription rule not found: {rule_id}")
        self.rule_id = rule_id


@dataclass(frozen=True)
class SubscriptionTestResult:
    matched: bool
    rule_id: int | None
    rule_name: str | None
    pattern: str
    text: str
    matched_keywords: list[str]


class SubscriptionService:
    def __init__(self, repository: SubscriptionRepository) -> None:
        self._repository = repository

    def create_rule(
        self,
        *,
        name: str,
        pattern: str = "",
        enabled: bool = True,
        tmdb_id: int | None = None,
        tmdb_kind: str | None = None,
        aliases: tuple[str, ...] | list[str] | None = None,
        poster_path: str | None = None,
        year: int | None = None,
        require_year_match: bool = True,
    ) -> SubscriptionRuleRecord:
        normalised_aliases = _normalise_aliases(aliases)
        validate_subscription_signals(pattern=pattern, tmdb_id=tmdb_id, aliases=normalised_aliases)
        return self._repository.create_rule(
            name=name,
            pattern=pattern,
            enabled=enabled,
            tmdb_id=tmdb_id,
            tmdb_kind=tmdb_kind,
            aliases=normalised_aliases,
            poster_path=poster_path,
            year=year,
            require_year_match=require_year_match,
        )

    def list_rules(self) -> list[SubscriptionRuleRecord]:
        return self._repository.list_rules()

    def get_rule(self, rule_id: int) -> SubscriptionRuleRecord | None:
        return self._repository.get_rule(rule_id)

    def update_rule(
        self,
        rule_id: int,
        *,
        name: str | None = None,
        pattern: str | None = None,
        enabled: bool | None = None,
        tmdb_id: int | None | _Unset = _UNSET,
        tmdb_kind: str | None | _Unset = _UNSET,
        aliases: tuple[str, ...] | list[str] | None | _Unset = _UNSET,
        poster_path: str | None | _Unset = _UNSET,
        year: int | None | _Unset = _UNSET,
        require_year_match: bool | None = None,
    ) -> SubscriptionRuleRecord | None:
        current = self._repository.get_rule(rule_id)
        if current is None:
            return None

        effective_pattern = current.pattern if pattern is None else pattern
        effective_tmdb_id = current.tmdb_id if isinstance(tmdb_id, _Unset) else tmdb_id
        if isinstance(aliases, _Unset):
            effective_aliases: tuple[str, ...] = current.aliases
            aliases_payload: tuple[str, ...] | _Unset = _UNSET
        else:
            normalised = _normalise_aliases(aliases)
            effective_aliases = tuple(normalised or ())
            aliases_payload = effective_aliases

        validate_subscription_signals(
            pattern=effective_pattern,
            tmdb_id=effective_tmdb_id,
            aliases=effective_aliases,
        )

        return self._repository.update_rule(
            rule_id,
            name=name,
            pattern=pattern,
            enabled=enabled,
            tmdb_id=tmdb_id,
            tmdb_kind=tmdb_kind,
            aliases=aliases_payload,
            poster_path=poster_path,
            year=year,
            require_year_match=require_year_match,
        )

    def delete_rule(self, rule_id: int) -> bool:
        return self._repository.delete_rule(rule_id)

    def enable_rule(self, rule_id: int) -> SubscriptionRuleRecord:
        return self._require_updated(rule_id, enabled=True)

    def disable_rule(self, rule_id: int) -> SubscriptionRuleRecord:
        return self._require_updated(rule_id, enabled=False)

    def test_match(self, rule_id: int, text: str) -> SubscriptionTestResult:
        record = self._repository.get_rule(rule_id)
        if record is None:
            raise SubscriptionRuleNotFoundError(rule_id)
        return self._test_rule(record, text)

    def test_pattern(self, *, pattern: str, text: str, name: str = "Ad hoc") -> SubscriptionTestResult:
        validate_subscription_pattern(pattern)
        record = SubscriptionRuleRecord(
            id=0,
            name=name,
            pattern=pattern,
            enabled=True,
            created_at="",
            updated_at="",
        )
        result = self._test_rule(record, text)
        return SubscriptionTestResult(
            matched=result.matched,
            rule_id=None,
            rule_name=name,
            pattern=result.pattern,
            text=result.text,
            matched_keywords=result.matched_keywords,
        )

    def _require_updated(self, rule_id: int, *, enabled: bool) -> SubscriptionRuleRecord:
        updated = self._repository.update_rule(rule_id, enabled=enabled)
        if updated is None:
            raise SubscriptionRuleNotFoundError(rule_id)
        return updated

    def _test_rule(self, record: SubscriptionRuleRecord, text: str) -> SubscriptionTestResult:
        rule = SubscriptionRule(
            id=str(record.id),
            name=record.name,
            pattern=record.pattern,
            enabled=record.enabled,
            tmdb_id=record.tmdb_id,
            year=record.year,
            require_year_match=record.require_year_match,
            aliases=record.aliases,
        )
        share = CollectedShare(
            share_code="",
            receive_code="",
            share_url="",
            source_type="subscription_test",
            source_id="local",
            message_id="sample",
            message_text=text,
        )
        matches = SubscriptionMatcher([rule]).match_share(share)
        matched_keywords = matches[0].matched_keywords if matches else []
        return SubscriptionTestResult(
            matched=bool(matches),
            rule_id=record.id,
            rule_name=record.name,
            pattern=record.pattern,
            text=text,
            matched_keywords=matched_keywords,
        )


def _normalise_aliases(aliases: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if aliases is None:
        return ()
    seen: dict[str, None] = {}
    for raw in aliases:
        cleaned = str(raw).strip()
        if cleaned and cleaned not in seen:
            seen[cleaned] = None
    return tuple(seen.keys())
