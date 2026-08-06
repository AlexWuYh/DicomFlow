# DicomFlow — AI 文档索引

本目录供 AI / 代理阅读的设计与开发规格。**实现代码不在此目录。**  
用户向说明见仓库根目录 `README.md` / `README.zh-CN.md`（勿把分支规范写进 README）。

| 文档 | 用途 |
|------|------|
| [01-product.md](./01-product.md) | 产品定位、场景、需求边界 |
| [02-architecture.md](./02-architecture.md) | 分层、扩展点、部署形态 |
| [03-mvp-spec.md](./03-mvp-spec.md) | 功能规格、API、状态机、参数 |
| [04-engine.md](./04-engine.md) | 转换引擎契约与流水线 |
| [05-decisions.md](./05-decisions.md) | 关键决策（ADR 摘要） |
| [06-roadmap.md](./06-roadmap.md) | 分阶段路线图（里程碑对照） |
| [07-docker.md](./07-docker.md) | 容器部署注意点（补 README） |
| [09-security.md](./09-security.md) | 安全默认、鉴权/captcha、公网清单 |
| [11-development.md](./11-development.md) | 里程碑模式、分支、CI/Release |

## 一句话定义

**本地优先的 DICOM 压缩包 → 医生可读媒体（MP4 / GIF）转换工具。**  
A 院源文件转换后，供 B/C/D 院接诊医生用普通播放器查阅。

## 已确认约束

1. **合并**：可选将多序列输出合成**单个**媒体文件。  
2. **部署**：个人/本地优先；架构预留云端扩展。  
3. **用户**：消费端是接诊医生，非诊断工作站、非家属娱乐预览。  
4. **开发**：见 [11-development.md](./11-development.md)（`dev` 集成、`main` 发布、里程碑驱动）。
