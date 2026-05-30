# 手动触发功能

## 概述

在前端"日志中心"页面的"总览"标签中，新增了三个手动触发按钮，用于手动执行收集、转存、整理流程。

## 功能说明

### 1. 收集匹配（processSubscriptions）
- **功能**: 处理收集队列（collect_queue），根据订阅规则匹配分享链接，将匹配的链接加入转存队列（transfer_queue）
- **API 端点**: `POST /subscriptions/process`
- **参数**: `{ limit: 50 }` - 最多处理 50 条收集记录
- **返回**: 
  - `scanned`: 扫描的记录数
  - `matched`: 匹配的记录数
  - `created`: 创建的转存任务数
  - `skipped`: 跳过的记录数
  - `errors`: 错误列表

### 2. 转存文件（processTransferQueue）
- **功能**: 处理转存队列（transfer_queue），将分享链接的文件转存到 115 网盘的中转目录
- **API 端点**: `POST /transfer-queue/process`
- **参数**: `{ limit: 20 }` - 最多处理 20 条转存任务
- **返回**:
  - `processed`: 处理的任务数
  - `success`: 成功的任务数
  - `failed`: 失败的任务数
  - `errors`: 错误列表

### 3. 整理文件（runOrganizerOnce）
- **功能**: 扫描中转目录，使用 TMDB 解析元数据，重命名并移动文件到媒体库
- **API 端点**: `POST /organizer/run-once`
- **参数**: `{ staging_cid: null }` - 使用配置的默认中转目录
- **返回**:
  - `scanned_count`: 扫描的文件数
  - `planned_count`: 计划整理的文件数
  - `success_count`: 成功整理的文件数
  - `skipped_count`: 跳过的文件数
  - `failed_count`: 失败的文件数

## 使用场景

### 典型工作流程
1. **收集匹配**: 从 Telegram 频道采集到的分享链接存储在收集队列中，点击"收集匹配"按钮，系统会根据订阅规则匹配这些链接，将匹配的链接加入转存队列
2. **转存文件**: 点击"转存文件"按钮，系统会将转存队列中的分享链接保存到 115 网盘的中转目录
3. **整理文件**: 点击"整理文件"按钮，系统会扫描中转目录，使用 TMDB 解析文件名，重命名并移动到媒体库的对应分类目录

### 手动干预场景
- **测试订阅规则**: 修改订阅规则后，手动触发收集匹配，验证规则是否正确
- **批量转存**: 积累了一批分享链接后，手动触发转存，避免频繁调用 API
- **立即整理**: 转存完成后，立即触发整理，快速将文件移动到媒体库
- **错误重试**: 某个环节失败后，修复问题后手动重试

## 前端实现

### 组件位置
- **文件**: `frontend/src/components/ManualTriggers.tsx`
- **集成**: `frontend/src/dashboard/LogCenterSummary.tsx`

### 状态管理
每个按钮有四种状态：
- `idle`: 空闲状态，可以点击
- `loading`: 处理中，按钮禁用
- `success`: 成功，显示绿色提示，3 秒后恢复
- `error`: 失败，显示红色提示，5 秒后恢复

### 用户体验
- 点击按钮后立即显示"处理中..."状态
- 完成后显示详细的处理结果（成功/失败数量）
- 错误时显示错误信息
- 自动恢复到空闲状态，可以再次点击

## 后端实现

### API 端点
- `POST /subscriptions/process` - 已存在，用于收集匹配
- `POST /transfer-queue/process` - **新增**，用于转存队列处理
- `POST /organizer/run-once` - 已存在，用于整理运行

### 依赖注入
- `get_transfer_queue_processor()` - **新增**，创建 `TransferQueueProcessor` 实例
- 依赖 `QueueRepository`、`Storage115Service`

### 处理逻辑
转存队列处理器（`TransferQueueProcessor`）：
- 从队列中领取待处理的转存任务（`claim_next_transfer`）
- 调用 `Storage115Service.save_share()` 转存文件
- 标记任务为成功（`mark_transfer_success`）或失败（`mark_transfer_failed_or_retry`）
- 失败任务会自动重试，最多 3 次

## 配置要求

### 收集匹配
- 需要配置订阅规则（`subscriptions` 表）
- 需要配置中转目录 CID（`P115_TRANSFER_CID`）

### 转存文件
- 需要配置 115 网盘 cookies（`P115_COOKIES`）
- 需要配置中转目录 CID（`P115_TRANSFER_CID`）

### 整理文件
- 需要配置 115 网盘 cookies（`P115_COOKIES`）
- 需要配置 TMDB API token（`TMDB_BEARER_TOKEN`）
- 需要配置媒体库根目录 CID（`MEDIA_LIBRARY_ROOT_CID`）

## 日志输出

所有手动触发操作都会输出详细的日志，可以在"系统日志"标签页查看：
- 收集匹配: 显示扫描、匹配、创建的记录数
- 转存文件: 显示转存过程、文件数、成功/失败状态
- 整理文件: 显示扫描、计划、重命名、移动、成功/失败统计

## 测试

### 后端测试
```bash
# 测试转存队列处理
curl -X POST http://localhost:8000/transfer-queue/process \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'

# 测试整理运行
curl -X POST http://localhost:8000/organizer/run-once \
  -H "Content-Type: application/json" \
  -d '{"staging_cid": null}'
```

### 前端测试
1. 启动前端: `cd frontend && npm run dev`
2. 访问 http://localhost:5173
3. 进入"日志中心" → "总览"
4. 点击三个手动触发按钮，观察状态变化和结果提示

## 注意事项

1. **并发控制**: 手动触发时，如果运行时调度器（runtime worker）也在运行，可能会同时处理队列，导致竞争。建议在手动操作时暂停运行时调度器。
2. **错误处理**: 如果某个环节失败，查看"系统日志"获取详细错误信息，修复问题后再次手动触发。
3. **批量限制**: 每次手动触发都有数量限制（收集 50 条，转存 20 条），避免一次处理过多任务导致超时。
4. **状态同步**: 手动触发完成后，页面上的队列统计和整理记录会在下次刷新时更新。
