from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.db import connect, migrate


class _Unset:
    __slots__ = ()


_UNSET = _Unset()


@dataclass(frozen=True)
class SubscriptionRuleRecord:
    id: int
    name: str
    pattern: str
    enabled: bool
    created_at: str
    updated_at: str
    tmdb_id: int | None = None
    tmdb_kind: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    poster_path: str | None = None


class SubscriptionRepository:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def init_schema(self) -> None:
        migrate(self._db_path)

    def create_rule(
        self,
        *,
        name: str,
        pattern: str,
        enabled: bool = True,
        tmdb_id: int | None = None,
        tmdb_kind: str | None = None,
        aliases: tuple[str, ...] | list[str] | None = None,
        poster_path: str | None = None,
    ) -> SubscriptionRuleRecord:
        aliases_json = _aliases_to_json(aliases)
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO subscription_rules (name, pattern, enabled, tmdb_id, tmdb_kind, aliases_json, poster_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    pattern,
                    self._enabled_to_int(enabled),
                    tmdb_id,
                    tmdb_kind,
                    aliases_json,
                    poster_path,
                ),
            )
            connection.commit()
            row = connection.execute(_SELECT_SQL + " WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return self._rule_from_row(row)
        finally:
            connection.close()

    def list_rules(self) -> list[SubscriptionRuleRecord]:
        connection = connect(self._db_path)
        try:
            rows = connection.execute(_SELECT_SQL + " ORDER BY id ASC").fetchall()
            return [self._rule_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_rule(self, rule_id: int) -> SubscriptionRuleRecord | None:
        connection = connect(self._db_path)
        try:
            row = connection.execute(_SELECT_SQL + " WHERE id = ?", (rule_id,)).fetchone()
            if row is None:
                return None
            return self._rule_from_row(row)
        finally:
            connection.close()

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
    ) -> SubscriptionRuleRecord | None:
        current = self.get_rule(rule_id)
        if current is None:
            return None

        next_name = current.name if name is None else name
        next_pattern = current.pattern if pattern is None else pattern
        next_enabled = current.enabled if enabled is None else enabled
        next_tmdb_id = current.tmdb_id if isinstance(tmdb_id, _Unset) else tmdb_id
        next_tmdb_kind = current.tmdb_kind if isinstance(tmdb_kind, _Unset) else tmdb_kind
        next_poster_path = current.poster_path if isinstance(poster_path, _Unset) else poster_path
        if isinstance(aliases, _Unset):
            next_aliases_json = _aliases_to_json(current.aliases)
        else:
            next_aliases_json = _aliases_to_json(aliases)

        connection = connect(self._db_path)
        try:
            connection.execute(
                """
                UPDATE subscription_rules
                SET name = ?,
                    pattern = ?,
                    enabled = ?,
                    tmdb_id = ?,
                    tmdb_kind = ?,
                    aliases_json = ?,
                    poster_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    next_name,
                    next_pattern,
                    self._enabled_to_int(next_enabled),
                    next_tmdb_id,
                    next_tmdb_kind,
                    next_aliases_json,
                    next_poster_path,
                    rule_id,
                ),
            )
            connection.commit()
            row = connection.execute(_SELECT_SQL + " WHERE id = ?", (rule_id,)).fetchone()
            return self._rule_from_row(row)
        finally:
            connection.close()

    def delete_rule(self, rule_id: int) -> bool:
        connection = connect(self._db_path)
        try:
            cursor = connection.execute(
                "DELETE FROM subscription_rules WHERE id = ?",
                (rule_id,),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def _rule_from_row(self, row: tuple[object, ...]) -> SubscriptionRuleRecord:
        return SubscriptionRuleRecord(
            id=row[0],
            name=row[1],
            pattern=row[2],
            enabled=bool(row[3]),
            created_at=row[4],
            updated_at=row[5],
            tmdb_id=row[6] if row[6] is not None else None,
            tmdb_kind=row[7] if row[7] is not None else None,
            aliases=_aliases_from_json(row[8]),
            poster_path=row[9] if row[9] is not None else None,
        )

    def _enabled_to_int(self, enabled: bool) -> int:
        return 1 if enabled else 0


_SELECT_SQL = (
    "SELECT id, name, pattern, enabled, created_at, updated_at,"
    " tmdb_id, tmdb_kind, aliases_json, poster_path FROM subscription_rules"
)


def _aliases_to_json(aliases: tuple[str, ...] | list[str] | None) -> str | None:
    if aliases is None:
        return None
    cleaned = [alias for alias in (str(a).strip() for a in aliases) if alias]
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def _aliases_from_json(raw: object) -> tuple[str, ...]:
    if raw is None or raw == "":
        return ()
    try:
        decoded = json.loads(str(raw))
    except (TypeError, ValueError):
        return ()
    if not isinstance(decoded, list):
        return ()
    return tuple(str(item) for item in decoded if str(item).strip())
