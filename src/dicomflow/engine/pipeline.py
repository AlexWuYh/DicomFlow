from __future__ import annotations

import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dicomflow.core.exceptions import ConvertError, DicomFlowError, NoDicomError
from dicomflow.core.models import ConvertParams, OutputFormat, Quality
from dicomflow.engine.archive import prepare_input
from dicomflow.engine.discover import SeriesGroup, find_dicom_instances, group_series
from dicomflow.engine.encode import concat_gifs, concat_videos, write_gif, write_mp4
from dicomflow.engine.quality import get_profile
from dicomflow.engine.window import apply_window, to_rgb_even


@dataclass
class ProgressEvent:
    phase: str
    percent: int
    message: str = ""
    series_index: int | None = None
    series_total: int | None = None
    frame_index: int | None = None
    frame_total: int | None = None


@dataclass
class ConvertResult:
    output_files: list[Path]
    series_outputs: list[Path] = field(default_factory=list)
    series_names: list[str] = field(default_factory=list)


ProgressCallback = Callable[[ProgressEvent], None]


def _emit(cb: ProgressCallback | None, event: ProgressEvent) -> None:
    if cb:
        cb(event)


def _iter_series_frames(series: SeriesGroup):
    import pydicom

    for inst in series.instances:
        try:
            ds = pydicom.dcmread(str(inst.path), force=True)
            pixel = ds.pixel_array
        except Exception as exc:  # noqa: BLE001
            raise ConvertError(
                f"读取像素失败: {inst.path.name}",
                detail=str(exc),
            ) from exc
        frame = apply_window(pixel, ds, source_path=inst.path)
        yield to_rgb_even(frame)
        # Release large arrays promptly
        del pixel, ds


def convert_dicom_package(
    input_path: Path | str,
    output_dir: Path | str,
    *,
    params: ConvertParams | None = None,
    format: OutputFormat | str | None = None,
    quality: Quality | str | None = None,
    merge: bool | None = None,
    fps: int | None = None,
    work_dir: Path | str | None = None,
    progress_callback: ProgressCallback | None = None,
    max_extract_files: int = 200_000,
    max_extract_bytes: int = 8 * 1024 * 1024 * 1024,
    max_ratio: float = 100.0,
) -> ConvertResult:
    """
    Convert a DICOM directory or archive into MP4/GIF outputs.

    merge=True  → single merged media file
    merge=False → per-series files; if multiple, also zip as primary download
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if params is None:
        params = ConvertParams()
    if format is not None:
        params.format = OutputFormat(format)
    if quality is not None:
        params.quality = Quality(quality)
    if merge is not None:
        params.merge = merge
    if fps is not None:
        params.fps = fps

    profile = get_profile(params.quality)
    effective_fps = params.fps
    if profile.fps_cap is not None:
        effective_fps = min(effective_fps, profile.fps_cap)

    work = Path(work_dir) if work_dir else output_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)

    try:
        _emit(
            progress_callback,
            ProgressEvent(phase="EXTRACTING", percent=5, message="准备输入 / 解压"),
        )
        root = prepare_input(
            input_path,
            work,
            max_files=max_extract_files,
            max_total_bytes=max_extract_bytes,
            max_ratio=max_ratio,
        )

        _emit(
            progress_callback,
            ProgressEvent(phase="DISCOVERING", percent=15, message="扫描 DICOM 序列"),
        )
        instances = find_dicom_instances(root)
        series_list = group_series(instances)
        series_total = len(series_list)

        series_out_dir = work / "series"
        series_out_dir.mkdir(parents=True, exist_ok=True)
        series_outputs: list[Path] = []
        series_names: list[str] = []

        ext = params.format.value
        for s_idx, series in enumerate(series_list, start=1):
            name = series.safe_name
            series_names.append(name)
            out_path = series_out_dir / f"{name}.{ext}"
            frame_total = len(series.instances)
            base_pct = 20 + int(60 * (s_idx - 1) / max(series_total, 1))

            def on_frame(
                fi: int,
                ft: int,
                *,
                _s_idx=s_idx,
                _base=base_pct,
                _name=name,
                _st=series_total,
            ) -> None:
                frac = fi / max(ft, 1)
                pct = _base + int((60 / max(_st, 1)) * frac)
                _emit(
                    progress_callback,
                    ProgressEvent(
                        phase="CONVERTING",
                        percent=min(pct, 85),
                        message=f"序列 {_s_idx}/{_st}: {_name}",
                        series_index=_s_idx,
                        series_total=_st,
                        frame_index=fi,
                        frame_total=ft,
                    ),
                )

            frames = _iter_series_frames(series)
            if params.format == OutputFormat.MP4:
                write_mp4(
                    frames,
                    out_path,
                    fps=effective_fps,
                    profile=profile,
                    frame_count=frame_total,
                    on_frame=on_frame,
                )
            else:
                write_gif(
                    frames,
                    out_path,
                    fps=effective_fps,
                    profile=profile,
                    frame_count=frame_total,
                    on_frame=on_frame,
                )
            series_outputs.append(out_path)

        _emit(
            progress_callback,
            ProgressEvent(phase="PACKAGING", percent=90, message="打包输出"),
        )

        final_files: list[Path] = []
        if params.merge:
            merged = output_dir / f"merged.{ext}"
            if params.format == OutputFormat.MP4:
                concat_videos(series_outputs, merged, fps=effective_fps)
            else:
                concat_gifs(series_outputs, merged)
            # Also copy individual series into output for optional use
            for p in series_outputs:
                target = output_dir / p.name
                if not target.exists():
                    shutil.copy2(p, target)
            final_files = [merged]
        else:
            copied: list[Path] = []
            for p in series_outputs:
                target = output_dir / p.name
                shutil.copy2(p, target)
                copied.append(target)
            if len(copied) == 1:
                final_files = copied
            else:
                zip_path = output_dir / "result.zip"
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for p in copied:
                        zf.write(p, arcname=p.name)
                final_files = [zip_path]

        _emit(
            progress_callback,
            ProgressEvent(phase="SUCCEEDED", percent=100, message="完成"),
        )
        return ConvertResult(
            output_files=final_files,
            series_outputs=[output_dir / p.name for p in series_outputs],
            series_names=series_names,
        )
    except DicomFlowError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConvertError("转换失败", detail=str(exc)) from exc
