# MVP 功能规格

## 1. 范围

Web + REST API + 转换引擎 + CLI。  
可选访问密码（`ACCESS_TOKEN`）；任务元数据 SQLite 持久化（`data/dicomflow.db`）。  
上传/输出默认保留 24 小时后自动清理。

## 2. 用户可见流程

1. 打开站点
2. 上传压缩包（zip / rar 等）——与转换分离，可反复转换
3. 设置参数：
   - 输出格式：MP4 | GIF
   - 清晰度：流畅 / 标准 / 高清（默认高清）
   - 合并为单个文件：开关（默认关）
   - 帧率（默认 10）
4. 开始转换 → **上传进度** 与 **转换进度** 分开显示
5. 完成后在线预览（仅当前格式）并下载：
   - 单序列：直接媒体文件
   - 多序列未合并：`result.zip` + 各序列可预览
   - 合并：`merged.mp4` / `merged.gif`

## 3. 参数枚举

```text
ConvertParams:
  format: "mp4" | "gif"          # 默认 mp4
  quality: "low" | "medium" | "high"  # 默认 high
  merge: bool                    # 默认 false
  fps: int                       # 默认 10，范围 1–30
  deidentify: bool               # 默认 true（日志与可选剥离 PHI；像素始终转出）
```

### 质量映射（实现基准）

| quality | MP4 | GIF |
|---------|-----|-----|
| low | scale=0.5, crf≈28, fps min(fps,8) | max_side=256, max_frames=80, colors=64 |
| medium | max_side=1024, crf≈23 | max_side=480, max_frames=120, colors=128 |
| high | 原尺寸（偶数对齐）, crf≈18 | max_side=640, max_frames=150, colors=256 |

实现可用近似参数（imageio quality / Pillow quantize），但**产品档位语义**保持上表。

## 4. 任务状态机

```
PENDING → EXTRACTING → DISCOVERING → CONVERTING → PACKAGING → SUCCEEDED
                 ↘ FAILED
CONVERTING 中可带 meta: { series_index, series_total, frame_index, frame_total, series_name }
任意阶段异常 → FAILED + error_code + message
```

### error_code（稳定字符串，供 UI/AI 判断）

| code | 含义 |
|------|------|
| `INVALID_ARCHIVE` | 无法解压或不支持的格式 |
| `ARCHIVE_BOMB` | 超出解压限制 |
| `NO_DICOM` | 未发现有效图像 DICOM |
| `CONVERT_ERROR` | 编码失败 |
| `UPLOAD_TOO_LARGE` | 上传超过大小限制 |
| `AUTH_REQUIRED` | 需要访问密码 |
| `RATE_LIMITED` / `UPLOAD_RATE_LIMITED` | 请求/上传过于频繁 |
| `INTERRUPTED` | 服务重启导致任务中断 |
| `INTERNAL` | 未知错误 |

## 5. HTTP API（v1）

Base: `/api/v1`

### 5.0 上传（与转换分离）

`POST /uploads`

- `Content-Type: multipart/form-data`
- 字段：`file`（压缩包）

响应 `201`:

```json
{
  "upload_id": "uuid",
  "filename": "C252708.rar",
  "size_bytes": 318750568
}
```

同一 `upload_id` 可多次发起转换，无需重新上传。

### 5.1 开始转换

`POST /jobs`

- `Content-Type: application/json`

```json
{
  "upload_id": "uuid",
  "format": "mp4",
  "quality": "high",
  "merge": false,
  "fps": 10
}
```

响应 `202`:

```json
{
  "job_id": "uuid",
  "status": "PENDING"
}
```

### 5.2 查询任务

`GET /jobs/{job_id}`

```json
{
  "job_id": "uuid",
  "status": "CONVERTING",
  "progress": {
    "phase": "CONVERTING",
    "percent": 42,
    "message": "序列 2/5: Bone 1.25mm",
    "series_index": 2,
    "series_total": 5
  },
  "result": null,
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

成功时 `result`:

```json
{
  "download_name": "merged.mp4",
  "content_type": "video/mp4",
  "size_bytes": 12345678,
  "outputs": [
    {"name": "merged.mp4", "kind": "merged"}
  ]
}
```

### 5.3 下载主文件

`GET /jobs/{job_id}/download`  
仅 `SUCCEEDED`；返回主交付文件（合并文件 / 单序列 / zip）。

### 5.4 预览单文件

`GET /jobs/{job_id}/files/{filename}`  
`Content-Disposition: inline`，供页面 video/img 预览。

### 5.5 健康检查

`GET /health` → `{ "status": "ok" }`

## 6. CLI（并行入口）

```bash
# 目录输入（兼容旧习惯）
dicomflow convert -i ./dicom_dir -o ./out --format mp4 --quality high

# 压缩包输入
dicomflow convert -i ./study.zip -o ./out --format gif --merge

# 启动本地 Web
dicomflow serve --host 127.0.0.1 --port 8765
```

## 7. 输出命名

- 单序列：`{SeriesNumber:03d}_{safe(SeriesDescription)}.{ext}`
- 多序列未合并：同上 + `result.zip`
- 合并：`merged.{ext}`
- `safe()`：非字母数字改为 `_`，截断长度，避免空名时用 UID 前 12 位

## 8. 解压限制（默认，可配置）

| 项 | 默认 |
|----|------|
| 上传包最大 | 2 GiB |
| 解压后总大小 | 8 GiB |
| 单文件最大 | 512 MiB |
| 文件数量 | 200_000 |
| 压缩比（zip bomb） | 解压/压缩 > 100 且解压>1GiB 拒绝 |

## 9. 验收清单

- [ ] zip 内多序列 CT → 多个 mp4 或一个 zip
- [ ] `--merge` → 单个 mp4，段落可辨
- [ ] gif + high 体积可控（有上限）
- [ ] 无扩展名 DICOM 可发现
- [ ] 损坏包 → `INVALID_ARCHIVE`，Web 有可读错误
- [ ] 仅监听 127.0.0.1
- [ ] `dicomflow convert` 不启动 HTTP 也能用
