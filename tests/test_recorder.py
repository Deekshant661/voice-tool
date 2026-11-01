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


DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0},
    {"name": "Microphone (Voicemod)", "max_input_channels": 2, "hostapi": 0},
    {"name": "Microphone Array (Intel Smart Sound)", "max_input_channels": 2, "hostapi": 0},
    {"name": "Speakers", "max_input_channels": 0, "hostapi": 0},
    {"name": "Microphone Array (Intel Smart Sound)", "max_input_channels": 2, "hostapi": 1},
]


def test_find_input_device_by_name(monkeypatch):
    from voicetool.recorder import find_input_device
    monkeypatch.setattr(rec.sd, "query_devices", lambda: DEVICES)
    assert find_input_device("microphone array") == 2   # case-insensitive, first (MME) match
    assert find_input_device("") is None                 # empty = Windows default
    with pytest.raises(RecorderError):                   # a speaker is not a microphone
        find_input_device("Speakers")


def test_find_input_device_missing_raises(monkeypatch):
    from voicetool.recorder import find_input_device
    monkeypatch.setattr(rec.sd, "query_devices", lambda: DEVICES)
    with pytest.raises(RecorderError, match="No microphone matching 'USB headset'"):
        find_input_device("USB headset")


def test_recorder_uses_chosen_device(monkeypatch):
    made = []
    monkeypatch.setattr(rec.sd, "InputStream", lambda **kw: made.append(FakeStream(**kw)) or made[-1])
    r = Recorder(device=2)
    r.start(); r.stop()
    assert made[0].kwargs["device"] == 2


def test_is_silent():
    from voicetool.recorder import is_silent
    assert is_silent(np.zeros(16000, np.float32))
    assert is_silent(np.full(16000, 0.00003, np.float32))   # what the idle Voicemod mic gave
    assert not is_silent(np.full(16000, 0.0106, np.float32))  # quiet real speech
    assert is_silent(np.zeros(0, np.float32))


@pytest.mark.mic
def test_default_microphone_actually_hears_sound():
    # Catches a muted mic or a virtual mic with nothing behind it. Speak while it runs.
    from voicetool.config import load_config
    from voicetool.recorder import find_input_device, is_silent
    r = Recorder(device=find_input_device(load_config().input_device))
    r.start()
    time.sleep(3)
    assert not is_silent(r.stop()), "the configured microphone delivered silence"
