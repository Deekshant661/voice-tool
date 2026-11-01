"""Whole chain with real parts: GPU Whisper, store, clipboard and paste into a real window.
Only the microphone is replaced, by Windows' built-in voice."""
import threading
import time

import pytest

from tests.conftest import force_foreground
from tests.test_transcriber_gpu import _read_16k, _speak
from voicetool.config import Config
from voicetool.model_manager import ModelManager
from voicetool.pipeline import Pipeline
from voicetool.store import Store


class SpokenRecorder:
    def __init__(self, audio):
        self.audio = audio

    def start(self):
        pass

    def stop(self):
        return self.audio

    def cancel(self):
        pass


@pytest.mark.gpu
@pytest.mark.win
def test_dictation_lands_in_window_and_store(tmp_path, root):
    import tkinter as tk
    from voicetool.transcriber import load_model, transcribe
    from voicetool.win.paste import deliver, foreground, get_clipboard_text, set_clipboard_text

    wav = tmp_path / "s.wav"
    _speak(wav)
    cfg = Config(vocabulary=["Vezras", "RDS", "pm2", "GitLab", "Postgres"])
    store = Store(tmp_path / "data")
    models = ModelManager(lambda: load_model(cfg), 60)
    notes = []
    p = Pipeline(cfg, SpokenRecorder(_read_16k(wav)), models, store, deliver, foreground,
                 transcribe, notes.append, lambda kind: None)

    win = tk.Toplevel(root)
    entry = tk.Entry(win, width=120)
    entry.pack()
    hwnd = force_foreground(win, root)
    entry.focus_force()
    root.update()
    assert foreground()[0] == hwnd, "test window did not get focus"

    set_clipboard_text("before")
    p.on_event("start")
    p.on_event("stop")
    done = threading.Event()
    threading.Thread(target=lambda: (p.drain(60), done.set()), daemon=True).start()
    while not done.is_set():
        root.update(); time.sleep(0.01)
    for _ in range(10):
        root.update(); time.sleep(0.02)

    text = entry.get()
    win.destroy()
    models.unload()  # free the 4 GB card; a second resident model spills to RAM and runs ~5x slower
    assert notes == []
    for word in ("Postgres", "pm2", "GitLab"):
        assert word in text
    assert get_clipboard_text() == "before"
    saved = store.recent(1)[0]
    assert saved.cleaned_text == text and saved.audio_path.exists()
