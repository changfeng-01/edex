from pathlib import Path
import zipfile

import pytest

from goa_eval.io_utils import extract_archives


def test_extract_archives_rejects_zip_members_outside_output_dir(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    archive = raw_dir / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "outside")
        zf.writestr("safe/file.txt", "inside")

    out_dir = tmp_path / "out"

    with pytest.raises(ValueError, match="Unsafe archive member"):
        extract_archives(raw_dir, out_dir)

    assert not (tmp_path / "escape.txt").exists()
