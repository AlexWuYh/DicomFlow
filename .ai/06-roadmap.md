# 路线图

与 [11-development.md](./11-development.md) 里程碑模式对照使用；完成条目请勾选并保持与代码一致。

## Phase 0 — 脚手架与引擎

- [x] `.ai` 规格与项目骨架  
- [x] 引擎：发现 / 窗位 / 流式 MP4·GIF / 合并 / 安全解压  
- [x] CLI `convert` + `serve`  
- [x] 单元测试 + 合成 DICOM  
- [x] 真实 RAR 手工验证（本地，PHI 不进 CI）

## Phase 1 — Web 可用

- [x] uploads + jobs API 分离  
- [x] 前端：双进度、预览、下载  
- [x] 24h TTL 清理  
- [x] Docker / compose  
- [x] 安全默认（关 docs、限流、可选令牌、CSP）

## Phase 2 — 体验与稳健性

- [x] SQLite 任务元数据  
- [x] 默认不信任 X-Forwarded-For  
- [x] UTC；用户向 README（中/英）  
- [x] 可选 Turnstile 人机验证（可开关，上传门禁）  
- [x] 站点 favicon  
- [ ] 转换前序列列表预览 / 勾选  
- [ ] 合并时序列标题条  
- [ ] 公网强制 `ACCESS_TOKEN` 启动门闩（生产加固）

## Phase 3 — 可扩展

- [ ] 对象存储适配器  
- [ ] 分布式队列适配器  
- [ ] 网关 / Redis 限流  
- [ ] 审计日志（脱敏）

## Phase 4 — 多端（按需）

- [ ] PWA / 桌面壳 / 移动端  

## 非目标

医疗器械注册、完整 PACS、诊断级测量与报告。
