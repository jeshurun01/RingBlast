import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_app_starts_with_previous_app_utils_interface(tmp_path):
    """A hot-reloaded app must not require helpers added in the same deployment."""
    shutil.copy2(PROJECT_ROOT / "app.py", tmp_path / "app.py")
    shutil.copy2(PROJECT_ROOT / "xml_to_image.py", tmp_path / "xml_to_image.py")
    (tmp_path / "app_utils.py").write_text(
        """
def csv_safe_cell(value):
    return value


def unique_upload_base(filename, used):
    return filename


def upload_fingerprint(files):
    return ()
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "app.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ImportError" not in result.stderr
