from types import SimpleNamespace

import numpy as np

from voicetool import transcriber
from voicetool.config import Config


class FakeWhisper:
    created = []
    fail_on_device = None

    not_cached = False
    local_flags = []

    def __init__(self, name, device, compute_type, download_root, local_files_only=False):
        FakeWhisper.local_flags.append(local_files_only)
        if device == FakeWhisper.fail_on_device:
            raise RuntimeError("no CUDA")
        if local_files_only and FakeWhisper.not_cached:
            raise FileNotFoundError("not downloaded yet")
        FakeWhisper.created.append((name, device, compute_type))
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        segs = [SimpleNamespace(text=" Hello"), SimpleNamespace(text=" world. ")]
        return iter(segs), SimpleNamespace(duration=1.0)


def setup_function():
    FakeWhisper.created = []
    FakeWhisper.fail_on_device = None
    FakeWhisper.not_cached = False
    FakeWhisper.local_flags = []


def test_load_model_uses_gpu(monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", FakeWhisper)
    _, label = transcriber.load_model(Config())
    assert FakeWhisper.created == [("large-v3-turbo", "cuda", "float16")]
    assert label == "large-v3-turbo (GPU)"


def test_load_model_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", FakeWhisper)
    FakeWhisper.fail_on_device = "cuda"
    _, label = transcriber.load_model(Config())
    assert FakeWhisper.created == [("small", "cpu", "int8")]
    assert label == "small (CPU fallback)"


def test_transcribe_joins_segments_and_biases_vocabulary():
    m = FakeWhisper("x", "cpu", "int8", None)
    cfg = Config(vocabulary=["Vezras", "pm2"])
    text = transcriber.transcribe(m, np.zeros(16000, np.float32), cfg)
    assert text == "Hello world."
    assert m.kwargs["initial_prompt"] == "Vezras, pm2."
    assert m.kwargs["language"] == "en" and m.kwargs["vad_filter"] is True
    assert m.kwargs["beam_size"] == 5


def test_transcribe_without_vocabulary_has_no_prompt():
    m = FakeWhisper("x", "cpu", "int8", None)
    transcriber.transcribe(m, np.zeros(16000, np.float32), Config(vocabulary=[]))
    assert m.kwargs["initial_prompt"] is None


def test_load_model_stays_offline_when_cached(monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", FakeWhisper)
    transcriber.load_model(Config())
    assert FakeWhisper.local_flags == [True]


def test_load_model_downloads_only_when_missing(monkeypatch):
    monkeypatch.setattr(transcriber, "WhisperModel", FakeWhisper)
    FakeWhisper.not_cached = True
    _, label = transcriber.load_model(Config())
    assert FakeWhisper.local_flags == [True, False] and label == "large-v3-turbo (GPU)"
