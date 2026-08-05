# DicomFlow

把医院导出的 DICOM 压缩包（zip / rar）转成 **MP4 / GIF**，用手机或电脑自带播放器就能看，方便跨院会诊传阅。

> 设计与规格文档：[`.ai/00-index.md`](.ai/00-index.md)

## 用户怎么用（网站）

1. 打开站点（本地默认 http://127.0.0.1:8765 ）
2. 上传医院给的压缩包
3. 选择格式（MP4/GIF）、清晰度，可选「合并成一个文件」
4. 开始转换 → 预览 → 下载  
5. **结果默认只保留 24 小时**，请及时保存

若站点要求访问密码，向部署方索取即可（与安装配置无关的使用方式）。

## 快速开始（Docker）

```bash
docker compose up -d --build
open http://127.0.0.1:8765
```

公网部署前请设置访问密码（令牌）：

```bash
export DICOMFLOW_ACCESS_TOKEN="$(openssl rand -hex 32)"
docker compose up -d --build
```

更多安全项见 [`.ai/09-security.md`](.ai/09-security.md)。

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
.ai/              # 产品 / 架构 / 安全规格
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
| `DICOMFLOW_MAX_UPLOAD_BYTES` | 1GiB | 上传上限 |
| `DICOMFLOW_JOB_TTL_HOURS` | `24` | 自动清理 |
| `DICOMFLOW_TRUST_X_FORWARDED_FOR` | `false` | 仅可信反代后开启 |
| `DICOMFLOW_ALLOWED_HOSTS` | `*` | 生产改为域名 |

完整示例：`.env.example`

## 许可

[MIT License](./LICENSE)。  

非医疗器械，不替代专业阅片工作站，不作诊断依据。
