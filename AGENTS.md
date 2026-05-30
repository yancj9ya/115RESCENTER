# AGENTS.md

## Communication
- Prefer Chinese when communicating with the user and presenting information, unless code, commands, logs, or external API names are clearer in their original language.

## Project shape
- This is a small Python CLI project, not a packaged app yet: `main.py` is the entrypoint and imports from `src.collectors`, `src.config`, `src.storage`, and pure subscription code lives under `src.subscriptions`.
- `src/queue/` owns the SQLite queue repository boundary: `collect_queue` and `transfer_queue` are persisted business queues, and repository code must stay state-only.
- Keep `src/queue/` free of workers, transfer execution, Telegram fetching, TMDB queries, file moving, and notification sending.
- `src/collectors/shares.py` owns pure 115 share-link parsing (`parse_115_shares`) and data shapes (`ParsedShareLink`, `CollectedShare`); keep it free of Telegram, subscription matching, transfer, TMDB, and notification side effects.
- `src/collectors/telegram_web.py` owns public Telegram channel web-page collection via `https://t.me/s/<channel>` HTML; it should only fetch/parse messages and return `CollectedShare` records, with fetchers injectable for tests.
- `src/subscriptions/matcher.py` owns first-stage subscription matching (`SubscriptionRule`, `SubscriptionMatcher`, `SubscriptionMatch`); keep it pure: input `CollectedShare`, output matches, no Telegram fetching, 115 transfer, TMDB, notification, or persistence side effects.
- `src/subscriptions/transfer_plan.py` converts `SubscriptionMatch` records into `TransferPlan` candidates; it must not call `Storage115Service.save_share()` or perform persistence/notification side effects.
- `src/storage/service115.py` is the boundary around `p115client`; keep business code depending on `Storage115Service`, not raw `p115client` response shapes.
- `PROJECT_PROGRESS.md` is the main design log. It records intended next modules (TMDB organizing, notifications) that are not implemented yet.

## Commands and verification
- CLI smoke commands documented by the repo:
  - `python main.py parse-share-text "<text containing 115 links>"`
  - `python main.py collect-tg-web-history <channel> [--limit <n>] [--html-file <path>]`
  - `python main.py list-share <share_code> [receive_code]`
  - `python main.py save-share <share_code> [receive_code] --target-cid <cid>`
  - `python main.py list-folder <cid>`
- No `pyproject.toml`, `requirements*.txt`, README, CI workflow, or test config exists at repo root. Do not invent pytest/ruff/mypy commands unless you add their config first.
- Current tests use stdlib `unittest`; run discovery with `python -m unittest discover -s tests -v` because default discovery from repo root found 0 tests.
- For syntax-only verification of current code, use Python compilation, e.g. `python -m py_compile main.py src/collectors/shares.py src/collectors/telegram_web.py src/config/settings.py src/storage/service115.py src/subscriptions/matcher.py src/subscriptions/transfer_plan.py src/queue/models.py src/queue/repository.py tests/test_queue_repository.py`.

## Runtime environment
- 115 operations require `P115_COOKIES`; missing cookies raise `Storage115Error` during service construction.
- Optional env vars used by current code:
  - `P115_TRANSFER_CID` default target folder for `save-share` when `--target-cid` is omitted.
  - `P115_ENSURE_COOKIES=1|true|True` passes cookie validation/refresh behavior through to `P115Client`.
  - `P115_CACHE_HOME` controls the `p115client` cache location.
- `p115client` writes cache under the user profile by default. Current wrapper sets `USERPROFILE` to `P115_CACHE_HOME` when provided, so prefer a workspace-local cache such as `.p115client.cache.d` in restricted environments.

## Implementation notes
- Normalize external 115 API objects through `Storage115Item`; `_normalize_item` already handles dicts and attribute-style objects with multiple possible key names.
- `save_share()` intentionally receives all top-level share items when `ids` is not supplied; pass explicit ids if adding filtered transfer behavior.
- Telegram web collection is implemented only for public `t.me/s/<channel>` HTML history pages. It must not perform subscription matching, 115 transfer, TMDB work, or notifications.
