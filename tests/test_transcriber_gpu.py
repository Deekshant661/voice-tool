import subprocess
import time
import wave

import numpy as np
import pytest

from voicetool.config import Config

SENTENCE = ("Please check the Postgres database on the demo box, then restart pm2 "
            "and send the team a short update about the GitLab backup.")


def _speak(path):
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{SENTENCE}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def _read_16k(path):
    with wave.open(str(path)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        raw = raw.reshape(-1, ch).mean(axis=1)
    out_len = int(len(raw) * 16000 / sr)
    return np.interp(np.linspace(0, len(raw) - 1, out_len), np.arange(len(raw)), raw).astype(np.float32)


@pytest.mark.gpu
def test_real_transcription_on_gpu(tmp_path):
    from voicetool.transcriber import load_model, transcribe
    wav = tmp_path / "s.wav"
    _speak(wav)
    audio = _read_16k(wav)
    cfg = Config(vocabulary=["Vezras", "RDS", "pm2", "GitLab", "Postgres"])
    model, label = load_model(cfg)
    assert "GPU" in label
    transcribe(model, audio, cfg)  # warm-up
    t = time.time()
    text = transcribe(model, audio, cfg)
    assert time.time() - t < 2.0
    for word in ("Postgres", "pm2", "GitLab"):
        assert word in text
