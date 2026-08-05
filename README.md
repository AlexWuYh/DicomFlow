# DicomFlow

本地优先的 DICOM 压缩包 → MP4 / GIF 转换工具。  
把 A 医院导出的源文件转成医生用普通播放器就能看的片子，便于跨院会诊传阅。

> 设计文档（供 AI / 开发阅读）：[`.ai/00-index.md`](.ai/00-index.md)

## 特性（MVP 目标）

- 上传 / 选择 zip 等压缩包（本地）
- 输出 **MP4** 或 **GIF**
- **质量档位**（默认高清，面向医生查阅）
- **合并开关**：多个序列合并为单个文件，或分别输出并打包 zip
- 架构预留云端扩展（Storage / Queue 端口），当前默认本机单进程

## 快速开始（Docker 推荐）

```bash
# 构建并启动 Web
docker compose up -d --build

# 浏览器打开
open http://127.0.0.1:8765

# 查看日志（转换进度）
docker compose logs -f dicomflow

# 停止
docker compose down
```

数据目录挂载在 Docker volume `dicomflow-data`（容器内 `/data`）。  
本地测试包可放在 `./input/`（compose 已只读挂载为 `/input`）。

容器内直接转真实样例（可选）：

```bash
docker compose exec dicomflow \
  dicomflow convert -i /input/C252708.rar -o /data/outputs/manual --format mp4 --quality medium
```

## 本地开发（不用 Docker）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# macOS 解压 rar 需要: brew install unar
dicomflow convert -i ./input/C252708.rar -o ./out --format mp4 --quality medium
dicomflow serve   # http://127.0.0.1:8765
```

兼容旧入口：`python dicom_convert.py -i ./input -o ./output -f mp4`

## 仓库结构

```
.ai/                 # 产品与架构文档（AI 可读）
src/dicomflow/       # 应用与转换引擎
web/                 # 本地 Web 静态页
tests/
data/                # 运行时目录（gitignore）
dicom_convert.py     # 原始 CLI 脚本（过渡保留）
```

## 配置

环境变量见 `.env.example` 与 `dicomflow.core.config`。常用项：

| 变量 | 默认 | 说明 |
|------|------|------|
| `DICOMFLOW_DATA_DIR` | `./data` | 上传/工作/输出根目录 |
| `DICOMFLOW_HOST` | `127.0.0.1` | 服务绑定 |
| `DICOMFLOW_PORT` | `8765` | 端口 |
| `DICOMFLOW_ACCESS_TOKEN` | _(空)_ | **公网必设**；前端会提示输入 |
| `DICOMFLOW_ENABLE_DOCS` | `false` | 是否开放 `/docs`（公网保持 false） |
| `DICOMFLOW_MAX_UPLOAD_BYTES` | `1GiB` | 上传大小上限 |
| `DICOMFLOW_RATE_LIMIT_RPM` | `60` | 每 IP 每分钟请求上限 |
| `DICOMFLOW_JOB_TTL_HOURS` | `24` | 上传/转换结果自动清理时间 |
| `DICOMFLOW_CLEANUP_INTERVAL_SECONDS` | `900` | 清理任务扫描间隔 |

### 公网部署注意

1. 设置长随机 `DICOMFLOW_ACCESS_TOKEN`
2. 前置 HTTPS 反代
3. 配置 `DICOMFLOW_ALLOWED_HOSTS=你的域名`
4. 医疗数据敏感：优先内网；公网需尽快清理 `/data`
5. 详见 [`.ai/09-security.md`](.ai/09-security.md)

## 许可

MIT（个人工具；非医疗器械，不替代专业诊断工作站。）
