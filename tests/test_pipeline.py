import threading
import time
from contextlib import contextmanager

import numpy as np

from voicetool.config import Config
from voicetool.pipeline import Pipeline
from voicetool.recorder import RecorderError
from voicetool.win.paste import PasteResult

SR = 16000


class FakeRecorder:
    def __init__(self):
        self.next_audio = [np.zeros(SR, np.float32)]
        self.fail_next_start = False
        self.fail_next_stop = False
        self.start_sleep = 0.0
        self.cancelled = 0

    def start(self):
        time.sleep(self.start_sleep)
        if self.fail_next_start:
            self.fail_next_start = False
            raise RecorderError("no device")

    def stop(self):
        if self.fail_next_stop:
            self.fail_next_stop = False
            raise OSError("device unplugged")
        return self.next_audio.pop(0) if self.next_audio else np.zeros(SR, np.float32)

    def cancel(self):
        self.cancelled += 1


class FakeModels:
    def __init__(self):
        self.loading_requested = 0

    def ensure_loading(self):
        self.loading_requested += 1

    @contextmanager
    def use(self):
        yield "model"


class FakeStore:
    def __init__(self):
        self.added = []
        self.deleted = 0
        self.size = 0
        self.has_rows = True
        self.ops = []

    def add(self, audio, raw, cleaned, title, process):
        self.ops.append("add")
        self.added.append((raw, cleaned, title, process))
        return len(self.added)

    def delete_last(self):
        self.ops.append("delete_last")
        self.deleted += 1
        return self.has_rows

    def total_bytes(self):
        return self.size


class Harness:
    def __init__(self, **cfg):
        self.cfg = Config(**{"replacements": {"pm 2": "pm2"}, **cfg})
        self.recorder = FakeRecorder()
        self.models = FakeModels()
        self.store = FakeStore()
        self.transcripts = []
        self.delivered = []
        self.deliver_result = PasteResult.PASTED
        self.deliver_sleep = 0.0
        self.deliver_error = None
        self.active = 0
        self.overlap = False
        self.notes = []
        self.beeps = []
        self.states = []
        self.p = Pipeline(self.cfg, self.recorder, self.models, self.store, self.deliver,
                          lambda: (42, "Notepad", "notepad.exe"), self.transcribe,
                          self.notes.append, self.beeps.append, self.states.append)

    def transcribe(self, model, audio, cfg):
        item = self.transcripts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def deliver(self, text, hwnd):
        self.active += 1
        if self.active > 1:
            self.overlap = True
        time.sleep(self.deliver_sleep)
        if self.deliver_error:
            self.active -= 1
            raise self.deliver_error
        self.delivered.append((text, hwnd))
        self.active -= 1
        return self.deliver_result

    def dictate(self, transcript, seconds=1.0):
        self.recorder.next_audio = [np.zeros(int(SR * seconds), np.float32)]
        self.transcripts.append(transcript)
        self.p.on_event("start")
        self.p.on_event("stop")


def test_happy_path_pastes_and_stores():
    h = Harness()
    h.dictate("um, restart pm 2")
    h.p.drain(2)
    assert h.delivered == [("Restart pm2", 42)]
    assert h.store.added == [("um, restart pm 2", "Restart pm2", "Notepad", "notepad.exe")]
    assert h.models.loading_requested == 1
    assert h.beeps == ["start", "stop"]


def test_short_tap_does_nothing():
    h = Harness()
    h.dictate("should not be used", seconds=0.1)
    h.p.drain(2)
    assert h.delivered == [] and h.store.added == [] and h.transcripts == ["should not be used"]


def test_empty_transcript_does_nothing():
    h = Harness()
    h.dictate("")
    h.p.drain(2)
    assert h.delivered == [] and h.store.added == []


def test_filler_only_transcript_does_nothing():
    h = Harness()
    h.dictate("Um.")
    h.p.drain(2)
    assert h.delivered == [] and h.store.added == []


def test_logging_off_skips_store():
    h = Harness(logging=False)
    h.dictate("hello")
    h.p.drain(2)
    assert h.delivered == [("Hello", 42)] and h.store.added == []


def test_logging_toggle_at_runtime():
    h = Harness()
    h.p.logging = False
    h.dictate("hello")
    h.p.drain(2)
    assert h.store.added == []


def test_cancel_discards():
    h = Harness()
    h.p.on_event("start")
    h.p.on_event("cancel")
    h.p.drain(2)
    assert h.recorder.cancelled == 1 and h.delivered == []


