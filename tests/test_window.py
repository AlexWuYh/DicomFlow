import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dicomflow.engine.window import apply_window, to_rgb_even


def _minimal_ds(**kwargs) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPInstanceUID = generate_uid()
    for k, v in kwargs.items():
        setattr(ds, k, v)
    return ds


def test_apply_window_with_tags():
    ds = _minimal_ds(WindowCenter=100, WindowWidth=200)
    pixel = np.linspace(0, 200, 16, dtype=np.float32).reshape(4, 4)
    out = apply_window(pixel, ds)
    assert out.dtype == np.uint8
    assert out.min() >= 0 and out.max() <= 255


def test_monochrome1_inverts():
    ds = _minimal_ds(
        WindowCenter=50,
        WindowWidth=100,
        PhotometricInterpretation="MONOCHROME1",
    )
    pixel = np.full((4, 4), 50, dtype=np.float32)
    out = apply_window(pixel, ds)
    # center maps ~127 then inverted
    assert out.mean() > 100


def test_to_rgb_even_pads():
    frame = np.zeros((5, 7), dtype=np.uint8)
    rgb = to_rgb_even(frame)
    assert rgb.shape == (6, 8, 3)
