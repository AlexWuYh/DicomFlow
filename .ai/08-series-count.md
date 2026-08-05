# 序列数量：旧脚本 vs 新引擎

## 结论

**新引擎（Web / `dicomflow convert`）按 `SeriesInstanceUID` 输出、文件名带序列号前缀，结果更正确。**

旧脚本 `dicom_convert.py` 会在**同名 SeriesDescription** 时互相覆盖，磁盘上看到的 MP4 更少。

## 实测：`input/C252708.rar`

| 项 | 旧脚本逻辑 | 新引擎 |
|----|------------|--------|
| 发现 DICOM 图像 | 1284 | 1284 |
| 独立序列 UID | **17** | **17** |
| 最终不冲突的输出文件名 | **≈10**（覆盖后） | **17**（+ 可选 merged/zip） |

### 旧脚本覆盖原因

命名只用 `SeriesDescription`：

```python
out_file = output_dir / f"{safe_name}.mp4"
```

本样例冲突：

| 输出文件名 | 实际序列数 | 结果 |
|------------|------------|------|
| `1_25mm_bone.mp4` | 2 | 只剩最后写入的一条 |
| `Processed_Images.mp4` | 7 | 只剩最后写入的一条 |

→ 17 个序列写完后磁盘上约 **10 个** mp4，**不是**少发现了序列，而是**后写覆盖了先写**。

### 新引擎命名

`{SeriesNumber:03d}_{safe(SeriesDescription)}.mp4`  
例如 `010_1_25mm_bone.mp4` 与 `011_1_25mm_bone.mp4` 并存。

合并开启时还会多一个 `merged.mp4`，以及各序列文件（便于预览），主下载为 `merged.mp4`。

## 产品建议

- 默认以新引擎为准。
- 若用户只想「原始薄层/诊断相关序列」，可后续加：排除 `LOCALIZER` / `SCREEN SAVE` / 可选勾选序列（非本次 bug）。
