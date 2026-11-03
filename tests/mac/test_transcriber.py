from pathlib import Path

import numpy as np
import pytest

from voicetool.config import MODELS_DIR, Config
from voicetool.mac import transcriber


class FakeHolder:
    model = None
    model_path = None
    loads = []

    @classmethod
    def get_model(cls, path, dtype):
        cls.loads.append(path)
        cls.model, cls.model_path = "weights", path
        return cls.model


class FakeMlxWhisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        return {"text": "  hello from the mac  "}


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    FakeHolder.model = FakeHolder.model_path = None
    FakeHolder.loads = []
    mw = FakeMlxWhisper()
    cleared = []
    monkeypatch.setattr(transcriber, "mlx_whisper", mw)
    monkeypatch.setattr(transcriber, "ModelHolder", FakeHolder)
    monkeypatch.setattr(transcriber, "clear_cache", lambda: cleared.append(True))
    monkeypatch.setattr(transcriber, "MODELS_DIR", tmp_path)
    (tmp_path / "whisper-small.en-mlx").mkdir()
    return mw, cleared, tmp_path


def test_load_reads_the_model_from_the_models_folder(fakes):
    _, _, models = fakes
    model, label = transcriber.load_model(Config(model_name="whisper-small.en-mlx"))
    assert FakeHolder.loads == [str(models / "whisper-small.en-mlx")]
    assert model.path == models / "whisper-small.en-mlx"
    assert label == "whisper-small.en-mlx (Apple GPU)"


def test_missing_model_says_how_to_download_it(fakes):
    with pytest.raises(FileNotFoundError, match="hf download mlx-community/whisper-tiny"):
        transcriber.load_model(Config(model_name="whisper-tiny"))


def test_transcribe_passes_vocabulary_and_language_and_strips(fakes):
    mw, _, _ = fakes
    model, _ = transcriber.load_model(Config(model_name="whisper-small.en-mlx"))
    cfg = Config(model_name="whisper-small.en-mlx", vocabulary=["Vezras", "pm2"], language="en")
    assert transcriber.transcribe(model, np.zeros(16000, np.float32), cfg) == "hello from the mac"
    call = mw.calls[0]
    assert call["path_or_hf_repo"] == str(model.path)
    assert call["initial_prompt"] == "Vezras, pm2."
    assert call["language"] == "en"
    assert call["condition_on_previous_text"] is False


def test_release_frees_mlx_memory(fakes):
    _, cleared, _ = fakes
    model, _ = transcriber.load_model(Config(model_name="whisper-small.en-mlx"))
    transcriber.release(model)
    assert FakeHolder.model is None and FakeHolder.model_path is None
    assert cleared == [True]


@pytest.mark.mac
def test_real_model_transcribes_speech():
    import soundfile as sf
    from voicetool.config import load_config
    cfg = load_config()
    wav = Path(__file__).parent / "speech_sample.wav"
    if not wav.exists():
        pytest.skip("record tests/mac/speech_sample.wav first")
    audio, sr = sf.read(wav, dtype="float32")
    assert sr == 16000
    model, _ = transcriber.load_model(cfg)
    assert transcriber.transcribe(model, audio, cfg).strip()
    transcriber.release(model)


def test_segments_whisper_rates_as_not_speech_are_dropped(fakes):
    mw, _, _ = fakes
    mw.transcribe = lambda audio, **kw: {"text": " Deploy it. Thank you.", "segments": [
        {"text": " Deploy it.", "no_speech_prob": 0.05},
        {"text": " Thank you.", "no_speech_prob": 0.92}]}
    model, _ = transcriber.load_model(Config(model_name="whisper-small.en-mlx"))
    assert transcriber.transcribe(model, np.zeros(16000, np.float32), Config()) == "Deploy it."


def test_pure_hallucination_on_silence_gives_nothing(fakes):
    mw, _, _ = fakes
    mw.transcribe = lambda audio, **kw: {"text": " Thank you.", "segments": [
        {"text": " Thank you.", "no_speech_prob": 0.8}]}
    model, _ = transcriber.load_model(Config(model_name="whisper-small.en-mlx"))
    assert transcriber.transcribe(model, np.zeros(16000, np.float32), Config()) == ""


@pytest.mark.mac
def test_real_model_works_across_threads():
    # The app loads on one thread, transcribes on the pipeline worker, releases on a timer.
    import threading
    import soundfile as sf
    from voicetool.config import load_config
    cfg = load_config()
    audio, _ = sf.read(Path(__file__).parent / "speech_sample.wav", dtype="float32")
    box = {}
    def on_thread(fn):
        t = threading.Thread(target=lambda: box.update(r=fn()))
        t.start(); t.join()
        return box.pop("r", None)
    model, _ = on_thread(lambda: transcriber.load_model(cfg))
    assert on_thread(lambda: transcriber.transcribe(model, audio, cfg)).strip()
    assert on_thread(lambda: transcriber.transcribe(model, audio, cfg)).strip()
    on_thread(lambda: transcriber.release(model))
