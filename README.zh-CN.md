# DicomFlow

[English](./README.md) | **简体中文**

把医院导出的 DICOM 压缩包（**zip / rar**）转成 **MP4 / GIF**，用手机或电脑自带播放器就能看，方便跨院会诊传阅。

## 用户怎么用（网站）

1. 打开站点（本地默认 http://127.0.0.1:8765 ）
2. 上传医院给的压缩包
3. 选择格式（MP4/GIF）、清晰度，可选「合并成一个文件」
4. 开始转换 → 预览 → 下载
5. **结果默认只保留 24 小时**，请及时保存

若站点要求访问密码，向部署方索取即可（与安装配置无关的使用方式）。

## 快速开始（Docker）

### Docker Compose（默认使用 GHCR `latest`）

**使用 GHCR 时不需要 Dockerfile**，只要本机有 Docker，且能访问 `ghcr.io`。

| 标签 | 镜像 |
|------|------|
| 最新（compose 默认） | `ghcr.io/alexwuyh/dicomflow:latest` |
| 固定版本 | `ghcr.io/alexwuyh/dicomflow:0.1.0` |
| 包页面 | https://github.com/AlexWuYh/DicomFlow/pkgs/container/dicomflow |

```bash
# 拉取并启动（不需要源码目录 / Dockerfile）
docker compose pull
docker compose up -d
# 打开 http://127.0.0.1:8765

# 固定版本
DICOMFLOW_IMAGE=ghcr.io/alexwuyh/dicomflow:0.1.0 docker compose up -d
```

若出现 `ghcr.io` **超时**，先解决网络/代理/镜像加速；默认 **不会** 自动本地编译。只有完整 clone 仓库后才可：

```bash
# 需要 Dockerfile + src + web
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

开发挂载（热更新 `web/`、`./input`）：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

```bash
# 直接 docker run
docker pull ghcr.io/alexwuyh/dicomflow:latest
docker run -d --name dicomflow \
  -p 8765:8765 \
  -v dicomflow-data:/data \
  -e DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)" \
  ghcr.io/alexwuyh/dicomflow:latest
```

若包为私有，先登录：

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
```

公开仓库可在 GitHub → Packages → `dicomflow` → Package settings 将可见性设为 **Public**。

公网部署前请设置访问密码（令牌）：

```bash
export DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)"
docker compose up -d
```

可选人机验证（Cloudflare Turnstile），与访问密码相互独立：

```bash
export DICOMFLOW_CAPTCHA_ENABLED=true
export DICOMFLOW_TURNSTILE_SITE_KEY="你的 site key"
export TURNSTILE_SECRET="你的 secret"   # 勿写入仓库
```

公网部署请设置强 `DICOMFLOW_ACCESS_TOKEN`、使用 HTTPS，并保持 `DICOMFLOW_ENABLE_DOCS=false`。可选人机验证见下方配置表。

## 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# CLI
dicomflow convert -i ./study.zip -o ./out --format mp4 --quality high
dicomflow serve   # http://127.0.0.1:8765

# 测试
pytest -q
```

macOS 解压 rar 可安装：`brew install unar`

## 仓库结构

```
src/dicomflow/    # API、引擎、任务、存储
web/              # 前端静态页
tests/
Dockerfile
docker-compose.yml
```

运行时数据（gitignore）：`data/`（含 `dicomflow.db`、uploads、outputs）

## 配置（常用）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DICOMFLOW_DATA_DIR` | `./data` | 数据根目录 |
| `DICOMFLOW_HOST` / `PORT` | `127.0.0.1` / `8765` | 监听 |
| `DICOMFLOW_ACCESS_TOKEN` | 空 | 公网建议必设（访问密码，可开关） |
| `DICOMFLOW_CAPTCHA_ENABLED` | `false` | 人机验证开关（Cloudflare Turnstile） |
| `DICOMFLOW_TURNSTILE_SITE_KEY` | 空 | 开启 captcha 时必填（公开 site key） |
| `TURNSTILE_SECRET` | 空 | 开启 captcha 时必填（服务端 secret，勿提交） |
| `DICOMFLOW_ENABLE_DOCS` | `false` | OpenAPI 文档开关 |
| `DICOMFLOW_MAX_UPLOAD_BYTES` | 1 GiB | 上传上限 |
| `DICOMFLOW_JOB_TTL_HOURS` | `24` | 自动清理 |
| `DICOMFLOW_TRUST_X_FORWARDED_FOR` | `false` | 仅可信反代后开启 |
| `DICOMFLOW_ALLOWED_HOSTS` | `*` | 生产改为域名 |

完整示例：[`.env.example`](./.env.example)

本地调试 Turnstile 时，请在 Cloudflare 控制台 Hostname Management 中加入 `localhost` 与 `127.0.0.1`（不要带端口）。

## 许可

[MIT License](./LICENSE)。

非医疗器械，不替代专业阅片工作站，不作诊断依据。
