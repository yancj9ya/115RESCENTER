# 部署状态

## 当前运行状态

### 后端服务
- **端口**: 8001
- **地址**: http://localhost:8001
- **状态**: ✅ 运行中
- **日志文件**: `backend_8001.log`

### 前端服务
- **端口**: 5173
- **地址**: http://localhost:5173
- **状态**: ✅ 运行中
- **日志文件**: `frontend_new.log`

## 新增功能

### 手动触发按钮
在前端"日志中心" → "总览"页面，新增三个手动触发按钮：

1. **收集匹配** - 处理收集队列，匹配订阅规则
   - API: `POST /subscriptions/process`
   - 限制: 最多 50 条

2. **转存文件** - 处理转存队列，保存到网盘
   - API: `POST /transfer-queue/process`
   - 限制: 最多 20 条

3. **整理文件** - 整理中转目录，移动到媒体库
   - API: `POST /organizer/run-once`
   - 使用默认中转目录

### 日志输出
所有手动触发操作都会输出详细日志到"系统日志"标签页：

- ✅ 订阅处理器日志（扫描、匹配、创建、跳过、失败）
- ✅ 转存队列处理器日志（开始、成功、失败、重试）
- ✅ 整理运行日志（扫描、计划、成功、跳过、失败）
- ✅ API 层日志（手动触发开始、完成统计）

## 访问方式

1. 打开浏览器访问: http://localhost:5173
2. 进入"日志中心"页面
3. 点击"总览"标签
4. 使用三个手动触发按钮
5. 切换到"系统日志"标签查看详细日志

## 注意事项

### 端口变更
- 后端从 8000 端口改为 **8001 端口**（8000 端口被占用）
- 前端 vite 配置已更新，代理指向 8001 端口
- 如需恢复 8000 端口，需要先清理僵尸进程

### 配置要求
- **收集匹配**: 需要订阅规则和中转目录 CID
- **转存文件**: 需要 115 cookies 和中转目录 CID
- **整理文件**: 需要 115 cookies、TMDB token、媒体库根目录 CID

## 测试命令

### 测试后端 API
```bash
# 健康检查
curl http://localhost:8001/health

# 测试转存队列处理
curl -X POST http://localhost:8001/transfer-queue/process \
  -H "Content-Type: application/json" \
  -d '{"limit": 1}'

# 测试订阅处理
curl -X POST http://localhost:8001/subscriptions/process \
  -H "Content-Type: application/json" \
  -d '{"limit": 1}'

# 测试整理运行
curl -X POST http://localhost:8001/organizer/run-once \
  -H "Content-Type: application/json" \
  -d '{"staging_cid": null}'
```

### 查看日志
```bash
# 查看后端日志
tail -f backend_8001.log

# 查看前端日志
tail -f frontend_new.log

# 查看应用日志
tail -f logs/app_20260529.log
```

## 文件清单

### 新增文件
- `frontend/src/components/ManualTriggers.tsx` - 手动触发按钮组件
- `MANUAL_TRIGGERS.md` - 手动触发功能文档
- `DEPLOYMENT_STATUS.md` - 本文件

### 修改文件
- `src/api/routes.py` - 新增转存队列处理 API 和日志
- `src/api/dependencies.py` - 新增转存队列处理器依赖
- `src/api/schemas.py` - 新增转存队列处理请求/响应模型
- `src/processors/subscription_processor.py` - 添加详细日志
- `src/processors/transfer_queue.py` - 添加详细日志
- `frontend/src/api.ts` - 新增 API 调用函数
- `frontend/src/types.ts` - 新增类型定义
- `frontend/src/dashboard/LogCenterSummary.tsx` - 集成手动触发组件
- `frontend/vite.config.ts` - 更新代理配置（8001 端口）
- `LOGGING_SYSTEM.md` - 更新日志文档

## 下次启动

如果需要重新启动服务：

```bash
# 启动后端（8001 端口）
cd "I:\Code\PythonCode\115RESCENTER"
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8001 &

# 启动前端
cd frontend
npm run dev &
```
