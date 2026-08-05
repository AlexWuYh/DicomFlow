# 转换引擎契约

## 1. 公共入口

```python
def convert_dicom_package(
    input_path: Path,          # 压缩包或已解压目录
    output_dir: Path,
    *,
    format: Literal["mp4", "gif"] = "mp4",
    quality: Literal["low", "medium", "high"] = "high",
    merge: bool = False,
    fps: int = 10,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
) -> ConvertResult:
    ...
```

`ConvertResult`:

```text
output_files: list[Path]   # 最终交付文件（单个媒体或 zip）
series_outputs: list[Path] # 各序列原始产物（合并前）
series_meta: list[SeriesInfo]
```

## 2. 流水线步骤

1. **normalize_input**  
   - 若是归档：安全解压到 workdir  
   - 若是目录：直接使用
2. **discover_dicoms**  
   - rglob 文件  
   - 后缀 `.dcm`（任意大小写）或无后缀时 `dcmread(force=True)` 探测  
   - 必须有可读取的 `pixel_array`
3. **group_series**  
   - key = `SeriesInstanceUID`  
   - 附加 Study/Series 元数据用于排序与命名
4. **sort_instances**  
   - InstanceNumber → IPP Z → 文件名
5. **render_frames**（流式）  
   - rescale（Slope/Intercept，若有）  
   - window（tag → 文件名 W/L → min-max）  
   - MONOCHROME1 反色  
   - 灰度→RGB  
   - 偶数宽高 pad（H.264）  
   - 按 quality 缩放
6. **encode**  
   - mp4: libx264 yuv420p  
   - gif: 调色板 + 抽帧上限
7. **merge or package**  
   - merge=true: ffmpeg concat（序列间黑场 0.5s）  
   - merge=false && len>1: zip  
   - 单文件：直接作为 download

## 3. 从旧脚本继承的行为

| 行为 | 来源 | 处理 |
|------|------|------|
| 文件名窗位 `W2000L600` | `dicom_convert.py` | 保留 |
| 偶数维度 pad | 同上 | 保留 |
| `force=True` 读取 | 同上 | 保留 |
| 全帧列表内存 | 同上 | **改为流式** writer.append |
| 仅 `.DCM` 后缀 | 同上 | **扩展**无后缀探测 |
| 自动 pip install | 同上 | **删除**（依赖 pyproject） |

## 4. ProgressEvent

```text
phase: EXTRACTING | DISCOVERING | CONVERTING | PACKAGING
percent: 0-100
message: str
series_index: int | None
series_total: int | None
frame_index: int | None
frame_total: int | None
```

## 5. 测试夹具建议

- 最小 3 帧假 DICOM 序列（生成器脚本）
- 两序列用于 merge/zip 分支
- 恶意 zip（`../` 路径）应被拒绝

## 6. 性能预算（个人本机参考）

| 规模 | 期望 |
|------|------|
| 1 序列 × 100 帧 512² | < 30s |
| 5 序列 × 200 帧 | < 5 min |
| 内存 | 单 Worker 峰值尽量 < 2–4 GB（流式） |
