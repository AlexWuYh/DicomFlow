from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
from PIL import Image

from dicomflow.core.exceptions import ConvertError
from dicomflow.engine.quality import QualityProfile

logger = logging.getLogger(__name__)


def resize_frame(frame: np.ndarray, profile: QualityProfile, *, for_gif: bool = False) -> np.ndarray:
    h, w = frame.shape[:2]
    max_side = profile.gif_max_side if for_gif else profile.max_side
    scale = profile.scale

    new_w, new_h = w, h
    if scale != 1.0:
        new_w = max(2, int(w * scale))
        new_h = max(2, int(h * scale))
    if max_side is not None:
        longest = max(new_w, new_h)
        if longest > max_side:
            ratio = max_side / longest
            new_w = max(2, int(new_w * ratio))
            new_h = max(2, int(new_h * ratio))

    new_w += new_w % 2
    new_h += new_h % 2

    if (new_w, new_h) == (w, h):
        return frame

    img = Image.fromarray(frame)
    img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    return np.asarray(img)


def write_mp4(
    frames: Iterable[np.ndarray],
    output_path: Path,
    *,
    fps: int,
    profile: QualityProfile,
    frame_count: int,
    on_frame: Callable[[int, int], None] | None = None,
) -> Path:
    import imageio.v2 as imageio

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        writer = imageio.get_writer(
            str(output_path),
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
            output_params=["-crf", str(profile.mp4_crf), "-preset", "medium"],
        )
    except TypeError:
        writer = imageio.get_writer(
            str(output_path),
            fps=fps,
            codec="libx264",
            quality=max(1, min(10, 31 - profile.mp4_crf // 3)),
            pixelformat="yuv420p",
            macro_block_size=1,
        )

    try:
        for idx, frame in enumerate(frames):
            frame = resize_frame(frame, profile, for_gif=False)
            writer.append_data(frame)
            if on_frame:
                on_frame(idx + 1, frame_count)
    except Exception as exc:  # noqa: BLE001
        raise ConvertError("MP4 编码失败", detail=str(exc)) from exc
    finally:
        writer.close()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ConvertError("MP4 输出为空")
    return output_path


def write_gif(
    frames: Iterable[np.ndarray],
    output_path: Path,
    *,
    fps: int,
    profile: QualityProfile,
    frame_count: int,
    on_frame: Callable[[int, int], None] | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = 1.0 / max(fps, 1)

    stride = 1
    if frame_count > profile.gif_max_frames:
        stride = int(np.ceil(frame_count / profile.gif_max_frames))

    pil_frames: list[Image.Image] = []
    try:
        for idx, frame in enumerate(frames):
            if idx % stride != 0:
                if on_frame:
                    on_frame(idx + 1, frame_count)
                continue
            frame = resize_frame(frame, profile, for_gif=True)
            img = Image.fromarray(frame).convert(
                "P", palette=Image.Palette.ADAPTIVE, colors=profile.gif_colors
            )
            pil_frames.append(img)
            if on_frame:
                on_frame(idx + 1, frame_count)

        if not pil_frames:
            raise ConvertError("GIF 无有效帧")

        pil_frames[0].save(
            output_path,
            save_all=True,
            append_images=pil_frames[1:],
            duration=int(duration * 1000),
            loop=0,
            optimize=True,
        )
    except ConvertError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ConvertError("GIF 编码失败", detail=str(exc)) from exc

    return output_path


def _probe_size(ffmpeg: str, path: Path) -> tuple[int, int]:
    """Return (width, height) via ffprobe-like ffmpeg output; fallback 512x512."""
    try:
        cmd = [
            ffmpeg,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(path),
        ]
        # imageio-ffmpeg is ffmpeg not ffprobe; try ffprobe next to it
        ffprobe = str(path)  # placeholder
        del ffprobe
    except Exception:  # noqa: BLE001
        pass

    # Prefer ffprobe if available; else parse ffmpeg -i
    try:
        import imageio_ffmpeg

        # imageio_ffmpeg ships ffmpeg only; use -i parse
        proc = subprocess.run(
            [ffmpeg, "-i", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        import re

        m = re.search(r"(\d{2,5})x(\d{2,5})", proc.stderr or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:  # noqa: BLE001
        logger.debug("probe size failed for %s", path, exc_info=True)
    return 512, 512


def concat_videos(
    inputs: list[Path],
    output_path: Path,
    *,
    fps: int,
    black_seconds: float = 0.4,
) -> Path:
    """
    Concatenate series videos by re-encoding with filter_complex.

    Stream-copy concat is unreliable for imageio-produced MP4s (bad timestamps /
    duration), which often results in only the first segment being playable.
    """
    if not inputs:
        raise ConvertError("没有可合并的视频")
    if len(inputs) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(inputs[0].read_bytes())
        return output_path

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise ConvertError("缺少 imageio-ffmpeg，无法合并视频") from exc

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Target canvas = max width/height across inputs (even)
    max_w, max_h = 0, 0
    for p in inputs:
        w, h = _probe_size(ffmpeg, p)
        max_w = max(max_w, w)
        max_h = max(max_h, h)
    max_w = max(2, max_w + (max_w % 2))
    max_h = max(2, max_h + (max_h % 2))

    n = len(inputs)
    cmd: list[str] = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for p in inputs:
        cmd.extend(["-i", str(p.resolve())])

    # Normalize fps/size then concat. Always re-encode (copy-concat breaks imageio MP4s).
    filter_parts: list[str] = []
    labels: list[str] = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]fps={fps},scale={max_w}:{max_h}:force_original_aspect_ratio=decrease,"
            f"pad={max_w}:{max_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )
        labels.append(f"[v{i}]")

    filter_parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=0[outv]")
    filter_complex = ";".join(filter_parts)

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        logger.warning(
            "ffmpeg filter concat failed, falling back to frame merge: %s",
            (proc.stderr or "")[-500:],
        )
        return _concat_videos_frame_fallback(
            inputs, output_path, fps=fps, black_seconds=black_seconds
        )

    return output_path


def _concat_videos_frame_fallback(
    inputs: list[Path],
    output_path: Path,
    *,
    fps: int,
    black_seconds: float = 0.4,
) -> Path:
    import imageio.v2 as imageio

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        str(output_path),
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p",
        macro_block_size=1,
        output_params=["-crf", "20", "-preset", "medium", "-movflags", "+faststart"],
    )
    try:
        target_size: tuple[int, int] | None = None
        for path in inputs:
            reader = imageio.get_reader(str(path))
            try:
                for frame in reader:
                    arr = np.asarray(frame)
                    if arr.ndim == 2:
                        arr = np.stack([arr] * 3, axis=-1)
                    if target_size is None:
                        h, w = arr.shape[:2]
                        target_size = (w + w % 2, h + h % 2)
                    tw, th = target_size
                    if arr.shape[1] != tw or arr.shape[0] != th:
                        img = Image.fromarray(arr).resize((tw, th), Image.Resampling.BILINEAR)
                        arr = np.asarray(img)
                    writer.append_data(arr)
                if target_size and black_seconds > 0:
                    tw, th = target_size
                    black = np.zeros((th, tw, 3), dtype=np.uint8)
                    for _ in range(max(1, int(fps * black_seconds))):
                        writer.append_data(black)
            finally:
                reader.close()
    except Exception as exc:  # noqa: BLE001
        raise ConvertError("视频合并失败（帧级回退）", detail=str(exc)) from exc
    finally:
        writer.close()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise ConvertError("视频合并输出为空")
    return output_path


def concat_gifs(inputs: list[Path], output_path: Path) -> Path:
    if not inputs:
        raise ConvertError("没有可合并的 GIF")
    if len(inputs) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(inputs[0].read_bytes())
        return output_path

    frames: list[Image.Image] = []
    duration = 100
    try:
        for path in inputs:
            img = Image.open(path)
            n = getattr(img, "n_frames", 1)
            for i in range(n):
                img.seek(i)
                frames.append(img.convert("RGB"))
                duration = img.info.get("duration", duration)
            if frames:
                # black-ish pause
                pause = Image.new("RGB", frames[-1].size, (0, 0, 0))
                frames.extend([pause.copy() for _ in range(3)])

        # unify size
        max_w = max(f.size[0] for f in frames)
        max_h = max(f.size[1] for f in frames)
        unified: list[Image.Image] = []
        for f in frames:
            canvas = Image.new("RGB", (max_w, max_h), (0, 0, 0))
            canvas.paste(f, ((max_w - f.size[0]) // 2, (max_h - f.size[1]) // 2))
            unified.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        unified[0].save(
            output_path,
            save_all=True,
            append_images=unified[1:],
            duration=duration,
            loop=0,
            optimize=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise ConvertError("GIF 合并失败", detail=str(exc)) from exc
    return output_path
