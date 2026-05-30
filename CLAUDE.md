# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Communication

Prefer Chinese when communicating with the user and presenting information, unless code, commands, logs, or external API names are clearer in their original language.

## Project shape

115 资源中心：自动从 Telegram 公开频道抓取 115 分享链接 → 按订阅规则匹配 → 转存到中转目录 → TMDB 整理重命名 → 移动到媒体库 → 通知。后端是 Python CLI + FastAPI；前端是 Vite + React 19 + Tailwind。

仓库目前没有 `pyproject.toml` / `setup.py` / README；`requirements.txt` 仅列出 4 个直接运行时依赖（`fastapi`, `uvicorn`, `httpx`, `p115client`）。不要假设有 pytest、ruff、mypy、black 等工具配置——如要使用，先添加对应配置。

## Commands

后端（在仓库根目录运行）：
- `python -m unittest discover -s tests -v` — 全量测试（446 个，使用 stdlib `unittest`，从仓库根目录默认发现会得到 0 个测试，必须用 `-s tests`）。
- `python -m unittest tests.test_<module> -v` — 单个测试模块。
- `python -m unittest tests.test_<module>.<ClassName>.<test_name>` — 单个测试用例。
- `python -m py_compile main.py src/**/*.py` — 仅语法校验。
- `uvicorn src.api.app:app --reload` — 启动 FastAPI 服务。
- `python main.py <subcommand>` — CLI 入口；见 `build_parser()` (main.py:33)，子命令含 `parse-share-text`、`collect-tg-web-history`、`collect-tg-web-incremental`、`tg-collector-status`、`list-share`、`save-share`、`list-folder`、`plan-organize-json`、`organize-run-once`、`resolve-tmdb-movie`、`resolve-tmdb-multi`、`dry-run-backend`、`subscription-{list,create,enable,disable,delete,test,process}`、`runtime-{status,start,stop,worker}`。`runtime-worker` 现在跑 `EventDrivenRuntime`（事件驱动 + 兜底轮询的常驻循环），`--tick-seconds` 控制兜底轮询间隔。

前端（`frontend/` 目录）：
- `npm run dev` — Vite 开发服务（默认端口 5173，已在 CORS 白名单）。
- `npm run build` — `tsc -b && vite build`。
- `npm run preview` — 预览构建产物。

## Architecture

**严格分层，单向依赖**。每个模块有明确职责边界，违反边界会破坏测试和未来扩展。

### 运行时模型：三核心 + 工具类（事件驱动）

调度层采用"核心类 + 工具类"二分：

- **工具类**（无状态、被持有、可复用、不落业务队列）：115 网盘工具（`src/storage/service115.py`）、TMDB 工具（`src/organizing/`）、订阅工具（规则 CRUD + 纯匹配，**不参与落库**）。
- **核心类**（有状态、事件驱动 + 低频兜底轮询，`src/cores/`）：`CollectorCore`（采集 → 订阅匹配 → 落 `collect_queue`/`transfer_queue`）、`TransferCore`（读待转存 → `save_share` → 标记结果）、`OrganizerCore`（读已转存 → TMDB + 重命名 + 移动）。
- **事件链**：`CollectorCore →COLLECT_DONE→ TransferCore →TRANSFER_DONE→ OrganizerCore →ORGANIZE_DONE`。进程内 pub/sub（`src/events/`，`EventBus`），无 MQ 中间件。
- **核心原则：事件是触发器，DB 是真相**。事件不携带业务数据；消费者收到事件后去 DB 读对应状态记录；事件漏发不丢数据（下一轮兜底轮询补上）。
- **失败重试**：转存重试 3 次；整理失败记录跳过、标记等待人工处理（不自动重试）。
- **部署**：双进程——常驻 worker 进程（三核心跑在一个 `EventDrivenRuntime` 长驻循环）+ API 进程作控制平面。
- **手动触发跨进程桥**：API 进程的事件发布不到 worker 进程总线，故 `POST /runtime/trigger` 把 `manual_collect/transfer/organize` 写入 `runtime_manual_triggers` 表，worker 每 tick `claim_pending_manual_triggers()`（`BEGIN IMMEDIATE` 防重复认领）转成进程内事件。

### 数据流（端到端）

```
Telegram 公开频道 HTML
   ↓ (collectors)
collect_queue (SQLite)
   ↓ (subscriptions 匹配)
transfer_queue (SQLite)
   ↓ (storage115 → p115client 调 share_receive)
中转目录 (staging_cid)
   ↓ (organizing：TMDB 元数据 + 重命名 + 分类)
媒体库目录
   ↓ (notifications)
Webhook / InMemory
```

### 模块边界（关键约束）

