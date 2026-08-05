import io
import zipfile
from pathlib import Path

import pytest

from dicomflow.core.exceptions import InvalidArchiveError
from dicomflow.engine.archive import extract_archive


def test_zip_slip_rejected(tmp_path: Path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        # path traversal attempt
        zf.writestr("../outside.txt", "nope")

    dest = tmp_path / "out"
    # Depending on zip contents, extract may raise on resolve slip check
    # We construct a clearer slip via ZipInfo filename
    evil2 = tmp_path / "evil2.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("../../tmp/pwned.txt")
        zf.writestr(info, "x")
    evil2.write_bytes(buf.getvalue())

    with pytest.raises(InvalidArchiveError):
        extract_archive(evil2, dest)
