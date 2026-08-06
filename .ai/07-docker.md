# 容器部署注意点

用户启动说明以根目录 README 与 `docker-compose.yml` 为准。本文只记 AI 实现/排障时易漏点。

## 要点

| 项 | 说明 |
|----|------|
| 启动 | **默认只拉镜像、不 build**：`docker compose pull && docker compose up -d`（无需 Dockerfile） |
| 本地构建 | 完整仓库下：`docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build` |
| 开发挂载 | `docker-compose.dev.yml`（`./web`、`./input`） |
| **GHCR** | 默认 `ghcr.io/alexwuyh/dicomflow:latest`；`DICOMFLOW_IMAGE` 可覆盖；拉不动时是网络问题，不是缺 Dockerfile |
| 数据卷 | `dicomflow-data` → `/data`（含 db / uploads / outputs） |
| 可选挂载 | `./input` → `/input:ro` 便于容器内 CLI 测压缩包 |
| 并发 | `DICOMFLOW_WORKERS=1` 默认，大 CT 勿盲目加并发 |
| 内存 | 完整 CT 建议容器 ≥4GB |
| RAR | 镜像含 unrar-free / 7z；arm64 可能无官方 unrar，样例包已用 free 验证 |
| 公网 | 务必令牌 / captcha / HTTPS；见 [09-security.md](./09-security.md) |

## 容器内 CLI 示例

```bash
docker compose exec dicomflow \
  dicomflow convert -i /input/sample.zip -o /data/outputs/smoke \
  --format mp4 --quality medium
```

勿把真实患者档案提交进 git 或 CI。
