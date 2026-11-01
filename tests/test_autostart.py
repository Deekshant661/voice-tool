import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _ps(script, *args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(SCRIPTS / script), *args], capture_output=True, text=True)


def _read_shortcut(path):
    ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); "
          "$s.TargetPath; $s.Arguments; $s.WorkingDirectory")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return out.stdout.splitlines()


@pytest.mark.win
def test_install_creates_shortcut(tmp_path):
    r = _ps("install-autostart.ps1", "-StartupDir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    lnk = tmp_path / "Voice Tool.lnk"
    assert lnk.exists()
    target, args, workdir = _read_shortcut(lnk)
    assert target.lower().endswith(r"\.voice-tool\venv\scripts\pythonw.exe")
    assert args == "-m voicetool"
    assert Path(workdir) == REPO


@pytest.mark.win
def test_install_is_idempotent(tmp_path):
    _ps("install-autostart.ps1", "-StartupDir", str(tmp_path))
    r = _ps("install-autostart.ps1", "-StartupDir", str(tmp_path))
    assert r.returncode == 0 and len(list(tmp_path.glob("*.lnk"))) == 1


@pytest.mark.win
def test_uninstall_removes_shortcut(tmp_path):
    _ps("install-autostart.ps1", "-StartupDir", str(tmp_path))
    r = _ps("uninstall-autostart.ps1", "-StartupDir", str(tmp_path))
    assert r.returncode == 0 and not (tmp_path / "Voice Tool.lnk").exists()


@pytest.mark.win
def test_uninstall_when_not_installed(tmp_path):
    assert _ps("uninstall-autostart.ps1", "-StartupDir", str(tmp_path)).returncode == 0


@pytest.mark.win
def test_real_app_starts_and_stays_running():
    import os
    import time

    from voicetool.app import MUTEX_NAME, acquire_single_instance

    pythonw = Path(os.environ["USERPROFILE"]) / ".voice-tool" / "venv" / "Scripts" / "pythonw.exe"
    proc = subprocess.Popen([str(pythonw), "-m", "voicetool"], cwd=REPO)
    try:
        time.sleep(5)
        assert proc.poll() is None, f"app exited with code {proc.returncode}"
        assert acquire_single_instance(MUTEX_NAME) is None  # the running app holds the lock
    finally:
        proc.kill()
        proc.wait()
