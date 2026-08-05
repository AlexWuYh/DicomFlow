from __future__ import annotations

import logging
import shutil
import subprocess
import zipfile
from pathlib import Path

from dicomflow.core.exceptions import ArchiveBombError, InvalidArchiveError

logger = logging.getLogger(__name__)

RAR_MAGIC = b"Rar!\x1a\x07"
ZIP_MAGIC = b"PK"
SEVEN_Z_MAGIC = b"7z\xbc\xaf\x27\x1c"


def _is_within_directory(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _read_magic(path: Path, n: int = 8) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


def detect_archive_type(path: Path) -> str | None:
    """Return zip|rar|7z|tar|None based on magic / suffix."""
    if path.is_dir():
        return None
    magic = _read_magic(path)
    if magic.startswith(ZIP_MAGIC) or zipfile.is_zipfile(path):
        return "zip"
    if magic.startswith(RAR_MAGIC) or path.suffix.lower() == ".rar":
        return "rar"
    if magic.startswith(SEVEN_Z_MAGIC) or path.suffix.lower() == ".7z":
        return "7z"
    suffix = path.suffix.lower()
    if suffix in {".tar", ".gz", ".tgz", ".bz2", ".xz"}:
        return "tar"
    return None


def extract_archive(
    archive_path: Path,
    dest_dir: Path,
    *,
    max_files: int = 200_000,
    max_total_bytes: int = 8 * 1024 * 1024 * 1024,
    max_ratio: float = 100.0,
) -> Path:
    """Safely extract supported archives into dest_dir. Returns dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    kind = detect_archive_type(archive_path)
    if kind is None:
        raise InvalidArchiveError(
            f"不支持的归档格式: {archive_path.name}",
            detail="支持 zip / rar / 7z / tar 系列",
        )

    if kind == "zip":
        return _extract_zip(
            archive_path,
            dest_dir,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
            max_ratio=max_ratio,
        )

    if kind == "rar":
        _extract_with_tools(
            archive_path,
            dest_dir,
            tool_cmds=[
                ["unrar", "x", "-o+", "-y", str(archive_path), str(dest_dir) + "/"],
                ["unrar-free", "x", "-o+", "-y", str(archive_path), str(dest_dir) + "/"],
                ["unar", "-f", "-o", str(dest_dir), str(archive_path)],
                ["7z", "x", f"-o{dest_dir}", "-y", str(archive_path)],
                ["7zz", "x", f"-o{dest_dir}", "-y", str(archive_path)],
            ],
            label="RAR",
        )
        _assert_extract_limits(dest_dir, max_files=max_files, max_total_bytes=max_total_bytes)
        return dest_dir

    if kind == "7z":
        _extract_with_tools(
            archive_path,
            dest_dir,
            tool_cmds=[
                ["7z", "x", f"-o{dest_dir}", "-y", str(archive_path)],
                ["7zz", "x", f"-o{dest_dir}", "-y", str(archive_path)],
            ],
            label="7z",
        )
        _assert_extract_limits(dest_dir, max_files=max_files, max_total_bytes=max_total_bytes)
        return dest_dir

    # tar family
    try:
        shutil.unpack_archive(str(archive_path), str(dest_dir))
    except Exception as exc:  # noqa: BLE001
        raise InvalidArchiveError(
            f"无法解压归档: {archive_path.name}",
            detail=str(exc),
        ) from exc
    _assert_extract_limits(dest_dir, max_files=max_files, max_total_bytes=max_total_bytes)
    return dest_dir


def _extract_with_tools(
    archive_path: Path,
    dest_dir: Path,
    *,
    tool_cmds: list[list[str]],
    label: str,
) -> None:
    errors: list[str] = []
    for cmd in tool_cmds:
        binary = cmd[0]
        if shutil.which(binary) is None:
            errors.append(f"{binary}: not installed")
            continue
        logger.info("Extracting %s with %s", archive_path.name, binary)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=60 * 60,
            )
            if proc.returncode == 0:
                return
            errors.append(f"{binary}: {proc.stderr.strip() or proc.stdout.strip() or proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{binary}: {exc}")

    raise InvalidArchiveError(
        f"无法解压 {label} 归档: {archive_path.name}",
        detail="; ".join(errors) or "未找到 unrar/unar/7z",
    )


def _assert_extract_limits(
    dest_dir: Path,
    *,
    max_files: int,
    max_total_bytes: int,
) -> None:
    total = 0
    count = 0
    for p in dest_dir.rglob("*"):
        if not p.is_file():
            continue
        count += 1
        if count > max_files:
            raise ArchiveBombError("解压后文件数超过限制", detail=f"count>{max_files}")
        try:
            total += p.stat().st_size
        except OSError:
            continue
        if total > max_total_bytes:
            raise ArchiveBombError(
                "解压后体积超过限制",
                detail=f"bytes={total}",
            )


def _extract_zip(
    archive_path: Path,
    dest_dir: Path,
    *,
    max_files: int,
    max_total_bytes: int,
    max_ratio: float,
) -> Path:
    try:
        zf = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise InvalidArchiveError("无效的 ZIP 文件", detail=str(exc)) from exc

    compressed_size = archive_path.stat().st_size or 1
    total_uncompressed = 0
    file_count = 0

    with zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise ArchiveBombError(
                "归档内文件数超过限制",
                detail=f"count={len(infos)} max={max_files}",
            )

        for info in infos:
            if info.is_dir():
                continue
            file_count += 1
            if file_count > max_files:
                raise ArchiveBombError("归档内文件数超过限制")

            total_uncompressed += info.file_size
            if total_uncompressed > max_total_bytes:
                raise ArchiveBombError(
                    "解压后体积超过限制",
                    detail=f"bytes={total_uncompressed}",
                )
            ratio = total_uncompressed / compressed_size
            if ratio > max_ratio and total_uncompressed > 1024 * 1024 * 1024:
                raise ArchiveBombError(
                    "疑似 zip bomb（压缩比过高）",
                    detail=f"ratio={ratio:.1f}",
                )

            target = (dest_dir / info.filename).resolve()
            if not _is_within_directory(dest_dir, target):
                raise InvalidArchiveError(
                    "归档包含非法路径（Zip Slip）",
                    detail=info.filename,
                )

        zf.extractall(dest_dir)

    return dest_dir


def prepare_input(
    input_path: Path,
    work_dir: Path,
    *,
    max_files: int = 200_000,
    max_total_bytes: int = 8 * 1024 * 1024 * 1024,
    max_ratio: float = 100.0,
) -> Path:
    """Return a directory containing DICOM files (extract archive if needed)."""
    if not input_path.exists():
        raise InvalidArchiveError(f"输入不存在: {input_path}")

    if input_path.is_dir():
        return input_path

    raw_dir = work_dir / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    extract_archive(
        input_path,
        raw_dir,
        max_files=max_files,
        max_total_bytes=max_total_bytes,
        max_ratio=max_ratio,
    )
    return raw_dir
