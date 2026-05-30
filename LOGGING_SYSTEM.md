# 日志系统实现总结

## 已完成功能

### 1. 统一日志配置 (`src/logging_config.py`)

实现了三种日志输出方式：

- **控制台输出**: 实时显示日志到终端（默认 INFO 级别）
- **文件输出**: 保存到 `logs/app_YYYYMMDD.log`（默认 DEBUG 级别）
- **内存缓存**: 保留最近 1000 条日志供前端 API 读取

特性：
- 自动创建日志目录
- 按日期分割日志文件
- 支持自定义日志级别
- 第三方库日志降噪（httpx, urllib3 等设为 WARNING）

### 2. 日志 API 端点 (`src/api/routes_logs.py`)

提供以下接口：

- `GET /logs/recent`: 获取最近的日志记录
  - 参数: `limit` (1-1000), `level` (可选过滤)
  - 返回: JSON 格式的日志列表
  
- `DELETE /logs/clear`: 清空内存日志缓存

- `GET /logs/stream`: SSE 实时日志流（预留接口）

### 3. 前端日志查看器 (`frontend/src/components/LogViewer.tsx`)

功能特性：
- 实时自动刷新（默认 3 秒）
- 日志级别过滤（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 关键词搜索
- 彩色级别标签
- 显示时间戳、模块、函数、行号
- 响应式设计

### 4. 集成到主应用

- 日志查看器已集成到"日志中心"页面
- 新增"系统日志"标签页
- 与现有的收集、转存、整理日志并列显示

## 已添加日志的模块

### Telegram 采集器 (`src/collectors/telegram_web.py`)
```python
logger.info(f"开始采集 Telegram 频道: @{channel}, 限制: {limit} 条消息")
logger.info(f"解析到 {len(messages)} 条消息")
logger.info(f"采集到分享链接: {share.share_url} (消息 {message_id})")
logger.info(f"采集完成: @{channel}, 共采集到 {len(collected)} 个分享链接")
```

### 订阅匹配器 (`src/subscriptions/matcher.py`)
```python
logger.debug(f"匹配分享链接: {share.share_url}")
logger.info(f"匹配成功: 规则 '{rule.name}' (ID: {rule.id}), 关键词: {hits}, 链接: {share.share_url}")
```

### 订阅处理器 (`src/processors/subscription_processor.py`)
```python
logger.info(f"开始订阅处理: limit={limit}, staging_cid={staging_cid}")
logger.info(f"加载了 {len(rules)} 条启用的订阅规则")
logger.debug(f"处理收集记录 #{record.id}: {record.message_id} ({len(record.shares_json)} 个分享)")
logger.info(f"分享链接匹配成功: {share.share_url}, 匹配 {len(share_matches)} 条规则")
logger.debug(f"跳过收集记录 #{record.id}: 无匹配规则")
logger.info(f"收集记录处理成功 #{record.id}: 创建 {plan_count} 个转存任务")
logger.error(f"收集记录处理失败 #{record.id}: {error}", exc_info=True)
logger.info(f"订阅处理完成: 扫描={scanned}, 匹配={matched}, 创建={created}, 跳过={skipped}, 失败={len(errors)}")
```

### 转存队列处理器 (`src/processors/transfer_queue.py`)
```python
logger.info(f"开始转存任务 #{record.id}: share_code={record.share_code}, staging_cid={record.staging_cid}")
logger.info(f"转存任务成功 #{record.id}: share_code={record.share_code}")
logger.warning(f"转存任务失败 #{record.id} (尝试 {record.attempt_count + 1}/{self._max_attempts}): {error}")
logger.error(f"转存任务失败 #{record.id} (已达最大重试次数 {self._max_attempts}): {error}", exc_info=True)
```

