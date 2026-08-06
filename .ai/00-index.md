# DicomFlow — AI 文档索引

本目录存放所有供 AI / 开发者阅读的设计与规格文档。实现代码不放在此目录。

| 文档 | 用途 |
|------|------|
| [01-product.md](./01-product.md) | 产品定位、用户场景、需求边界 |
| [02-architecture.md](./02-architecture.md) | 架构分层、扩展点、部署形态 |
| [03-mvp-spec.md](./03-mvp-spec.md) | MVP 功能规格、API、参数枚举、状态机 |
| [04-engine.md](./04-engine.md) | DICOM 转换引擎契约与验收标准 |
| [05-decisions.md](./05-decisions.md) | 关键决策记录（ADR 摘要） |
| [06-roadmap.md](./06-roadmap.md) | 分阶段路线图 |
| [07-docker.md](./07-docker.md) | Docker / Podman 部署与验证记录 |
| [08-series-count.md](./08-series-count.md) | 新旧脚本序列数量差异说明 |
| [09-security.md](./09-security.md) | 公网安全默认项与部署清单 |
| [10-review-report.md](./10-review-report.md) | 全量 Review 报告（代码/文档/安全/运维） |
| [11-development.md](./11-development.md) | 开发规范：里程碑模式、分支（main/dev）、PR 目标、Release 流水线（供 AI 阅读） |

## 一句话产品定义

**本地优先的 DICOM 压缩包 → 医生可读媒体（MP4 / GIF）转换工具。**  
病人从 A 医院拿到源文件，转换后交给 B/C/D 医生用普通播放器/浏览器查阅，无需专业影像软件。

## 当前约束（已确认）

1. **合并**：输出的多个图片/视频可选合并为**单个文件**。
2. **部署**：个人使用、**本地优先**，架构预留云端/多用户扩展。
3. **用户**：服务对象是**接诊医生**（跨院会诊/复诊查阅），不是家属娱乐预览。