- `src/collectors/shares.py`：纯粹的 115 分享链接解析（`parse_115_shares`、`ParsedShareLink`、`CollectedShare`）；不得包含 Telegram、订阅匹配、转存、TMDB 或通知副作用。
- `src/collectors/telegram_web.py`：仅抓取/解析 `https://t.me/s/<channel>` HTML，返回 `CollectedShare`；fetcher 必须可注入以便测试用本地 HTML fixture。
- `src/queue/`：SQLite 持久化边界，**state-only**。表：`collect_queue`、`transfer_queue`、`collector_cursors`。不得包含 worker、Telegram 抓取、转存执行、TMDB 查询、文件移动或通知发送。模型见 `src/queue/models.py`；状态常量 `PENDING`/`RUNNING`/`SUCCESS`/`SKIPPED`/`FAILED`。
- `src/subscriptions/matcher.py`：纯匹配（输入 `CollectedShare`，输出 `SubscriptionMatch`）；不得 fetch、转存、TMDB、通知或持久化。
- `src/subscriptions/transfer_plan.py`：将 `SubscriptionMatch` 转为 `TransferPlan` 候选；**不得调** `Storage115Service.save_share()` 或做持久化/通知。
- `src/storage/service115.py`：`p115client` 的唯一封装；业务代码必须依赖 `Storage115Service`，不得直接消费 `p115client` 的原始返回结构。通过 `Storage115Item._normalize_item` 规范化外部对象。提供 `list_folder`、`rename_file`、`move_file`、`delete_file`、`ensure_folder`、`ensure_dir`（带缓存）、`save_share` 等方法。构造时必须显式传 `config` 或 `client`（无 env 兜底）。
- `src/processors/`：编排层（被核心类薄包装）。`telegram_collection.py` 做增量轮询；`subscription_processor.py` 扫 `collect_queue` 产出 `transfer_queue`；`transfer_queue.py`、`organize_folder.py`、`organize_run.py`、`collect_queue.py` 是各队列的处理器。`organize_run.py` 实现完整的整理流程，包括 TMDB 元数据解析、重复文件检测、重命名和移动。
- `src/events/`：进程内事件总线。`EventBus`（线程安全同步 pub/sub，订阅者异常隔离）+ 事件常量 `COLLECT_DONE`/`TRANSFER_DONE`/`ORGANIZE_DONE`/`MANUAL_*`。`Event` 不带业务数据。
- `src/cores/`：三核心 `CollectorCore`/`TransferCore`/`OrganizerCore`，薄包装现有 processor，完成后仅当有产出才 publish 下游事件，返回 `CoreResult`（core/status/processed/succeeded/skipped/failed/error）。
- `src/runtime/`：调度与控制平面。`RuntimeFactory` 装配各核心与工具；`EventDrivenRuntime`（`src/runtime/event_runtime.py`）订阅事件级联触发 + per-tick 去重 + 未级联到的核心兜底轮询，`run_once()` / `run_until_stopped(max_ticks=)` 跑循环；`RuntimeControlService` 管理 desired/effective 状态；组件枚举：`telegram_collector`、`subscription_processor`、`transfer_processor`、`organizer`。（旧 `RuntimeWorker`/`scheduler.py` 已删除。）
- `src/api/`：FastAPI 入口。`src/api/app.py` 创建应用并从 YAML 加载配置；路由集中在 `src/api/routes.py`，schemas 在 `schemas.py`，依赖注入在 `dependencies.py`。CORS 由 `config/api.yml` 控制，默认 `http://localhost:5173`、`http://127.0.0.1:5173`。
- `src/config/`：配置管理（**纯 YAML**）。`loader.py` 提供 `ConfigLoader` 加载 YAML 配置；`yaml_settings.py` 定义 `AppConfig` 及各子配置类（`NetdiskConfig`、`TmdbConfig`、`OrganizeConfig` 等）；`settings.py` 提供 `AppSettings.from_yaml(config_dir)`（config 目录缺失时返回空 `AppSettings()`）；`yaml_writer.py` 的 `update_yaml_values()` 用 `ruamel.yaml` 保注释写回（settings PATCH 路由用）。无 env/dotenv 路径。
- `src/organizing/`：TMDB 解析器（`TmdbMovieResolver`、`TmdbMultiResolver`）、`OrganizeRule`、`build_organize_plan`、`OrganizeRepository`。整理逻辑：
  - TMDB 元数据解析失败（resolver 返回 `None`）的文件会被跳过，留在中转目录，状态标记为 `SKIPPED_UNMATCHED`。
  - 目标目录存在同名文件时，比较文件大小：保留较大文件，跳过或删除较小文件。如果当前文件 ≤ 已存在文件，标记为 `SKIPPED_DUPLICATE` 并跳过；如果当前文件 > 已存在文件，删除已存在文件后移动当前文件。
  - 状态常量：`PLANNED`、`SUCCESS`、`FAILED`、`SKIPPED_DIR`、`SKIPPED_UNMATCHED`、`SKIPPED_DUPLICATE`。
