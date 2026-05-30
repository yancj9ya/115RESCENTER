# 配置指南

本文档说明如何配置 115 资源中心。

## 配置方式

应用支持两种配置方式：

1. **YAML 配置文件**（推荐）：配置集中在 `config/` 目录，按功能分类，包含详细注释
2. **环境变量**（兼容旧方式）：通过 `.env` 文件配置

## 快速开始

### 方式一：使用 YAML 配置（推荐）

1. 如果已有 `.env` 文件，运行迁移工具：
   ```bash
   python migrate_config.py
   ```

2. 编辑配置文件，填入必需的配置项：
   ```bash
   # 编辑网盘配置
   notepad config/netdisk.yml
   
   # 编辑 TMDB 配置
   notepad config/tmdb.yml
   ```

3. 必需配置项：
   - `config/netdisk.yml` 中的 `p115.cookies` — 115 网盘 Cookie
   - `config/netdisk.yml` 中的 `p115.transfer_cid` — 中转目录 CID
   - `config/tmdb.yml` 中的 `tmdb.bearer_token` — TMDB API Token
   - `config/organize.yml` 中的 `organize.media_library_root_cid` — 媒体库根目录 CID

### 方式二：使用环境变量

1. 复制示例配置文件：
   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件，填入必需的配置项：
   ```bash
   notepad .env
   ```

3. 必需配置项：
   - `P115_COOKIES` — 115 网盘 Cookie
   - `P115_TRANSFER_CID` — 中转目录 CID
   - `TMDB_BEARER_TOKEN` — TMDB API Token
   - `MEDIA_LIBRARY_ROOT_CID` — 媒体库根目录 CID

## 配置文件说明

### config/netdisk.yml

115 网盘相关配置：

- `p115.cookies` — 115 网盘 Cookie（必需）
  - 获取方式：浏览器登录 115.com，打开开发者工具，复制 Cookie
  - 格式：`UID=...; CID=...; SEID=...; KID=...`

- `p115.transfer_cid` — 中转目录 CID（必需）
  - 用途：转存分享链接的目标目录
  - 获取方式：在 115 网盘中创建一个目录，从 URL 中获取 CID

- `p115.ensure_cookies` — 是否确保 Cookie 有效性（可选，默认 false）
  - 启用后会自动刷新过期的 Cookie

- `p115.cache_home` — 缓存目录（可选，默认 `.p115client.cache.d`）

### config/tmdb.yml

TMDB API 配置：

- `tmdb.bearer_token` — TMDB API Bearer Token（必需）
  - 获取方式：注册 TMDB 账号，在 https://www.themoviedb.org/settings/api 申请 API Key
  - 格式：`Bearer eyJ...`

- `tmdb.language` — 查询语言（可选，默认 `zh-CN`）

### config/organize.yml

整理系统配置：

- `organize.media_library_root_cid` — 媒体库根目录 CID（必需）
  - 用途：整理后的文件存放位置
  - 获取方式：在 115 网盘中创建媒体库目录，从 URL 中获取 CID

- `organize.auto_organize` — 是否启用自动整理（可选，默认 false）

- `organize.duplicate_strategy` — 重复文件处理策略（可选，默认 `keep_larger`）
  - `keep_larger`：保留较大的文件
  - `keep_first`：保留第一个文件
  - `skip`：跳过重复文件

- `organize.unmatched_strategy` — TMDB 解析失败处理（可选，默认 `keep_in_staging`）
  - `keep_in_staging`：留在中转目录
  - `move_to_unmatched`：移动到"未识别"目录

### config/api.yml

API 服务配置：

- `api.cors_origins` — CORS 允许的源（可选）
  - 格式：多个源用逗号分隔
  - 示例：`http://localhost:5173,http://127.0.0.1:5173`

- `api.port` — API 服务端口（可选，默认 8000）

- `api.host` — API 服务主机（可选，默认 `0.0.0.0`）

### config/notification.yml

通知配置：

- `notification.webhook.enabled` — 是否启用 Webhook 通知（可选，默认 false）

- `notification.webhook.url` — Webhook URL（可选）

- `notification.webhook.token` — 认证 Token（可选）

### config/runtime.yml

运行时调度器配置：

- `runtime.enabled` — 是否启用运行时调度器（可选，默认 false）
  - 启用后会自动运行采集、订阅、转存、整理等任务

- `runtime.components` — 各组件的启用状态和间隔时间

## 配置优先级

1. YAML 配置文件（如果 `config/` 目录存在且包含有效配置）
2. 环境变量（`.env` 文件）
3. 默认值

"有效配置"的判断标准：YAML 配置中包含 `p115.cookies` 或 `tmdb.bearer_token`。

## 常见问题

### Q: 如何从 .env 迁移到 YAML？

A: 运行 `python migrate_config.py`，工具会自动读取 `.env` 文件并生成对应的 YAML 配置文件。

### Q: 可以同时使用 YAML 和 .env 吗？

A: 可以，但 YAML 配置优先级更高。如果 YAML 配置有效，将忽略 `.env` 文件。

### Q: 如何获取 115 网盘的 Cookie？

A: 
1. 浏览器登录 https://115.com
2. 打开开发者工具（F12）
3. 切换到 Network 标签
4. 刷新页面
5. 找到任意请求，查看 Request Headers 中的 Cookie
6. 复制完整的 Cookie 字符串

### Q: 如何获取目录的 CID？

A:
1. 在 115 网盘中打开目标目录
2. 查看浏览器地址栏的 URL
3. URL 中 `cid=` 后面的数字就是 CID
4. 示例：`https://115.com/?cid=1234567890` → CID 是 `1234567890`

### Q: 如何获取 TMDB API Token？

A:
1. 注册 TMDB 账号：https://www.themoviedb.org/signup
2. 登录后访问：https://www.themoviedb.org/settings/api
3. 申请 API Key（选择 Developer 类型）
4. 复制 "API Read Access Token (v4 auth)"
5. 格式为 `Bearer eyJ...`

## 配置示例

### 最小配置示例（YAML）

```yaml
# config/netdisk.yml
p115:
  cookies: "UID=...; CID=...; SEID=...; KID=..."
  transfer_cid: 1234567890

# config/tmdb.yml
tmdb:
  bearer_token: "Bearer eyJ..."

# config/organize.yml
organize:
  media_library_root_cid: 9876543210
```

### 完整配置示例（YAML）

参考 `config/` 目录中的配置文件，每个文件都包含详细的注释和说明。