def test_focus_moved_notifies():
    h = Harness()
    h.deliver_result = PasteResult.COPIED_FOCUS_MOVED
    h.dictate("hello")
    h.p.drain(2)
    assert any("focus moved" in n for n in h.notes)


def test_elevated_notifies():
    h = Harness()
    h.deliver_result = PasteResult.COPIED_ELEVATED
    h.dictate("hello")
    h.p.drain(2)
    assert any("admin" in n for n in h.notes)


def test_dictations_run_serially():
    h = Harness()
    h.deliver_sleep = 0.2
    h.dictate("first")
    h.dictate("second")
    h.p.drain(3)
    assert [t for t, _ in h.delivered] == ["First", "Second"] and not h.overlap


def test_recorder_error_notifies_and_recovers():
    h = Harness()
    h.recorder.fail_next_start = True
    h.transcripts.append("ignored")
    h.p.on_event("start")
    h.p.on_event("stop")
    h.p.drain(2)
    assert any("Microphone unavailable" in n for n in h.notes) and h.delivered == []
    h.transcripts.clear()
    h.dictate("works again")
    h.p.drain(2)
    assert h.delivered == [("Works again", 42)]


def test_worker_survives_exception():
    h = Harness()
    h.dictate(RuntimeError("cuda died"))
    h.dictate("still alive")
    h.p.drain(2)
    assert any("Dictation failed: cuda died" in n for n in h.notes)
    assert h.delivered == [("Still alive", 42)]


def test_size_warning_once():
    h = Harness(warn_gb=1)
    h.store.size = 2e9
    h.dictate("one")
    h.dictate("two")
    h.p.drain(2)
    assert len([n for n in h.notes if "GB" in n]) == 1


def test_delete_last():
    h = Harness()
    h.p.on_event("delete_last")
    h.p.drain(2)
    assert h.store.deleted == 1 and h.notes == ["Deleted last recording"]


def test_delete_last_when_empty():
    h = Harness()
    h.store.has_rows = False
    h.p.on_event("delete_last")
    h.p.drain(2)
    assert h.notes == ["Nothing to delete"]


def test_corrections_calls_hook():
    h = Harness()
    opened = []
    h.p.open_corrections = lambda: opened.append(1)
    h.p.on_event("corrections")
    h.p.drain(2)
    assert opened == [1]


def test_states_follow_dictation():
    h = Harness()
    h.dictate("hello")
    h.p.drain(2)
    assert h.states[0] == "recording" and "working" in h.states and h.states[-1] == "idle"


def test_cancel_returns_to_idle():
    h = Harness()
    h.p.on_event("start")
    h.p.on_event("cancel")
    h.p.drain(2)
    assert h.states == ["recording", "idle"]


def test_failed_dictation_is_logged_with_traceback(caplog):
    import logging
    h = Harness()
    with caplog.at_level(logging.ERROR, logger="voicetool"):
        h.dictate(RuntimeError("cuda died"))
        h.p.drain(2)
    assert any("cuda died" in r.getMessage() and r.exc_info for r in caplog.records)


def test_slow_mic_does_not_block_the_keyboard_hook():
    h = Harness()
    h.recorder.start_sleep = 0.3
    t = time.monotonic()
    h.p.on_event("start")
    assert time.monotonic() - t < 0.05
    h.p.on_event("stop")
    h.transcripts.append("hello")
    h.p.drain(2)
    assert h.delivered == [("Hello", 42)]


def test_event_error_is_reported_and_hotkey_keeps_working(caplog):
    import logging
    h = Harness()
    h.recorder.fail_next_stop = True
    with caplog.at_level(logging.ERROR, logger="voicetool"):
        h.p.on_event("start")
        h.p.on_event("stop")
        h.p.drain(2)
    assert any("device unplugged" in n for n in h.notes)
    assert any("device unplugged" in r.getMessage() for r in caplog.records)
    h.dictate("works again")
    h.p.drain(2)
    assert h.delivered == [("Works again", 42)]


def test_delete_last_waits_for_pending_dictation():
    # Say something sensitive, then delete it straight away: the new one must be deleted.
    h = Harness()
    h.deliver_sleep = 0.3
    h.dictate("my password is hunter2")
    h.p.on_event("delete_last")
    h.p.drain(3)
    assert h.store.ops == ["add", "delete_last"]


def test_failed_paste_still_saves_and_shows_text():
    h = Harness()
    h.deliver_error = OSError("clipboard locked")
    h.dictate("important note")
    h.p.drain(2)
    assert h.store.added and h.store.added[0][1] == "Important note"
    assert any("Important note" in n and "clipboard locked" in n for n in h.notes)
