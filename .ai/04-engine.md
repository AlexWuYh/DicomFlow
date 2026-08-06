# 转换引擎契约

## 1. 入口

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
) -> ConvertResult: ...
```

`ConvertResult`：最终交付路径列表、各序列产物、序列元数据。

## 2. 流水线

1. **normalize_input** — 安全解压归档或使用目录  
2. **discover_dicoms** — rglob；`.dcm` 大小写；无后缀 `dcmread(force=True)`；需可读 `pixel_array`  
3. **group_series** — key = `SeriesInstanceUID`  
4. **sort_instances** — InstanceNumber → IPP Z → 文件名  
5. **render_frames**（流式）— rescale、窗位（tag → 文件名 `W{ww}L{wc}` → min-max）、MONOCHROME1、灰度→RGB、偶数边 pad、按 quality 缩放  
6. **encode** — mp4: libx264 yuv420p；gif: 调色板 + 帧/边长上限  
7. **merge or package** — merge：ffmpeg concat（序列间短黑场）；否则多序列 zip  

## 3. 命名与分组（重要）

- 分组必须用 **SeriesInstanceUID**，不能只用 SeriesDescription。  
- 输出文件名带 **SeriesNumber 前缀**，避免同描述序列互相覆盖。

## 4. ProgressEvent

```text
phase: EXTRACTING | DISCOVERING | CONVERTING | PACKAGING | ...
percent: 0-100
message, series_index/total, frame_index/total
```

## 5. 测试与性能（参考）

- 夹具：合成多帧序列、双序列 merge/zip、恶意 zip 路径  
- 预算（本机参考）：100 帧 512² 约 &lt;30s；流式避免整序列帧常驻内存  
