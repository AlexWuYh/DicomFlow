#!/usr/bin/env python3
"""Generate a tiny synthetic DICOM series for local smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)


def write_slice(path: Path, series_uid: str, study_uid: str, instance: int, value: int) -> None:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SeriesDescription = "Synthetic Bone"
    ds.SeriesNumber = 1
    ds.InstanceNumber = instance
    ds.Modality = "CT"
    ds.PatientName = "Test^Patient"
    ds.PatientID = "T001"
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 32
    ds.Columns = 32
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.WindowCenter = 100
    ds.WindowWidth = 200
    arr = np.full((32, 32), value, dtype=np.uint16)
    ds.PixelData = arr.tobytes()
    ds.save_as(path, write_like_original=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, default=Path("data/sample_dicom"))
    parser.add_argument("-n", "--frames", type=int, default=5)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    study = generate_uid()
    series = generate_uid()
    for i in range(1, args.frames + 1):
        write_slice(args.output / f"img_{i:03d}.dcm", series, study, i, value=40 + i * 10)
    print(f"Wrote {args.frames} slices to {args.output}")


if __name__ == "__main__":
    main()
