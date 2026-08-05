#!/usr/bin/env python3
"""
Deprecated entrypoint — use `dicomflow convert` instead.

This thin wrapper keeps old command lines working while routing through
the modern engine (unique series naming, zip/rar input, quality, merge).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    warnings.warn(
        "dicom_convert.py is deprecated; prefer: dicomflow convert -i ... -o ...",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "注意: dicom_convert.py 已废弃，建议使用: dicomflow convert -i <输入> -o <输出>",
        file=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        description="[deprecated] DICOM → media (wrapper around dicomflow engine)",
    )
    parser.add_argument("-i", "--input", required=True, help="DICOM 目录或压缩包")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument(
        "-f",
        "--format",
        default="mp4",
        choices=["mp4", "gif"],
        help="输出格式（默认 mp4）",
    )
    parser.add_argument(
        "-q",
        "--quality",
        default="high",
        choices=["low", "medium", "high"],
        help="质量档位",
    )
    parser.add_argument("--merge", action="store_true", help="合并为单个文件")
    parser.add_argument("--fps", type=int, default=10, help="帧率")
    args = parser.parse_args(argv)

    try:
        from dicomflow.core.models import ConvertParams, OutputFormat, Quality
        from dicomflow.engine.pipeline import convert_dicom_package
    except ImportError:
        print(
            "缺少 dicomflow 包。请先: pip install -e .",
            file=sys.stderr,
        )
        return 1

    def on_progress(event) -> None:
        extra = ""
        if event.series_index and event.series_total:
            extra = f" [{event.series_index}/{event.series_total}]"
        print(f"[{event.percent:3d}%] {event.phase}{extra} {event.message}")

    params = ConvertParams(
        format=OutputFormat(args.format),
        quality=Quality(args.quality),
        merge=bool(args.merge),
        fps=args.fps,
    )
    result = convert_dicom_package(
        Path(args.input),
        Path(args.output),
        params=params,
        progress_callback=on_progress,
    )
    print("Outputs:")
    for p in result.output_files:
        print(f"  - {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
