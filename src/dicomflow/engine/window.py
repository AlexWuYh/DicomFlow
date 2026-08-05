from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset


def apply_rescale(pixel: np.ndarray, ds: FileDataset) -> np.ndarray:
    slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
    intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
    if slope == 1.0 and intercept == 0.0:
        return pixel.astype(np.float64)
    return pixel.astype(np.float64) * slope + intercept


def _window_from_filename(path: Path | str | None) -> tuple[float, float] | None:
    if not path:
        return None
    match = re.search(r"[Ww](\d+)[Ll](-?\d+)", str(path))
    if not match:
        return None
    ww = float(match.group(1))
    wc = float(match.group(2))
    return wc, ww


def apply_window(pixel_data: np.ndarray, ds: FileDataset, source_path: Path | None = None) -> np.ndarray:
    """Apply VOI window to produce uint8 grayscale frame."""
    pixel = apply_rescale(pixel_data, ds)

    wc = getattr(ds, "WindowCenter", None)
    ww = getattr(ds, "WindowWidth", None)

    if wc is None or ww is None:
        fname = source_path or getattr(ds, "filename", None)
        parsed = _window_from_filename(fname)
        if parsed:
            wc, ww = parsed

    if wc is not None and ww is not None:
        if isinstance(wc, pydicom.multival.MultiValue):
            wc = float(wc[0])
        if isinstance(ww, pydicom.multival.MultiValue):
            ww = float(ww[0])
        wc, ww = float(wc), float(ww)
        lower = wc - ww / 2.0
        upper = wc + ww / 2.0
        pixel = np.clip(pixel, lower, upper)
        if upper > lower:
            pixel = (pixel - lower) / (upper - lower) * 255.0
        else:
            pixel = np.zeros_like(pixel)
    else:
        pmin, pmax = float(pixel.min()), float(pixel.max())
        if pmax > pmin:
            pixel = (pixel - pmin) / (pmax - pmin) * 255.0
        else:
            pixel = np.zeros_like(pixel)

    frame = pixel.astype(np.uint8)

    photometric = str(getattr(ds, "PhotometricInterpretation", "") or "").upper()
    if photometric == "MONOCHROME1":
        frame = 255 - frame

    return frame


def to_rgb_even(frame: np.ndarray) -> np.ndarray:
    """Grayscale/RGB → RGB with even H/W for H.264."""
    if frame.ndim == 2:
        frame = np.stack([frame] * 3, axis=-1)
    elif frame.ndim == 3 and frame.shape[2] == 1:
        frame = np.repeat(frame, 3, axis=2)
    elif frame.ndim == 3 and frame.shape[2] >= 3:
        frame = frame[:, :, :3]
    else:
        raise ValueError(f"Unsupported frame shape: {frame.shape}")

    h, w = frame.shape[:2]
    if h % 2 != 0 or w % 2 != 0:
        new_h = h + (h % 2)
        new_w = w + (w % 2)
        padded = np.zeros((new_h, new_w, 3), dtype=np.uint8)
        padded[:h, :w, :] = frame
        frame = padded
    return frame
