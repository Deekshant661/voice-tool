"""Menu-bar icon: shows state as text and holds the menu. rumps (AppKit) must own the main
thread, and AppKit is not thread-safe, so other threads hand work over with call_soon(); a timer
on the main thread runs it."""
import logging
import queue
import subprocess
from typing import Callable

import rumps

PUMP_S = 0.05
_TITLES = {"idle": "VT", "recording": "VT ●", "working": "VT …"}


def title_for(state: str) -> str:
    return _TITLES[state]


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MenuBar:
    def __init__(self, status: Callable[[], dict], handlers: dict[str, Callable[[], None]],
                 run: Callable[[list[str]], object] = subprocess.Popen):
        self._status = status
        self._run = run
        self._calls: queue.Queue = queue.Queue()
        self.app = rumps.App("Voice Tool", title=title_for("idle"), quit_button=None)
        self._model = rumps.MenuItem("Model: not loaded")
        self._size = rumps.MenuItem("Recordings: 0.00 GB")
        self._logging = rumps.MenuItem("Save recordings", callback=lambda _: handlers["logging"]())
        self._keep = rumps.MenuItem("Keep model loaded", callback=lambda _: handlers["keep"]())
        self.app.menu = [
            self._model, self._size, None, self._logging, self._keep,
            rumps.MenuItem("Unload model now", callback=lambda _: handlers["unload"]()), None,
            rumps.MenuItem("Open recent dictations", callback=lambda _: handlers["corrections"]()),
            rumps.MenuItem("Open data folder", callback=lambda _: handlers["data"]()),
            rumps.MenuItem("Quit Voice Tool", callback=lambda _: handlers["quit"]()),
        ]
        self._timer = rumps.Timer(lambda _: self.pump(), PUMP_S)

    # --- any thread ---
    def call_soon(self, fn: Callable[[], None]) -> None:
        self._calls.put(fn)

    def set_state(self, state: str) -> None:
        def apply():
            self.app.title = title_for(state)
            if state == "idle":
                self.refresh_status()
        self.call_soon(apply)

    def notify(self, msg: str) -> None:
        # Best effort: a notification must never break a dictation.
        try:
            self._run(["osascript", "-e",
                       f'display notification {_quote(msg)} with title "Voice Tool"'])
        except Exception:
            logging.getLogger("voicetool").exception("notification failed")

    # --- main thread ---
    def pump(self) -> None:
        while True:
            try:
                fn = self._calls.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:  # one failed action must not stop all later ones
                logging.getLogger("voicetool").exception("Action failed")

    def refresh_status(self) -> None:
        s = self._status()
        self._model.title = f"Model: {s['model'] or 'not loaded'}"
        self._size.title = f"Recordings: {s['bytes'] / 1e9:.2f} GB"
        self._logging.state = int(s["logging"])
        self._keep.state = int(s["keep_loaded"])

    def start(self) -> None:
        """Blocks: runs the AppKit event loop on the calling (main) thread."""
        self.refresh_status()
        self._timer.start()
        self.app.run()

    def stop(self) -> None:
        rumps.quit_application()
