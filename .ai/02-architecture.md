# 架构设计（本地优先 · 可扩展）

## 1. 设计原则

1. **本地优先**：默认无外部依赖（无 Redis/S3/账号）；数据落在本机工作目录。
2. **内核纯净**：`engine` 零 Web 框架依赖，CLI / API / 未来 Worker 共用。
3. **端口可替换**：存储、任务队列、鉴权通过接口注入，云端扩展时只换适配器。
4. **同步可跑、异步可挂**：个人本机可用进程内后台任务；扩展时换 Celery/RQ。

## 2. 逻辑架构

```
┌──────────────────────────────────────────────────────────┐
│  Clients（当前：本地 Web；未来：App / 桌面壳）              │
└────────────────────────────┬─────────────────────────────┘
                             │ HTTP
┌────────────────────────────▼─────────────────────────────┐
│  API Layer  (FastAPI)                                     │
│  - 任务创建 / 查询 / 下载 / 健康检查                        │
│  - 不写 DICOM 细节                                        │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│  Application Services                                     │
│  - JobService: 编排上传→解压→转换→打包→清理               │
│  - 依赖: StoragePort, QueuePort, Engine                   │
└──────────────┬─────────────────────────────┬──────────────┘
               │                             │
     ┌─────────▼─────────┐         ┌─────────▼─────────┐
     │  StoragePort      │         │  QueuePort        │
     │  LocalFilesystem  │         │  InProcessQueue   │
     │  (S3/OSS 未来)    │         │  (Celery 未来)    │
     └─────────┬─────────┘         └─────────┬─────────┘
               │                             │
               └──────────────┬──────────────┘
                              ▼
               ┌──────────────────────────────┐
               │  Engine (纯函数/类库)          │
               │  archive → discover → window  │
               │  → encode mp4/gif → merge     │
               └──────────────────────────────┘
```

## 3. 目录结构（仓库）

```
DicomFlow/
├── .ai/                    # AI/人类共享的设计文档（本目录）
├── src/dicomflow/
│   ├── core/               # 配置、模型、异常
│   ├── engine/             # 转换内核（无 FastAPI）
│   ├── storage/            # StoragePort + Local 实现
│   ├── tasks/              # QueuePort + InProcess + JobStore(SQLite) + cleanup
│   └── api/                # FastAPI 路由、安全中间件、依赖注入
├── web/                    # 静态前端
├── tests/
├── scripts/
├── data/                   # 运行时目录（gitignore）
│   ├── dicomflow.db        # 上传/任务元数据
│   ├── uploads/
│   ├── work/
│   └── outputs/
├── pyproject.toml
└── README.md
```

## 4. 扩展点（Ports）

### 4.1 StoragePort

```text
save_upload(stream, job_id) -> path_or_key
open_read(key) -> BinaryIO
publish_output(local_path, job_id) -> download_ref
delete_job_files(job_id) -> None
```

- **LocalFilesystemStorage**：`data/` 下分 job 目录。
- **未来 ObjectStorage**：预签名上传/下载，Worker 拉对象。

### 4.2 QueuePort

```text
enqueue(job_id, runner) -> None
```

- **InProcessQueue**：线程池执行转换（默认 max_workers=1）。
- **未来 CeleryQueue**：同一 JobService 任务体。

### 4.3 JobStore（元数据）

- **SQLite**（`data/dicomflow.db`）：uploads / jobs 持久化。
- 重启时将仍为 PENDING/RUNNING 的任务标为 FAILED（`INTERRUPTED`）。

### 4.4 Auth

- 可选 `DICOMFLOW_ACCESS_TOKEN`（请求头 `X-DicomFlow-Token`）。
- OpenAPI 默认关闭。

## 5. 任务数据流

```
POST /api/v1/uploads  → 落盘 uploads/{upload_id}/ + SQLite
POST /api/v1/jobs     → SQLite 建任务 + 队列转换
GET  /api/v1/jobs/{id}
GET  /api/v1/jobs/{id}/download | /files/{name}

Worker:
  1. extract → work/{job_id}/raw/
  2. discover series
  3. convert each series → outputs
  4. merge 或 zip
  5. 更新 SQLite 状态 + 产物列表
```

## 6. 部署形态

| 形态 | 适用 | 组件 |
|------|------|------|
| **A. 本地单机（当前）** | 个人 | FastAPI + 静态 Web + InProcess + Local FS |
| B. 本地 Docker | 换机一致性 | 同 A，打包 ffmpeg/unrar 依赖 |
| C. 私有化小服务 | 家庭 NAS / 小团队 | + SQLite/PG + 反向代理 HTTPS |
| D. 云端 SaaS | 未来 | + S3 + Celery + Auth + 清理策略 |

从 A→D 应只增加适配器与配置，**不改 engine 业务语义**。

## 7. 技术栈（锁定 MVP）

| 层 | 选择 | 理由 |
|----|------|------|
| 语言 | Python 3.11+ | 复用现有脚本 |
| API | FastAPI | 轻、异步、OpenAPI |
| 引擎 | pydicom + numpy + imageio/Pillow | 现有栈 |
| 合并 | ffmpeg concat（imageio-ffmpeg 自带二进制优先） | 可靠拼接 |
| 元数据 | 内存 + 可选 SQLite | 个人足够 |
| 前端 | 原生 HTML/JS 或极简静态页 | 降低并行成本 |
| 打包 | pyproject.toml (hatch/uv) | 标准 |

**刻意不引入（MVP）**：Redis、Celery、PostgreSQL、React、Flutter、K8s。

## 8. 安全（个人本地仍要做）

- 解压：防 Zip Slip、限制解压后体积与文件数。
- 路径：所有 IO 限制在 `data/{job_id}/` 下。
- 日志：默认脱敏 PatientName/PatientID。
- 不监听公网：默认 `127.0.0.1`。

## 9. CLI 入口

- 正式入口：`dicomflow convert` / `dicomflow serve`（包内 `cli.py`）。
- 早期独立脚本已移除；逻辑在 `engine/`。
