# 架构设计（本地优先 · 可扩展）

## 1. 原则

1. **本地优先**：默认无 Redis/S3/账号；数据在本机 `data/`。  
2. **内核纯净**：`engine` 不依赖 Web 框架；CLI / API / 未来 Worker 共用。  
3. **端口可替换**：Storage / Queue 可换适配器。  
4. **默认同进程任务**：`InProcessQueue`；扩展可换 Celery/RQ。

## 2. 逻辑架构

```
Clients (Web)
    │ HTTP
API (FastAPI)  ── 上传 / 任务 / 下载 / bootstrap / health
    │
JobService ── StoragePort ── LocalFilesystem
           └── QueuePort   ── InProcessQueue
           └── JobStore    ── SQLite (data/dicomflow.db)
    │
Engine: archive → discover → window → encode → merge/zip
```

## 3. 仓库结构（要点）

```
.ai/                 # 本目录：规格（AI）
src/dicomflow/
  core/              # 配置、模型、异常
  engine/            # 转换内核
  storage/           # StoragePort + Local
  tasks/             # Queue、JobService、JobStore、cleanup
  api/               # 路由、安全、captcha
web/                 # 静态前端
tests/
data/                # 运行时（gitignore）：db / uploads / work / outputs
```

## 4. 扩展点

| Port | 当前 | 未来 |
|------|------|------|
| Storage | 本地目录分 job | S3/MinIO + 预签名 |
| Queue | 进程内线程池（默认 workers=1） | Celery/RQ |
| JobStore | SQLite：uploads + jobs | 可换 PG |
| Auth | 可选访问令牌 + 可选 Turnstile | 完整账号体系（非目标） |

重启时：仍为 PENDING/RUNNING 的任务标为 FAILED（`INTERRUPTED`）。

## 5. 任务数据流

```
POST /api/v1/uploads          → 落盘 + SQLite（可要 captcha）
POST /api/v1/jobs             → 建任务 + 入队
GET  /api/v1/jobs/{id}        → 状态与进度
GET  /api/v1/jobs/{id}/download | /files/{name}
GET  /api/v1/bootstrap        → 前端公开配置（无 secret）
GET  /health                  → 探活（无鉴权）

Worker: extract → discover → convert → merge|zip → 更新 SQLite
```

## 6. 部署形态

| 形态 | 组件 |
|------|------|
| 本地 / Docker（当前） | FastAPI + 静态 Web + InProcess + Local FS + SQLite |
| 私有化小服务 | + HTTPS 反代 + 强令牌 / captcha |
| 云端（未来） | + 对象存储 + 分布式队列 + 网关限流 |

从本地到云端应**只加适配器与配置**，不改 engine 语义。

## 7. 技术栈（当前）

| 层 | 选择 |
|----|------|
| 语言 | Python ≥3.11 |
| API | FastAPI |
| 引擎 | pydicom + numpy + imageio / Pillow；合并用 ffmpeg |
| 元数据 | SQLite |
| 前端 | 原生 HTML/JS |
| 打包 | pyproject.toml |

**刻意不引入（现阶段）**：Redis、Celery、PostgreSQL、重型前端框架、K8s。

## 8. 安全底线（详见 09-security）

- 解压防 Zip Slip / 体积与文件数限制  
- IO 限制在 `data/` 任务目录  
- 默认绑定 `127.0.0.1`；公网需令牌/HTTPS/限流  
- 可选 Turnstile 保护上传  
