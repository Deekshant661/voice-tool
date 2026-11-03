"""Wires everything together on macOS. Threads: the menu bar (AppKit) owns the main thread,
pynput listens on its own, and the pipeline has its control and worker threads."""
import fcntl
import logging
import logging.handlers
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from voicetool.config import APP_DIR, DATA_DIR, Config

LOG_PATH = APP_DIR / "voicetool.log"
LOCK_PATH = APP_DIR / "voicetool.lock"
TICK_S = 30
QUIT_WAIT_S = 2.0
SOUNDS = {"start": "/System/Library/Sounds/Pop.aiff", "stop": "/System/Library/Sounds/Tink.aiff"}
log = logging.getLogger("voicetool")


def setup_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=1,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    sys.excepthook = lambda t, e, tb: log.error("Uncaught error", exc_info=(t, e, tb))
    threading.excepthook = lambda a: log.error(
        "Uncaught error in thread %s", a.thread.name if a.thread else "?",
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def acquire_single_instance(path: Path = LOCK_PATH):
    """Returns the open lock file (keep it open while running), or None if already running."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def beep(kind: str, run: Callable[[list[str]], object] = subprocess.Popen) -> None:
    run(["afplay", SOUNDS[kind]])  # Popen returns at once; the sound plays on its own


class MacApp:
    def __init__(self, cfg: Config, store, models, pipeline, bar, launcher, listener,
                 release: Callable[[], None], run: Callable[[list[str]], object] = subprocess.Popen):
        self.cfg, self.store, self.models, self.pipeline = cfg, store, models, pipeline
        self.bar, self.launcher, self.listener = bar, launcher, listener
        self.data_dir = DATA_DIR
        self._release = release
        self._run = run

    def status(self) -> dict:
        return {"model": self.models.label, "bytes": self.store.total_bytes(),
                "logging": self.pipeline.logging, "keep_loaded": self.models.keep_loaded}

    def toggle_logging(self) -> None:
        self.pipeline.logging = not self.pipeline.logging

    def toggle_keep_loaded(self) -> None:
        self.models.keep_loaded = not self.models.keep_loaded

    def tick(self) -> None:
        if self.models.tick():
            self._release()

    def unload(self, wait: bool = False) -> None:
        def run():
            self.models.unload()  # waits for any dictation in progress
            self._release()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        if wait:
            t.join()

    def open_data(self) -> None:
        self._run(["open", str(self.data_dir)])

    def open_corrections(self) -> None:
        self.launcher.open()

    def quit(self) -> None:
        self.listener.stop()
        self.pipeline.drain(QUIT_WAIT_S)  # let a dictation finish pasting and restore the clipboard
        self.bar.stop()


def main() -> None:
    import rumps

    from voicetool.config import load_config
    from voicetool.hotkeys import HotkeyMachine
    from voicetool.mac import paste
    from voicetool.mac.corrections import CorrectionsLauncher
    from voicetool.mac.keyboard import start_listener
    from voicetool.mac.menubar import MenuBar
    from voicetool.mac.transcriber import load_model, release, transcribe
    from voicetool.model_manager import ModelManager
    from voicetool.pipeline import Pipeline
    from voicetool.recorder import Recorder, RecorderError, find_input_device
    from voicetool.store import Store

    setup_log(LOG_PATH)
    log.info("starting")
    lock = acquire_single_instance()
    if lock is None:
        log.info("already running, exiting")
        print("Voice Tool is already running (see the menu bar).")
        return

    cfg = load_config()
    store = Store(DATA_DIR)
    models = ModelManager(lambda: load_model(cfg), cfg.idle_unload_minutes * 60)
    models.keep_loaded = cfg.keep_loaded
    mic_problem = None
    try:
        device = find_input_device(cfg.input_device)
    except RecorderError as e:
        device, mic_problem = None, f"{e}. Using the default microphone."

    holder: dict = {}
    bar = MenuBar(lambda: holder["app"].status(), {
        "logging": lambda: holder["app"].toggle_logging(),
        "keep": lambda: holder["app"].toggle_keep_loaded(),
        "unload": lambda: holder["app"].unload(),
        "corrections": lambda: holder["app"].open_corrections(),
        "data": lambda: holder["app"].open_data(),
        "quit": lambda: holder["app"].quit(),
    })
    pipeline = Pipeline(cfg, Recorder(device=device), models, store, paste.deliver,
                        paste.foreground, transcribe, bar.notify, beep, bar.set_state,
                        notices=paste.MAC_NOTICES)
    launcher = CorrectionsLauncher()
    pipeline.open_corrections = launcher.open
    machine = HotkeyMachine(cfg.talk_key, cfg.corrections_key, cfg.delete_last_key)
    listener, full = start_listener(machine, pipeline.on_event)
    app = MacApp(cfg, store, models, pipeline, bar, launcher, listener, release)
    holder["app"] = app
    models.on_loaded = lambda label: log.info("model loaded: %s", label)
    rumps.Timer(lambda _: app.tick(), TICK_S).start()

    log.info("ready: hold %s to dictate; microphone: %s; accessibility: %s",
             cfg.talk_key, pipeline.recorder.device_name, "yes" if full else "NO")
    if not full:
        bar.notify("Accessibility is off for this terminal: dictation works, but pasting and "
                   "Option shortcuts won't. Enable it in System Settings, then restart.")
    if mic_problem:
        bar.notify(mic_problem)
    try:
        bar.start()
    finally:
        listener.stop()
        lock.close()