- `src/notifications/`：`Notifier` 抽象，`InMemoryNotifier`、`WebhookNotifier`（`WebhookConfig`）。
- `src/resources/`：资源频道注册表（`channels` 表）。

### 入口

- `main.py` — CLI 入口；命令分派和 `Storage115Service` 装配。
- `src/api/app.py` — FastAPI `app`；从仓库根 `config/` 目录的 YAML 加载配置（`AppSettings.from_yaml`），目录缺失时返回空配置。
- `src/processors/dry_run_backend.py` — 完整端到端离线流水线（`DryRunBackendService`），用 fakes（`FakeTransferStorage`、`FakeOrganizeStorage`、`FakeMetadataResolver`），是回归测试和最小集成验证的主要工具。

## Configuration

应用配置**仅支持 YAML**（env/dotenv 已淘汰）。配置文件位于仓库根 `config/` 目录，按功能分类：

- `config/netdisk.yml` — 115 网盘配置（`p115.cookies`、`p115.transfer_cid`、`p115.cache_home`、`p115.ensure_cookies`）
- `config/tmdb.yml` — TMDB API 配置（`bearer_token`、`language`）
- `config/organize.yml` — 整理系统配置（`organize.media_library_root_cid`、`duplicate_strategy` 等）
- `config/subscription.yml` — 订阅规则配置
- `config/notification.yml` — 通知配置（webhook）
- `config/api.yml` — API 服务配置（CORS、端口、主机等）
- `config/runtime.yml` — 运行时调度器配置（兜底轮询间隔等）

每个配置文件包含详细的中文注释。读取走 `AppSettings.from_yaml(config_dir)`（目录缺失时返回空配置，不抛错）；写入走 `update_yaml_values()`（用 `ruamel.yaml` 保留注释，注意它会给新写入的字符串值加引号）。

settings PATCH 路由（`/netdisk/settings`、`/organizer/settings`、`/notification/settings`）直接把改动写回对应 YAML；目标文件缺失时返回 503。

## Runtime 必需配置

- `config/netdisk.yml` 的 `p115.cookies` — **必需** 用于任何真实 115 操作；缺失会在 `Storage115Service` 构造时抛 `Storage115Error`。
- `p115.transfer_cid` — 默认中转目录 CID（`save-share` 未指定 `--target-cid` 时使用）。
- `p115.ensure_cookies` — 透传给 `P115Client` 的 cookie 校验/刷新行为。
- `p115.cache_home` — `p115client` 缓存目录；默认 `.p115client.cache.d`。wrapper 会把 `USERPROFILE` 指向这个路径，避免 p115client 默认写入用户家目录在受限环境下失败。
- `config/tmdb.yml` 的 `bearer_token`、`language`（默认 `zh-CN`）— `resolve-tmdb-*` 和 `organize-run-once` 必需。
- `config/notification.yml` — 可选的 Webhook 通知。
- `config/api.yml` 的 CORS — 允许源列表。

`PROJECT_PROGRESS.md` 是设计日志，记录历史决策；`AGENTS.md` 与本文件互补，包含等价的模块边界约束。

## Implementation notes

- 队列幂等性：`collect_queue` 用 `UNIQUE(source_type, source_id, message_id)`；`transfer_queue` 用 `UNIQUE(share_url, staging_cid)`，重入队时合并 `matched_rules_json` 与 `source_messages_json`。
- `claim_next_collect` / `claim_next_transfer` 使用 `BEGIN IMMEDIATE` + 状态转 `RUNNING` 抢占；如果进程崩溃，`reset_running_collects()` / `reset_running_transfers()` 用于恢复。
- `save_share()` 在未传 `ids` 时**接收所有顶层分享文件**；要做过滤转存请显式传 `ids`。
- 当前阶段 Telegram 采集只支持公开 `t.me/s/<channel>` HTML 当前页；不做后台 daemon、深度翻页、账号登录、Bot API 或 Telethon。Telethon 是后续方向但已明确延期。
- TMDB 测试通过 `_FakeTmdbClient` 注入响应（`main.py:238`），离线 CLI 路径走 `--json-file`。
- `DryRunBackendService` 是观测整条管线的最快方式，参考 `tests/test_backend_dry_run_flow.py` 和 `tests/test_dry_run_backend.py`。
- 整理器（organizer）行为：
  - 无法解析 TMDB 元数据的文件（`metadata is None`）会被跳过，留在中转目录，不会移动到"未识别"目录。
  - 目标目录存在同名文件时，按文件大小决策：当前文件 ≤ 已存在文件时跳过（`SKIPPED_DUPLICATE`），当前文件 > 已存在文件时删除旧文件并移动新文件。
  - 测试覆盖：`tests/test_organize_duplicate_handling.py` 专门测试重复文件处理逻辑。
