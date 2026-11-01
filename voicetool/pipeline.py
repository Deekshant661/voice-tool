"""Hotkey events in, pasted text out.

Two threads, so the keyboard hook never waits on anything slow:
- control: handles each hotkey event (opening/closing the mic, the tray state);
- worker: processes dictations and "delete last" strictly in order, one at a time."""
import logging
import queue
import threading
import time
from typing import Callable

from voicetool.cleanup import clean
from voicetool.config import Config
from voicetool.recorder import RecorderError, is_silent, too_short
from voicetool.win.paste import PasteResult

log = logging.getLogger("voicetool")

_NOTICES = {
    PasteResult.COPIED_FOCUS_MOVED: "Copied — focus moved, paste it with Ctrl+V",
    PasteResult.COPIED_ELEVATED: "Copied — can't paste into admin windows, use Ctrl+V",
}
_DELETE_LAST = object()


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
        self._events: queue.Queue = queue.Queue()
        self._work: queue.Queue = queue.Queue()
        self._cond = threading.Condition()
        self._pending_events = 0
        self._pending_work = 0
        self._recording = False
        self._target = (0, "", "")
        self._warned_size = False
        threading.Thread(target=self._control_loop, daemon=True, name="control").start()
        threading.Thread(target=self._worker_loop, daemon=True, name="worker").start()

    def on_event(self, event: str) -> None:
        """Called on the keyboard hook thread: only queue the event."""
        with self._cond:
            self._pending_events += 1
        self._events.put(event)

    def drain(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with self._cond:
            while (self._pending_events or self._pending_work) and time.monotonic() < deadline:
                self._cond.wait(deadline - time.monotonic())

    # --- control thread ---
    def _control_loop(self) -> None:
        while True:
            event = self._events.get()
            log.info("hotkey: %s", event)
            try:
                self._handle(event)
            except Exception as e:  # e.g. the mic unplugged mid-dictation
                self._recording = False
                log.exception("Hotkey action '%s' failed: %s", event, e)
                self.notify(f"Voice Tool error: {e}")
                self._settle_state()
            finally:
                with self._cond:
                    self._pending_events -= 1
                    self._cond.notify_all()

    def _handle(self, event: str) -> None:
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
            self._enqueue_work((audio, self._target))
        elif event == "cancel":
            if self._recording:
                self._recording = False
                self.recorder.cancel()
                self._settle_state()
        elif event == "delete_last":
            # Queued behind pending dictations, so it deletes the one just spoken.
            self._enqueue_work(_DELETE_LAST)
        elif event == "corrections":
            self.open_corrections()

    def _enqueue_work(self, item) -> None:
        with self._cond:
            self._pending_work += 1
        if item is not _DELETE_LAST:
            self.on_state("working")
        self._work.put(item)

    # --- worker thread ---
    def _worker_loop(self) -> None:
        while True:
            item = self._work.get()
            try:
                if item is _DELETE_LAST:
                    self.notify("Deleted last recording" if self.store.delete_last() else "Nothing to delete")
                else:
                    self._process(*item)
            except Exception as e:  # one bad dictation must not stop the tool
                log.exception("Dictation failed: %s", e)
                self.notify(f"Dictation failed: {e}")
            finally:
                with self._cond:
                    self._pending_work -= 1
                    self._cond.notify_all()
                self._settle_state()

    def _process(self, audio, target) -> None:
        seconds = len(audio) / 16000
        if too_short(audio, self.cfg.min_seconds):
            log.info("dictation: %.2f s, too short, skipped", seconds)
            return
        if is_silent(audio):
            name = getattr(self.recorder, "device_name", "the microphone")
            log.info("dictation: %.2f s of pure silence from %s", seconds, name)
            self.notify(f"Microphone sent silence ({name}). Is it muted? "
                        "Choose another with input_device in config.toml")
            return
        started = time.monotonic()
        with self.models.use() as model:
            raw = self.transcribe_fn(model, audio, self.cfg)
        text = clean(raw, self.cfg.fillers, self.cfg.replacements) if raw else ""
        if not text:
            log.info("dictation: %.2f s, no speech found", seconds)
            return
        hwnd, title, process = target
        try:
            result = self.deliver_fn(text, hwnd)
        except Exception as e:
            # Don't lose what was said: keep it in the store and show it.
            log.exception("Paste failed: %s", e)
            self._save(audio, raw, text, title, process)
            self.notify(f"Paste failed ({e}). You said: {text[:200]}")
            return
        log.info("dictation: %.2f s audio, %d chars, %s in %.2f s", seconds, len(text),
                 result.value, time.monotonic() - started)
        if result in _NOTICES:
            self.notify(_NOTICES[result])
        self._save(audio, raw, text, title, process)

    def _save(self, audio, raw, text, title, process) -> None:
        if not self.logging:
            return
        self.store.add(audio, raw, text, title, process)
        if not self._warned_size and self.store.total_bytes() > self.cfg.warn_gb * 1e9:
            self._warned_size = True
            self.notify(f"Recordings are over {self.cfg.warn_gb:g} GB — open the data folder to review")

    def _settle_state(self) -> None:
        if self._recording:
            return
        with self._cond:
            busy = self._pending_work > 0
        self.on_state("working" if busy else "idle")
