# Docker 部署说明

## 启动

```bash
# Docker Desktop / Docker Engine
docker compose up -d --build

# 或 Podman
podman machine start   # macOS 如需要
podman compose up -d --build
# 等价: podman build -t dicomflow:local . && podman run ...
```

打开：http://127.0.0.1:8765

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DICOMFLOW_HOST` | `0.0.0.0`（镜像内） | 监听地址 |
| `DICOMFLOW_PORT` | `8765` | 端口 |
| `DICOMFLOW_DATA_DIR` | `/data` | 上传/工作/输出 |
| `DICOMFLOW_WEB_DIR` | `/app/web` | 静态前端 |
| `DICOMFLOW_WORKERS` | `1` | 并发转换任务数 |

## 卷

- `dicomflow-data` → `/data`：任务持久化
- `./input` → `/input:ro`：本地测试压缩包（可选）

## 验证过的真实样例

- 文件：`input/C252708.rar`（约 304MB，RAR5，1284 帧，17 序列）
- 容器内 CLI：

```bash
docker compose exec dicomflow \
  dicomflow convert -i /input/C252708.rar -o /data/outputs/real_ct \
  --format mp4 --quality medium
```

结果：每序列一个 MP4 + `result.zip`（约 14MB，medium 档）。

## 注意

1. **RAR**：镜像含 `unrar-free` / `7z`；arm64 可能无官方 unrar，以 free 版为主（本样例已验证可解）。
2. **内存**：完整 CT 建议容器 ≥4GB。
3. **大文件上传**：Web 用 XHR 显示上传进度；304MB 级上传取决于本机磁盘与网络（本机回环通常可接受）。
4. 本机无 Docker Desktop 时可用 Podman；`docker` 软链若指向已卸载的 Docker.app 会失效。
