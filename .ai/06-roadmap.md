# 路线图

## Phase 0 — 脚手架与引擎硬化

- [x] `.ai` 设计文档
- [x] 项目骨架（包结构、配置、端口、本地 Web）
- [x] 引擎：发现 / 窗位+rescale / 流式 MP4 / GIF / 合并 / 安全解压
- [x] CLI `convert` + `serve`；旧脚本 thin wrapper
- [x] 单元测试 + 合成 DICOM 冒烟
- [x] 真实医院 RAR 手工验证（本地）

## Phase 1 — Web 可用

- [x] FastAPI uploads + jobs API
- [x] 静态前端：上传/转换分离、双进度、预览、下载
- [x] 24h TTL 自动清理
- [x] Docker / compose
- [x] 安全默认（关 docs、限流、可选访问令牌、CSP）

## Phase 2 — 体验与稳健性

- [x] SQLite 任务/上传元数据持久化
- [x] 默认不信任 X-Forwarded-For
- [x] UTC 时间统一；README 用户向
- [ ] 转换前序列列表预览 / 勾选
- [ ] 合并时序列标题条
- [ ] 公网强制 ACCESS_TOKEN 启动门闩（P0 余项）

## Phase 3 — 可扩展形态

- [ ] S3/MinIO Storage 适配器
- [ ] Celery/RQ Queue 适配器
- [ ] 反代层限流 / Redis 限流
- [ ] 审计日志（脱敏）

## Phase 4 — 多端（按需）

- [ ] PWA
- [ ] 桌面壳（Tauri）
- [ ] 移动 App

## 非目标

- 医疗器械注册 / 完整 PACS / 诊断级测量
