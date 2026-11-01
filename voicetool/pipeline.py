"""Hotkey events in, pasted text out. Dictations are processed one at a time, in order."""
import logging
import queue
import threading
import time
from typing import Callable

from voicetool.cleanup import clean
from voicetool.config import Config
from voicetool.recorder import RecorderError, too_short
from voicetool.win.paste import PasteResult

log = logging.getLogger("voicetool")

_NOTICES = {
    PasteResult.COPIED_FOCUS_MOVED: "Copied — focus moved, paste it with Ctrl+V",
    PasteResult.COPIED_ELEVATED: "Copied — can't paste into admin windows, use Ctrl+V",
}


class Pipeline:
    def __init__(self, cfg: Config, recorder, models, store, deliver_fn, foreground_fn,
                 transcribe_fn, notify: Callable[[str], None], beep: Callable[[str], None],
                 on_state: Callable[[str], None] = lambda state: None):
        self.cfg = cfg
        self.recorder = recorder
        self.models = models
        self.store = store
        self.deliver_fn = deliver_fn
        self.foreground_fn = foreground_fn
        self.transcribe_fn = transcribe_fn
        self.notify = notify
        self.beep = beep
        self.on_state = on_state
        self.logging = cfg.logging  # the tray can toggle this while running
        self.open_corrections: Callable[[], None] = lambda: None
        self._queue: queue.Queue = queue.Queue()
        self._pending = 0
        self._cond = threading.Condition()
        self._recording = False
        self._target = (0, "", "")
        self._warned_size = False
        threading.Thread(target=self._worker, daemon=True).start()

    def on_event(self, event: str) -> None:
        if event == "start":
            self._target = self.foreground_fn()
            self.models.ensure_loading()
            try:
                self.recorder.start()
            except RecorderError as e:
                self.notify(f"Microphone unavailable: {e}")
                return
            self._recording = True
            self.on_state("recording")
            self.beep("start")
        elif event == "stop":
            if not self._recording:
                return  # the start failed, or was cancelled
            self._recording = False
            audio = self.recorder.stop()
            self.beep("stop")
            with self._cond:
                self._pending += 1
            self.on_state("working")
            self._queue.put((audio, self._target))
        elif event == "cancel":
            if self._recording:
                self._recording = False
                self.recorder.cancel()
                self._settle_state()
        elif event == "delete_last":
            self.notify("Deleted last recording" if self.store.delete_last() else "Nothing to delete")
        elif event == "corrections":
            self.open_corrections()

    def drain(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._pending and time.monotonic() < deadline:
                self._cond.wait(deadline - time.monotonic())

    def _worker(self) -> None:
        while True:
            audio, target = self._queue.get()
            try:
                self._process(audio, target)
            except Exception as e:  # one bad dictation must not stop the tool
                log.exception("Dictation failed: %s", e)
                self.notify(f"Dictation failed: {e}")
            finally:
                with self._cond:
                    self._pending -= 1
                    self._cond.notify_all()
                self._settle_state()

    def _process(self, audio, target) -> None:
        if too_short(audio, self.cfg.min_seconds):
            return
        with self.models.use() as model:
            raw = self.transcribe_fn(model, audio, self.cfg)
        if not raw:
            return
        text = clean(raw, self.cfg.fillers, self.cfg.replacements)
        if not text:
            return
        hwnd, title, process = target
        result = self.deliver_fn(text, hwnd)
        if result in _NOTICES:
            self.notify(_NOTICES[result])
        if self.logging:
            self.store.add(audio, raw, text, title, process)
            if not self._warned_size and self.store.total_bytes() > self.cfg.warn_gb * 1e9:
                self._warned_size = True
                self.notify(f"Recordings are over {self.cfg.warn_gb:g} GB — open the data folder to review")

    def _settle_state(self) -> None:
        if self._recording:
            return
        with self._cond:
            busy = self._pending > 0
        self.on_state("working" if busy else "idle")
