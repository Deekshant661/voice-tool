"""Wires everything together. Threads: tkinter owns the main thread, the tray runs detached,
pynput listens on its own thread, and the pipeline has one worker. Anything that touches tkinter
is handed to the main thread through call_soon()."""
import os
import queue
import threading
import tkinter as tk
from typing import Callable

import win32api
import win32event
import winerror

from voicetool.config import DATA_DIR, Config

MUTEX_NAME = "VoiceTool.SingleInstance"
TICK_MS = 30_000
PUMP_MS = 50
_TONES = {"start": (880, 60), "stop": (660, 60)}


def beep_tone(kind: str) -> tuple[int, int]:
    return _TONES[kind]


def fallback_notice(label: str) -> str | None:
    if "fallback" in label:
        return f"GPU unavailable — using {label.split(' ')[0]} model on CPU"
    return None


def acquire_single_instance(name: str = MUTEX_NAME):
    handle = win32event.CreateMutex(None, False, name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None
    return handle


class App:
    def __init__(self, cfg: Config, root: tk.Tk, store, models,
                 make_pipeline: Callable, make_tray: Callable,
                 opener: Callable[[str], None] = os.startfile,
                 open_corrections_window: Callable | None = None):
        self.cfg = cfg
        self.root = root
        self.store = store
        self.store_dir = DATA_DIR
        self.models = models
        self.opener = opener
        if open_corrections_window is None:
            from voicetool.win.corrections import open_window as open_corrections_window
        self._open_corrections_window = open_corrections_window
        self.stopping = False
        self._calls: queue.Queue = queue.Queue()
        self.tray = make_tray(self)
        self.pipeline = make_pipeline(self)
        self.pipeline.open_corrections = lambda: self.call_soon(self.open_corrections)
        self.models.on_loaded = self._on_loaded
        self.root.after(PUMP_MS, self._pump)

    # --- main-thread hand-off ---
    def call_soon(self, fn: Callable[[], None]) -> None:
        self._calls.put(fn)

    def _pump(self) -> None:
        while not self._calls.empty():
            self._calls.get()()
        if not self.stopping:
            self.root.after(PUMP_MS, self._pump)

    # --- used by the pipeline ---
    def notify(self, msg: str) -> None:
        self.tray.notify(msg)

    def set_state(self, state: str) -> None:
        self.tray.set_state(state)

    def _on_loaded(self, label: str) -> None:
        notice = fallback_notice(label)
        if notice:
            self.notify(notice)

    # --- tray menu ---
    def status(self) -> dict:
        return {"model": self.models.label, "bytes": self.store.total_bytes(),
                "logging": self.pipeline.logging, "keep_loaded": self.models.keep_loaded}

    def toggle_logging(self) -> None:
        self.pipeline.logging = not self.pipeline.logging

    def toggle_keep_loaded(self) -> None:
        self.models.keep_loaded = not self.models.keep_loaded

    def unload(self) -> None:
        # Waits for any dictation in progress, so keep it off the UI and tray threads.
        threading.Thread(target=self.models.unload, daemon=True).start()

    def open_data(self) -> None:
        self.opener(str(self.store_dir))

    def open_corrections(self) -> None:
        self._open_corrections_window(self.root, self.store)

    def start(self, tick_ms: int = TICK_MS) -> None:
        self.tray.start()

        def tick():
            if self.stopping:
                return
            self.models.tick()
            self.root.after(tick_ms, tick)

        self.root.after(tick_ms, tick)

    def quit(self) -> None:
        self.stopping = True
        self.tray.stop()
        self.call_soon(self.root.quit)
        self.root.after(0, self._pump)


def main() -> None:
    import winsound

    from voicetool.config import load_config
    from voicetool.hotkeys import HotkeyMachine
    from voicetool.model_manager import ModelManager
    from voicetool.pipeline import Pipeline
    from voicetool.recorder import Recorder
    from voicetool.store import Store
    from voicetool.transcriber import load_model, transcribe
    from voicetool.win.keyboard import start_listener
    from voicetool.win.paste import deliver, foreground
    from voicetool.win.tray import Tray

    mutex = acquire_single_instance()
    if mutex is None:
        win32api.MessageBox(0, "Voice Tool is already running (see the tray).", "Voice Tool")
        return

    cfg = load_config()
    root = tk.Tk()
    root.withdraw()
    store = Store(DATA_DIR)
    models = ModelManager(lambda: load_model(cfg), cfg.idle_unload_minutes * 60)
    models.keep_loaded = cfg.keep_loaded

    def beep(kind: str) -> None:
        threading.Thread(target=winsound.Beep, args=beep_tone(kind), daemon=True).start()

    app = App(
        cfg, root, store, models,
        make_pipeline=lambda a: Pipeline(cfg, Recorder(), models, store, deliver, foreground,
                                         transcribe, a.notify, beep, a.set_state),
        make_tray=lambda a: Tray(a.status, a.toggle_logging, a.unload, a.toggle_keep_loaded,
                                 a.open_data, lambda: a.call_soon(a.open_corrections), a.quit),
    )
    machine = HotkeyMachine(cfg.talk_key, cfg.corrections_key, cfg.delete_last_key)
    listener = start_listener(machine, app.pipeline.on_event)
    app.start()
    try:
        root.mainloop()
    finally:
        listener.stop()
