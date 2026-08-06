# 功能规格（与实现对齐）

## 1. 范围

Web + REST API + 转换引擎 + CLI。  
可选访问密码；可选 Turnstile 人机验证（仅上传）；任务元数据 SQLite；上传/输出默认 **24h** 自动清理。

## 2. 用户可见流程

1. 打开站点（若要求：访问密码 → 人机验证）  
2. 上传压缩包（zip/rar 等）——与转换分离，同一 `upload_id` 可多次转换  
3. 参数：格式 MP4|GIF、清晰度、是否合并、帧率  
4. 转换：上传进度与转换进度分离  
5. 预览（当前格式）+ 下载（单文件 / zip / merged）

## 3. 参数

```text
ConvertParams / JobStartRequest:
  format: "mp4" | "gif"           # 默认 mp4
  quality: "low" | "medium" | "high"  # 默认 high
  merge: bool                     # 默认 false
  fps: int                        # 默认 10，1–30
```

`ConvertParams.deidentify` 仅引擎/模型层默认 true（日志侧）；**HTTP 创建任务接口不暴露该字段**。

### 质量语义

| quality | MP4 | GIF |
|---------|-----|-----|
| low | 缩小 + 高压缩 | 边长/帧数紧上限 |
| medium | 平衡 | 中等上限 |
| high | 原分辨率优先 | 仍有边长/帧数硬上限 |

GIF 始终有硬上限；会诊优先 MP4。

## 4. 状态

**任务 status（API 顶层）**：`PENDING` | `RUNNING` | `SUCCEEDED` | `FAILED`

**progress.phase**：`PENDING` | `EXTRACTING` | `DISCOVERING` | `CONVERTING` | `PACKAGING` | `SUCCEEDED` | `FAILED`

### error / 安全相关 code（稳定字符串）

| code | 含义 |
|------|------|
| `INVALID_ARCHIVE` | 无法解压或不支持 |
| `ARCHIVE_BOMB` | 超出解压限制 |
| `NO_DICOM` | 未发现有效图像 |
| `CONVERT_ERROR` | 编码失败 |
| `UPLOAD_TOO_LARGE` | 上传超限 |
| `AUTH_REQUIRED` | 需要访问密码 |
| `RATE_LIMITED` / `UPLOAD_RATE_LIMITED` | 限流 |
| `CAPTCHA_REQUIRED` / `CAPTCHA_FAILED` / `CAPTCHA_MISCONFIGURED` / `CAPTCHA_UNAVAILABLE` | 人机验证 |
| `INTERRUPTED` | 服务重启中断任务 |
| `INTERNAL` | 未知错误 |

## 5. HTTP API（`/api/v1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/bootstrap` | 公开配置：`auth_required`、`captcha_enabled`、`captcha_site_key`、`job_ttl_hours` 等 |
| POST | `/uploads` | multipart `file`；可选 `cf-turnstile-response` |
| POST | `/jobs` | JSON：`upload_id` + 转换参数 → 202 `{ job_id, status }` |
| GET | `/jobs/{id}` | 状态、进度、result、error |
| GET | `/jobs/{id}/download` | 主交付文件（仅 SUCCEEDED） |
| GET | `/jobs/{id}/files/{name}` | inline 预览 |
| GET | `/health` 与根路径 `/health` | 探活，无鉴权 |

## 6. CLI

```bash
dicomflow convert -i ./study.zip -o ./out --format mp4 --quality high
dicomflow convert -i ./study.zip -o ./out --format gif --merge
dicomflow serve --host 127.0.0.1 --port 8765
```

## 7. 输出命名

- 序列：`{SeriesNumber:03d}_{safe(SeriesDescription)}.{ext}`（避免仅按描述命名导致覆盖）  
- 多序列未合并：另有 `result.zip`  
- 合并：`merged.{ext}`

## 8. 限制默认（`Settings`，可环境变量覆盖）

| 项 | 默认 |
|----|------|
| 上传最大 | 1 GiB |
| 解压后总大小 | 4 GiB |
| 解压文件数 | 100_000 |
| 压缩比 | 100 |
| 任务 TTL | 24 h |

## 9. 验收要点

- 多序列 zip/rar → 多 mp4 或 zip；`--merge` → 单文件  
- 同名 SeriesDescription 不互相覆盖  
- GIF high 体积可控  
- 无扩展名 DICOM 可发现  
- 损坏包 / 鉴权 / captcha 有可读错误  
- 默认监听 127.0.0.1；CLI convert 可不启 HTTP  