### API 路由 (`src/api/routes.py`)
```python
logger.info(f"手动触发订阅处理: limit={request.limit}")
logger.info(f"订阅处理完成: 扫描={summary.scanned}, 匹配={summary.matched}, 创建={summary.created}, 跳过={summary.skipped}")
logger.info(f"手动触发转存队列处理: limit={request.limit}")
logger.info(f"转存队列处理完成: 处理={processed}, 成功={success}, 失败={failed}")
logger.info(f"手动触发整理运行: staging_cid={staging_cid}")
logger.info(f"整理运行完成 (run_id={result.run_id}): 扫描={result.scanned_count}, 成功={result.success_count}, 跳过={result.skipped_count}, 失败={result.failed_count}")
```

### 115 转存服务 (`src/storage/service115.py`)
```python
logger.info(f"开始转存分享: share_code={share_code}, target_cid={target_cid}")
logger.info(f"转存文件数量: {len(receive_ids)}, IDs: {receive_ids}")
logger.info(f"转存成功: share_code={share_code}, 文件数: {len(receive_ids)}")
logger.error(f"转存失败: 没有可转存的文件 (share_code={share_code})")
```

### TMDB 解析器 (`src/organizing/tmdb.py`)
```python
logger.info(f"TMDB 电影搜索: query='{query}', year={year}")
logger.warning(f"TMDB 搜索无结果: query='{query}', year={year}")
logger.info(f"TMDB 解析成功: '{title}' ({year}), 地区: {region}")
```

### 整理服务 (`src/processors/organize_run.py`)
```python
logger.info(f"开始整理运行: run_id={run.id}, staging_cid={staging_cid}")
logger.info(f"扫描到 {len(items)} 个文件/文件夹")
logger.debug(f"跳过目录: {file_name} (ID: {file_id})")
logger.debug(f"解析元数据: {file_name}")
logger.info(f"跳过未匹配文件: {file_name} (无元数据)")
logger.info(f"计划整理: {file_name} -> {target_path}/{plan.new_name}")
logger.info(f"跳过重复文件: {file_name} - {reason}")
logger.info(f"删除较小的重复文件: {file_name} (旧大小: {existing_size}, 新大小: {current_size})")
logger.debug(f"重命名文件: {plan.original_name} -> {plan.new_name}")
logger.debug(f"移动文件到目标目录: CID={target_cid}")
logger.info(f"整理成功: {file_name} -> {target_path}/{plan.new_name}")
logger.error(f"整理失败: {file_name} - {error}", exc_info=True)
logger.info(f"整理运行完成 (run_id={run.id}): 扫描={scanned_count}, 计划={planned_count}, 成功={success_count}, 跳过={skipped_count}, 失败={failed_count}")
```

## 日志文件位置

- **日志目录**: `I:\Code\PythonCode\115RESCENTER\logs\`
- **日志文件**: `app_20260529.log` (按日期命名)
- **编码**: UTF-8

## 使用方式

### 后端使用
```python
import logging

logger = logging.getLogger(__name__)

# 记录日志
logger.debug("调试信息")
logger.info("正常信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 前端访问

1. **Web 界面**: 访问 http://localhost:5173，进入"日志中心" → "系统日志"
2. **API 直接访问**: 
   ```bash
   curl "http://localhost:8000/logs/recent?limit=100&level=INFO"
   ```

## 测试

运行测试脚本生成示例日志：
```bash
python test_logging.py
```

## 下一步优化建议

1. **SSE 实时推送**: 实现 `/logs/stream` 端点，支持实时日志推送
2. **日志持久化查询**: 支持查询历史日志文件
3. **日志导出**: 支持导出日志为 CSV/JSON
4. **日志统计**: 添加日志级别统计图表
5. **完善其他模块日志**: 为队列处理、整理运行等模块添加详细日志
6. **日志轮转**: 实现自动清理旧日志文件
7. **性能监控**: 添加性能指标日志（响应时间、内存使用等）

## 技术栈

- **后端**: Python logging, FastAPI
- **前端**: React 19, TypeScript, Tailwind CSS
- **日志格式**: 结构化 JSON
- **编码**: UTF-8
