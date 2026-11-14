import threading
import time

import numpy as np

from voicetool.mac import recorder as mac_recorder


class FakeStream:
    """Hands out 0.1 s blocks of ones. hang=True: CoreAudio never returns from closing."""
    instances = []
    hang = False

    def __init__(self, *a, **kw):
        assert "callback" not in kw  # a Python callback is what deadlocked the close
        self.closed = False
        FakeStream.instances.append(self)
    def start(self): pass
    def read(self, frames):
        time.sleep(0.01)
        return np.ones((frames, 1), np.float32), False
    def stop(self):
        if FakeStream.hang: threading.Event().wait()
    abort = stop
    def close(self): self.closed = True


def make(monkeypatch, hang):
    FakeStream.instances, FakeStream.hang = [], hang
    monkeypatch.setattr(mac_recorder.sd, "InputStream", FakeStream)
    return mac_recorder.MacRecorder()


def test_recording_then_stop_returns_the_audio_and_closes_the_mic(monkeypatch):
    r = make(monkeypatch, hang=False)
    r.start(); time.sleep(0.1)
    audio = r.stop()
    assert len(audio) > 0 and len(audio) % 1600 == 0
    time.sleep(0.05)
    assert FakeStream.instances[0].closed


def test_a_mic_that_never_closes_does_not_freeze_the_tool(monkeypatch):
    r = make(monkeypatch, hang=True)
    t = time.monotonic()
    r.start(); time.sleep(0.05)
    assert len(r.stop()) > 0
    r.start()            # the next dictation still works
    time.sleep(0.05)
    second = r.stop()
    assert time.monotonic() - t < 1
    # nothing from the first recording leaks into the second
    assert len(second) < 1600 * 10
