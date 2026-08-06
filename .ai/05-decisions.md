# 关键决策记录（摘要）

## ADR-001：本地优先

个人使用 + 医疗源文件 → 默认本机 Web 与本地磁盘，不强制 Redis/S3/账号。

## ADR-002：合并 = 多输出合成单文件

`merge=true`：拼接为单个 mp4/gif，序列间黑场；默认 `false` 按序列分文件（多个则 zip）。

## ADR-003：引擎与 API 分离

`engine` 无 Web 依赖；禁止在路由写窗位/DICOM 细节。

## ADR-004：质量默认 high

消费端是接诊医生 → 默认 `high`，另提供 low/medium 控体积。

## ADR-005：MVP 不做重前端 / App

静态页 + FastAPI；App/PWA 仅在路线图后期按需。

## ADR-006：进程内队列 + SQLite 元数据

单用户默认 `InProcessQueue`；任务/上传元数据用 **SQLite** 持久化。  
进程重启：未完成任务标 `INTERRUPTED`/`FAILED`，磁盘孤儿靠 TTL 清理。

## ADR-007：GIF 强制上限

全层高分辨率 GIF 不可用 → 按档限制边长与帧数；会诊优先 MP4。

## ADR-008：访问密码与 Turnstile 均可独立开关

公网可叠加 `ACCESS_TOKEN` 与 Turnstile；本地可全关。secret 用 `TURNSTILE_SECRET`，不入库。
