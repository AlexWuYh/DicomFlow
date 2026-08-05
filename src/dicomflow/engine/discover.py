from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset

from dicomflow.core.exceptions import NoDicomError

logger = logging.getLogger(__name__)

SKIP_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".mp4",
    ".gif",
    ".zip",
    ".rar",
    ".7z",
    ".txt",
    ".xml",
    ".json",
    ".html",
    ".pdf",
    ".exe",
    ".dll",
}


@dataclass
class DicomInstance:
    """Metadata-only instance; pixels loaded lazily during convert."""

    path: Path
    instance_number: float
    series_uid: str
    series_description: str
    series_number: int
    study_uid: str
    study_date: str
    study_time: str


@dataclass
class SeriesGroup:
    series_uid: str
    series_description: str
    series_number: int
    study_uid: str
    study_date: str
    study_time: str
    instances: list[DicomInstance] = field(default_factory=list)

    @property
    def safe_name(self) -> str:
        desc = self.series_description.strip() or self.series_uid[:12]
        safe = re.sub(r"[^\w\-]+", "_", desc, flags=re.UNICODE).strip("_")
        # Windows-ish reserved chars already stripped; collapse repeats
        safe = re.sub(r"_+", "_", safe)
        num = f"{self.series_number:03d}" if self.series_number else "000"
        base = f"{num}_{safe or self.series_uid[:12]}"
        return base[:120]


def _instance_sort_key(ds: Dataset) -> float:
    if getattr(ds, "InstanceNumber", None) is not None:
        try:
            return float(ds.InstanceNumber)
        except (TypeError, ValueError):
            pass
    if hasattr(ds, "ImagePositionPatient"):
        try:
            return float(ds.ImagePositionPatient[2])
        except (TypeError, ValueError, IndexError):
            pass
    return 0.0


def _looks_like_dicom_path(path: Path) -> bool:
    suffix = path.suffix
    if suffix.upper() == ".DCM":
        return True
    if suffix.lower() in {".dicom", ".ima"}:
        return True
    if suffix == "":
        return True
    if suffix.lower() in SKIP_SUFFIXES:
        return False
    # Odd extensions: still try (some PACS export .001 etc.)
    if re.fullmatch(r"\.\d+", suffix):
        return True
    return False


def _has_image_pixels(ds: Dataset) -> bool:
    if getattr(ds, "SamplesPerPixel", None) is None and not hasattr(ds, "Rows"):
        # Likely non-image DICOM (SR/PR/etc.)
        if "PixelData" not in ds and "FloatPixelData" not in ds and "DoubleFloatPixelData" not in ds:
            return False
    if "PixelData" in ds or "FloatPixelData" in ds or "DoubleFloatPixelData" in ds:
        return True
    # stop_before_pixels still leaves PixelData element sometimes absent until full read
    rows = getattr(ds, "Rows", None)
    cols = getattr(ds, "Columns", None)
    return bool(rows and cols)


def _try_read_header(path: Path) -> Dataset | None:
    try:
        ds = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
        if not _has_image_pixels(ds):
            return None
        return ds
    except Exception:  # noqa: BLE001
        return None


def find_dicom_instances(root_dir: Path) -> list[DicomInstance]:
    root = Path(root_dir)
    if not root.exists():
        raise NoDicomError(f"目录不存在: {root}")

    instances: list[DicomInstance] = []
    scanned = 0
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        if not _looks_like_dicom_path(fpath):
            continue

        scanned += 1
        ds = _try_read_header(fpath)
        if ds is None:
            continue

        series_uid = str(getattr(ds, "SeriesInstanceUID", "unknown") or "unknown")
        study_uid = str(getattr(ds, "StudyInstanceUID", "unknown") or "unknown")
        desc = str(getattr(ds, "SeriesDescription", "") or "")
        try:
            series_number = int(getattr(ds, "SeriesNumber", 0) or 0)
        except (TypeError, ValueError):
            series_number = 0

        instances.append(
            DicomInstance(
                path=fpath,
                instance_number=_instance_sort_key(ds),
                series_uid=series_uid,
                series_description=desc,
                series_number=series_number,
                study_uid=study_uid,
                study_date=str(getattr(ds, "StudyDate", "") or ""),
                study_time=str(getattr(ds, "StudyTime", "") or ""),
            )
        )

    logger.info("DICOM scan: candidates=%s images=%s under %s", scanned, len(instances), root)
    return instances


def group_series(instances: list[DicomInstance]) -> list[SeriesGroup]:
    if not instances:
        raise NoDicomError("未找到任何有效 DICOM 图像文件")

    groups: dict[str, SeriesGroup] = {}
    for inst in instances:
        if inst.series_uid not in groups:
            groups[inst.series_uid] = SeriesGroup(
                series_uid=inst.series_uid,
                series_description=inst.series_description,
                series_number=inst.series_number,
                study_uid=inst.study_uid,
                study_date=inst.study_date,
                study_time=inst.study_time,
            )
        groups[inst.series_uid].instances.append(inst)

    series_list = list(groups.values())
    for g in series_list:
        g.instances.sort(key=lambda x: (x.instance_number, str(x.path)))

    series_list.sort(
        key=lambda g: (
            g.study_date,
            g.study_time,
            g.study_uid,
            g.series_number,
            g.series_description,
            g.series_uid,
        )
    )
    return series_list
