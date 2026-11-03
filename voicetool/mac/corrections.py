"""'Recent dictations' window for macOS. The menu bar owns the main thread and tkinter wants it
too, so the window runs in its own short-lived process, reusing the shared tkinter window."""
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from typing import Callable

from voicetool.config import DATA_DIR
from voicetool.store import Store
from voicetool.win import corrections as window  # plain tkinter, no Windows calls


class WindowStore(Store):
    """The main app may have written a FLAC whose row isn't committed yet; orphan cleanup from
    this second process would delete that recording. The main app cleans up on its own start."""

    def _remove_orphans(self) -> None:
        pass


def current_window():
    return window._open


def child_main(data_dir: Path, root: tk.Tk | None = None) -> None:
    own_root = root is None
    if own_root:
        root = tk.Tk()
        root.withdraw()
    win = window.open_window(root, WindowStore(data_dir))
    root.wait_window(win.win)
    if own_root:
        root.destroy()


def _spawn() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "voicetool.mac.corrections", str(DATA_DIR)])


class CorrectionsLauncher:
    def __init__(self, spawn: Callable[[], object] = _spawn):
        self._spawn = spawn
        self._proc = None

    def open(self) -> bool:
        """Returns False when the window is already open."""
        if self._proc is not None and self._proc.poll() is None:
            return False
        self._proc = self._spawn()
        return True


if __name__ == "__main__":
    child_main(Path(sys.argv[1]))
