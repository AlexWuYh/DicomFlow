from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dicomflow",
        description="Local-first DICOM → MP4/GIF converter",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="Convert DICOM dir/archive to media")
    convert.add_argument("-i", "--input", required=True, help="Input directory or archive")
    convert.add_argument("-o", "--output", required=True, help="Output directory")
    convert.add_argument(
        "-f",
        "--format",
        default="mp4",
        choices=["mp4", "gif"],
        help="Output format",
    )
    convert.add_argument(
        "-q",
        "--quality",
        default="high",
        choices=["low", "medium", "high"],
        help="Quality preset (default: high for clinical review)",
    )
    convert.add_argument(
        "--merge",
        action="store_true",
        help="Merge all series into a single media file",
    )
    convert.add_argument("--fps", type=int, default=10, help="Frames per second")

    serve = sub.add_parser("serve", help="Start local web UI + API")
    serve.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    serve.add_argument("--port", type=int, default=None, help="Bind port (default 8765)")

    app_cmd = sub.add_parser(
        "app",
        help="Start offline desktop app (Windows-first: local UI window, no network)",
    )
    app_cmd.add_argument(
        "--port",
        type=int,
        default=None,
        help="Loopback port (default: ephemeral free port)",
    )
    app_cmd.add_argument(
        "--data-dir",
        default=None,
        help="App data directory (uploads/outputs); default: platform app data path",
    )

    return parser


def cmd_convert(args: argparse.Namespace) -> int:
    from dicomflow.core.models import ConvertParams, OutputFormat, Quality
    from dicomflow.engine.pipeline import convert_dicom_package

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


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from dicomflow.core.config import get_settings

    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    print(f"DicomFlow listening on http://{host}:{port}")
    uvicorn.run(
        "dicomflow.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
    )
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    from dicomflow.desktop.app import run_offline_app

    data_dir = Path(args.data_dir) if args.data_dir else None
    return run_offline_app(port=args.port, data_dir=data_dir)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "convert":
            raise SystemExit(cmd_convert(args))
        if args.command == "serve":
            raise SystemExit(cmd_serve(args))
        if args.command == "app":
            raise SystemExit(cmd_app(args))
        parser.error(f"unknown command {args.command}")
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main(sys.argv[1:])
