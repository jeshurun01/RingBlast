"""Private-environment bootstrap used by Run_RingBlast.bat (stdlib only)."""
from hashlib import sha256
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    if (sys.version_info[:2] != (3, 12) or sys.prefix == sys.base_prefix
            or Path(sys.prefix).resolve() != (root / ".venv").resolve()):
        print("ERROR: RingBlast needs Python 3.12 in this folder's .venv. "
              "Rename the existing .venv folder and double-click Run_RingBlast.bat again.",
              file=sys.stderr)
        return 1
    try:
        requirements = root / "requirements.txt"
        stamp = root / ".venv" / "ringblast-requirements.sha256"
        fingerprint = sha256(requirements.read_bytes()).hexdigest()
        if not stamp.is_file() or stamp.read_text(encoding="ascii") != fingerprint:
            print("Installing RingBlast dependencies in .venv...", flush=True)
            subprocess.run(
                [sys.executable, "-I", "-m", "pip", "install", "-r", str(requirements)],
                cwd=root,
                check=True,
            )
            stamp.write_text(fingerprint, encoding="ascii")
        print("Starting RingBlast at http://127.0.0.1:8501 (Ctrl+C to stop).", flush=True)
        result = subprocess.run(
            [sys.executable, "-I", "-m", "streamlit", "run", str(root / "app.py"),
             "--server.address", "127.0.0.1", "--server.port", "8501",
             "--server.showEmailPrompt", "false",
             "--browser.serverAddress", "127.0.0.1", "--browser.gatherUsageStats", "false"],
            cwd=root,
            check=False,
        )
        if result.returncode:
            print("ERROR: RingBlast stopped. See the error above. If port 8501 is in use, "
                  "close the other RingBlast window. For missing packages, rename .venv "
                  "and run the launcher again.", file=sys.stderr)
        return result.returncode
    except subprocess.CalledProcessError:
        print("ERROR: Dependency installation failed. Check your internet connection, "
              "proxy and the pip error above, then double-click the launcher to retry.",
              file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}\nKeep the complete RingBlast clone in a writable folder. "
              "If .venv is damaged, rename it and run the launcher again.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
