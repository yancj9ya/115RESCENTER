# 115 自动转存项目讨论进度

## 项目目标

构建一个面向 115 网盘的自动转存与自动整理系统，核心流程包括：

1. 从 Telegram 公开频道等资源入口抓取 115 分享链接。
2. 根据订阅规则验证资源，并将命中的资源转存到 115 网盘中的中转待整理文件夹。
3. 对待整理文件夹中的资源执行自动整理：
   - 根据文件名在 TMDB 检索真实资源名称。
   - 对文件进行规范化重命名。
   - 按分类移动到指定媒体库文件夹。
4. 对已经整理并移动到目标文件夹的资源进行入库通知，通知渠道需要可拓展。

## 当前已确认决策

### 115 网盘操作库

115 网盘操作模块确定优先使用 [`ChenyangGao/p115client`](https://github.com/ChenyangGao/p115client)。

已在当前环境中安装并探索：

- 安装包名：`p115client`
- 当前版本：`0.0.8.4.9`
- 主要入口：
  - `P115Client`
  - `P115ShareFileSystem`
  - `P115FileSystem`

### 初始化方式

推荐通过 Cookie 初始化客户端：

```python
from p115client import P115Client

client = P115Client(cookies="...", ensure_cookies=False)
```

补充注意：

- `p115client` 默认会尝试写入用户目录下的 `~/.p115client.cache.d`。
- 在当前受限沙箱中，导入时需要临时将 `USERPROFILE` 指向工作区才能避免权限问题。
- 实际项目中需要在启动配置或部署文档中处理缓存目录/用户目录权限问题。

## 115 分享读取与转存方案

### 推荐封装方式

优先使用 `P115ShareFileSystem` 处理分享链接内容读取和接收：

```python
from p115client import P115ShareFileSystem

share_fs = P115ShareFileSystem(
    client,
    share_code="...",
    receive_code="...",
)

items = share_fs.listdir()
result = share_fs.receive(ids, to_pid=target_cid)
```

原因：

- 更贴近“把分享链接当成一个只读文件系统”的业务模型。
- 方便先读取分享目录内容，再根据订阅规则决定是否接收。
- 接收时可指定目标目录 `to_pid`，适合转存到“中转待整理文件夹”。

### 底层可用 API

`P115Client` 也提供直接接收分享的底层接口：

```python
client.share_receive({
    "share_code": "...",
    "receive_code": "...",
    "file_id": "...",
    "cid": target_cid,
})
```

核心参数：

- `share_code`：分享码。
- `receive_code`：访问码/接收码。
- `file_id`：分享中的文件或目录 ID，多个 ID 可用英文逗号分隔。
- `cid`：转存到自己网盘中的目标目录 ID。

分享目录读取底层接口：

```python
client.share_snap({
    "share_code": "...",
    "receive_code": "...",
    "cid": 0,
    "limit": 32,
    "offset": 0,
})
```

## 115 文件整理操作方案

文件整理阶段主要使用 `P115Client` 的文件系统相关 API，必要时再封装为更稳定的业务服务。

### 已确认可用接口

```python
client.fs_files(...)
client.fs_rename(...)
client.fs_move(...)
client.fs_mkdir(...)
```

对应能力：

- `fs_files`：列出目录文件。
- `fs_rename`：重命名文件或目录。
- `fs_move`：移动文件或目录。
- `fs_mkdir`：创建目录。

也可使用 `P115FileSystem` 的高级封装：

```python
from p115client import P115FileSystem

fs = P115FileSystem(client)
fs.listdir(cid)
fs.rename(file_id, new_name)
fs.move(file_id, target_cid)
fs.mkdir(parent_cid, folder_name)
```

## 后续拟封装接口

项目内部建议新增 `Storage115Service`，避免业务层直接依赖 `p115client` 的具体方法和返回结构。

建议暴露稳定方法：

```python
class Storage115Service:
    def list_share(self, share_code: str, receive_code: str = ""):
        ...

    def save_share(self, share_code: str, receive_code: str, target_cid: int):
        ...

    def list_folder(self, cid: int):
        ...

    def rename_file(self, file_id: int, new_name: str):
        ...

    def move_file(self, file_id: int, target_cid: int):
        ...

    def ensure_folder(self, parent_cid: int, name: str):
        ...
```

初步职责划分：

- `list_share`：读取分享链接目录结构，用于订阅验证和资源预览。
- `save_share`：将命中资源转存到中转待整理文件夹。
- `list_folder`：扫描中转待整理文件夹。
- `rename_file`：执行 TMDB 匹配后的规范化重命名。
- `move_file`：将资源移动到最终媒体库目录。
- `ensure_folder`：按分类或资源名称创建目标目录。

## 下一步待确认

后续需要继续确认以下模块设计：

1. 订阅规则：关键词、正则、黑名单/白名单、资源类型等规则如何定义和管理。
2. TMDB 整理规则：电影/剧集命名规范、匹配失败策略、目标目录结构。
3. 通知模块：优先支持哪些通知渠道，以及通知触发点如何和队列状态衔接。
4. 部署方式：本地 Python、Docker、定时任务还是常驻服务。
5. Telegram 深度采集：`Telethon` 用户账号模式仍然延期，不属于当前 HTML 增量采集阶段。

## 当前进度同步：115 模块

已完成 115 存储模块的第一版落地，当前代码结构如下：

```text
main.py
src/
  config/
    settings.py
  storage/
    service115.py
```

### 已实现能力

- `Storage115Config`：从环境变量或代码参数构造 115 客户端配置。
- `Storage115Service.list_share`：读取 115 分享顶层或指定目录内容。
- `Storage115Service.save_share`：将分享文件接收到指定 `target_cid`。
- `Storage115Service.list_folder`：列出自己网盘指定目录。
- `Storage115Service.rename_file`：按文件 ID 重命名。
- `Storage115Service.move_file`：按文件 ID 移动到目标目录。
- `Storage115Service.ensure_folder`：目标目录不存在时自动创建。
- `main.py`：提供最小 CLI 验证入口。

### 环境变量

```powershell
$env:P115_COOKIES = "UID=...; CID=...; SEID=..."
$env:P115_CACHE_HOME = "I:\Code\PythonCode\115RESCENTER\.p115client.cache.d"
$env:P115_TRANSFER_CID = "0"
```

### CLI 示例

```powershell
python main.py list-share <share_code> [receive_code]
python main.py save-share <share_code> [receive_code] --target-cid <cid>
python main.py list-folder <cid>
```

### 校验结果

- 已完成基础语法校验。
- 已确认 `p115client` 的核心初始化与文件系统接口可用。

### 后续建议

当前已经完成公开 Telegram HTML 增量采集的第一阶段，后续可继续建设“订阅规则模块”和“转存处理器”，让 `collect_queue` 中的 115 分享链接先经过规则命中，再由独立转存流程调用 `Storage115Service.save_share` 转存到中转目录。

## 资源采集模块设计

### 当前采集范围

资源采集模块当前聚焦 Telegram 公开频道的 `https://t.me/s/<channel>` HTML 页面，后续预留 RSS、网页、手动导入、账号会话采集等扩展入口。

本阶段已选择并实现 public HTML 一次性增量轮询，而不是 `Telethon` 用户账号模式或 Bot API：

- `TelegramWebCollector` 和 `parse_telegram_public_channel_html` 只负责公开 HTML 抓取/解析，不做持久化、订阅匹配、转存、TMDB 或通知。
- `TelegramCollectionService` 负责增量轮询编排：读取 SQLite 游标、调用 fetcher 获取当前页消息、解析消息文本中的 115 分享链接、幂等写入 `collect_queue`，最后更新游标状态。
- `QueueRepository` 持有 `collector_cursors` 和 `collect_queue` 的 SQLite 状态；`src/queue/` 保持 state-only，不包含 worker、Telegram 抓取或业务转存逻辑。
- CLI/API 都调用共享处理服务，避免各自实现不同的增量和幂等规则。

### 已实现能力

- SQLite 游标表：按 `source_type` + `source_id` 保存 `last_seen_message_id`、`last_poll_at`、`last_status`、`last_error`。
- 当前页 public HTML 轮询：使用 `https://t.me/s/<channel>?limit=<n>`，也支持测试/手动 QA 通过本地 HTML fixture 注入。
- 消息解析：当前实现提取 `data-post` 中的 numeric message id、`.tgme_widget_message_text` 文本、`time[datetime]` 发布时间，并从文本中复用 `parse_115_shares` 提取 115 分享。
- 幂等入队：`collect_queue` 对 `source_type` + `source_id` + `message_id` 建唯一约束，重复轮询不会重复创建同一消息的采集记录。
- 游标推进：按数字消息 ID 排序处理；成功轮询后推进到已经完成 reconcile 的最新消息，抓取或入队异常会记录失败状态并保留安全游标。
- CLI：`collect-tg-web-incremental <channel> [--limit <n>] [--html-file <path>] [--db-path <path>]` 执行一次轮询，`tg-collector-status <channel> [--db-path <path>]` 查看游标状态。
- API：`POST /collectors/telegram/{channel}/poll` 执行一次 HTML fixture 驱动的轮询，`GET /collectors/telegram/{channel}/status` 查看游标状态。

### 115 分享链接解析

采集模块支持常见 115 分享格式，例如：

```text
https://115.com/s/<share_code>
https://115.com/s/<share_code>?password=<receive_code>
https://115.com/s/<share_code>#<receive_code>
```

解析结果统一为内部结构：

```python
class CollectedShare:
    share_code: str
    receive_code: str
    share_url: str
    source_type: str
    source_id: str
    message_id: str
    message_text: str
    published_at: datetime | None
```

其中：

- `share_code`：115 分享码。
- `receive_code`：访问码，没有则为空字符串。
- `source_type`：当前 HTML 采集使用 `telegram_web`。
- `source_id`：规范化后的公开频道 username。
- `message_id`：Telegram numeric message ID，用于增量同步、幂等入队和排错。

### 明确限制

当前阶段保持窄范围：一次命令或一次 API 请求只轮询公开 HTML 当前页，不做后台调度、daemon、实时监听、深度历史翻页、账号登录、Bot API、通知扩展、TMDB 整理或 115 转存执行。

`Telethon` 仍然是后续深度采集方向，可用于账号会话、已加入频道历史、实时监听等场景；但它已明确延期，不是本阶段依赖，也没有被加入运行路径。

用户提供的 Telegram HTML 解析线索包括 message wrap/body、forwarded source、photo/background-image URL、inline keyboard buttons、author/channel display name 等。当前实现只提取本阶段入队所需的 message id、文本、datetime 和 115 分享链接；这些更丰富字段是后续 parser hardening 的候选项，除非补齐对应代码和测试，否则不应写入当前数据契约。

### 模块边界

采集模块不做以下事情：

- 不判断资源是否命中订阅。
- 不调用 `Storage115Service` 转存。
- 不调用 TMDB。
- 不发送入库通知。

这些逻辑分别交给订阅模块、115 存储模块、整理模块和通知模块。

### 验证结果

- `python -m unittest discover -s tests -v`：187 个测试通过。
- `python -m py_compile main.py src/collectors/shares.py src/collectors/telegram_web.py src/queue/models.py src/queue/repository.py src/processors/telegram_collection.py src/api/routes.py src/api/schemas.py src/api/dependencies.py`：通过。
- 范围搜索确认本阶段 collector/queue/Telegram processor/API/CLI 路径没有新增 `Telethon`、scheduler/daemon、`Storage115Service.save_share`、`P115Client`、Webhook 或通知扩展；已有 dry-run/notification/storage 模块中的相关词属于既有非本阶段范围。

