import time

import numpy as np
import pytest

from voicetool import recorder as rec
from voicetool.recorder import Recorder, RecorderError, too_short


def test_too_short():
    assert too_short(np.zeros(4000, np.float32), 0.3) is True
    assert too_short(np.zeros(4800, np.float32), 0.3) is False


def test_stop_without_start_is_empty():
    assert Recorder().stop().size == 0


class FakeStream:
    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.kwargs = kwargs
        self.closed = False

    def start(self):
        block = np.full((1600, 1), 0.5, dtype=np.float32)
        self.callback(block, 1600, None, None)
        self.callback(block, 1600, None, None)

    def stop(self):
        pass

    def close(self):
        self.closed = True


def test_collects_blocks_as_mono_16k(monkeypatch):
    made = []
    monkeypatch.setattr(rec.sd, "InputStream", lambda **kw: made.append(FakeStream(**kw)) or made[-1])
    r = Recorder()
    r.start()
    a = r.stop()
    assert a.dtype == np.float32 and a.ndim == 1 and a.size == 3200
    assert made[0].kwargs["samplerate"] == 16000 and made[0].kwargs["channels"] == 1
    assert made[0].closed


def test_cancel_discards(monkeypatch):
    monkeypatch.setattr(rec.sd, "InputStream", lambda **kw: FakeStream(**kw))
    r = Recorder()
    r.start()
    r.cancel()
    assert r.stop().size == 0


def test_open_failure_raises_recorder_error(monkeypatch):
    def boom(**kw):
        raise rec.sd.PortAudioError("no device")
    monkeypatch.setattr(rec.sd, "InputStream", boom)
    with pytest.raises(RecorderError):
        Recorder().start()


def test_restart_starts_fresh(monkeypatch):
    monkeypatch.setattr(rec.sd, "InputStream", lambda **kw: FakeStream(**kw))
    r = Recorder()
    r.start(); r.stop()
    r.start()
    assert r.stop().size == 3200


@pytest.mark.mic
def test_records_something():
    r = Recorder()
    r.start()
    time.sleep(0.5)
    a = r.stop()
    assert a.dtype == np.float32 and a.ndim == 1 and a.size > 6000
