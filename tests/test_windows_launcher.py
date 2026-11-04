"""Bootstrap logic on all platforms; actual cmd.exe smoke tests on Windows."""
import importlib.util
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_launcher(monkeypatch, tmp_path):
    path = ROOT / "scripts" / "launch_ringblast.py"
    assert path.is_file(), "The launcher bootstrap must exist"
    spec = importlib.util.spec_from_file_location("launch_ringblast", path)
    assert spec is not None and spec.loader is not None
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    root = tmp_path / "RingBlast with spaces & symbols"
    (root / "scripts").mkdir(parents=True)
    (root / ".venv").mkdir()
    (root / "app.py").write_text("", encoding="utf-8")
    (root / "requirements.txt").write_text("streamlit>=1.57,<2\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "__file__", str(root / "scripts" / path.name))
    monkeypatch.setattr(launcher.sys, "version_info", (3, 12, 10))
    monkeypatch.setattr(launcher.sys, "prefix", str(root / ".venv"))
    monkeypatch.setattr(launcher.sys, "base_prefix", str(tmp_path / "Python312"))
    return launcher, root


def test_first_run_installs_in_venv_then_launches_local_app(monkeypatch, tmp_path):
    launcher, root = load_launcher(monkeypatch, tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 0
    assert len(commands) == 2
    assert commands[0][0] == [sys.executable, "-I", "-m", "pip", "install", "-r", str(root / "requirements.txt")]
    app_command, options = commands[1]
    assert app_command[:5] == [sys.executable, "-I", "-m", "streamlit", "run"]
    assert str(root / "app.py") in app_command
    assert app_command[app_command.index("--server.address") + 1] == "127.0.0.1"
    assert app_command[app_command.index("--browser.gatherUsageStats") + 1] == "false"
    assert options["cwd"] == root
    assert (root / ".venv" / "ringblast-requirements.sha256").is_file()


def test_reuses_install_until_requirements_change(monkeypatch, tmp_path):
    launcher, root = load_launcher(monkeypatch, tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 0
    commands.clear()
    assert launcher.main() == 0
    assert len(commands) == 1
    assert "streamlit" in commands[0]
    (root / "requirements.txt").write_text("streamlit>=1.58,<2\n", encoding="utf-8")
    commands.clear()
    assert launcher.main() == 0
    assert len(commands) == 2
    assert "pip" in commands[0]


@pytest.mark.parametrize("invalid", ["version", "system", "other_venv"])
def test_rejects_wrong_interpreter_before_install(monkeypatch, tmp_path, capsys, invalid):
    launcher, root = load_launcher(monkeypatch, tmp_path)
    if invalid == "version":
        monkeypatch.setattr(launcher.sys, "version_info", (3, 13, 0))
    elif invalid == "system":
        monkeypatch.setattr(launcher.sys, "base_prefix", launcher.sys.prefix)
    else:
        monkeypatch.setattr(launcher.sys, "prefix", str(tmp_path / "other_venv"))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("Must not install or launch"))
    assert launcher.main() == 1
    assert "Python 3.12" in capsys.readouterr().err
    assert not (root / ".venv" / "ringblast-requirements.sha256").exists()


def test_install_failure_is_retryable_and_actionable(monkeypatch, tmp_path, capsys):
    launcher, root = load_launcher(monkeypatch, tmp_path)
    commands = []

    def fail(command, **kwargs):
        commands.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(launcher.subprocess, "run", fail)
    assert launcher.main() == 1
    assert len(commands) == 1
    assert not (root / ".venv" / "ringblast-requirements.sha256").exists()
    assert "internet" in capsys.readouterr().err.lower()


def test_missing_clone_file_gives_actionable_error(monkeypatch, tmp_path, capsys):
    launcher, root = load_launcher(monkeypatch, tmp_path)
    (root / "requirements.txt").unlink()
    assert launcher.main() == 1
    assert "requirements.txt" in capsys.readouterr().err


def test_streamlit_failure_is_propagated(monkeypatch, tmp_path, capsys):
    launcher, root = load_launcher(monkeypatch, tmp_path)

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0 if "pip" in command else 5)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 5
    assert "8501" in capsys.readouterr().err


def test_batch_entrypoint_is_safe_for_double_click():
    batch = ROOT / "Run_RingBlast.bat"
    assert batch.is_file(), "Double-click entrypoint must exist"
    text = batch.read_text(encoding="ascii")
    assert "setlocal EnableExtensions DisableDelayedExpansion" in text
    assert 'pushd "%~dp0"' in text
    assert 'py -3.12 -m venv ".venv"' in text
    assert '".venv\\Scripts\\python.exe" -I "scripts\\launch_ringblast.py"' in text
    assert "pause" in text
    assert "exit /b" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows cmd.exe and py launcher")
def test_windows_double_click_fresh_then_cached_launch(tmp_path):
    """Run the real batch, venv, pip and Streamlit from an unrelated cwd."""
    root = tmp_path / "RingBlast spaces & symbols! (test)"
    (root / "scripts").mkdir(parents=True)
    for name in ("Run_RingBlast.bat", "requirements.txt", "app.py", "app_utils.py", "xml_to_image.py"):
        shutil.copy2(ROOT / name, root / name)
    shutil.copy2(ROOT / "scripts" / "launch_ringblast.py", root / "scripts")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(2):
        log = tmp_path / f"launch-{attempt}.log"
        with log.open("wb") as output:
            process = subprocess.Popen(
                f'cmd.exe /d /s /c ""{root / "Run_RingBlast.bat"}""',
                cwd=tmp_path,
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 180
                healthy = False
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        with opener.open("http://127.0.0.1:8501/_stcore/health", timeout=1) as response:
                            healthy = response.status == 200
                        if healthy:
                            break
                    except (urllib.error.URLError, TimeoutError, OSError):
                        pass
                    time.sleep(0.5)
                contents = log.read_text(encoding="utf-8", errors="replace")
                assert healthy, contents
                assert process.poll() is None, contents
                assert "Starting RingBlast" in contents
                assert ("Installing RingBlast dependencies" in contents) == (attempt == 0)
                assert (root / ".venv" / "ringblast-requirements.sha256").is_file()
            finally:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
                process.wait(timeout=15)
                assert process.stdin is not None
                process.stdin.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows cmd.exe")
@pytest.mark.parametrize("failure", ["missing_python", "incomplete_clone", "broken_venv"])
def test_windows_batch_reports_errors_and_waits_for_key(tmp_path, failure):
    root = tmp_path / "RingBlast errors & spaces!"
    (root / "scripts").mkdir(parents=True)
    for name in ("Run_RingBlast.bat", "app.py", "requirements.txt"):
        shutil.copy2(ROOT / name, root / name)
    shutil.copy2(ROOT / "scripts" / "launch_ringblast.py", root / "scripts")
    if failure == "incomplete_clone":
        (root / "app.py").unlink()
    elif failure == "broken_venv":
        (root / ".venv").mkdir()
    env = os.environ.copy()
    env["PATH"] = str(tmp_path / "no-python-here")
    cmd = str(Path(env["SystemRoot"]) / "System32" / "cmd.exe")
    result = subprocess.run(
        f'"{cmd}" /d /s /c ""{root / "Run_RingBlast.bat"}""',
        cwd=tmp_path, env=env, input="\n", capture_output=True, text=True,
        timeout=20, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ERROR:" in result.stdout
    assert "Press any key" in result.stdout  # PAUSE executed, fed a key by the test.
    message = {"missing_python": "Python 3.12", "incomplete_clone": "complete RingBlast folder",
               "broken_venv": "rename it"}[failure]
    assert message in result.stdout
