"""Microphone capture straight to 16 kHz mono float32, the format Whisper wants."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
# Peak level below which a recording is treated as "the mic sent nothing". Measured: an idle
# virtual mic (Voicemod not running) peaks at 0.00003; quiet real speech on the laptop mic ~0.01.
SILENCE_PEAK = 0.001


class RecorderError(Exception):
    pass


def too_short(audio: np.ndarray, min_seconds: float, samplerate: int = SAMPLE_RATE) -> bool:
    return len(audio) < min_seconds * samplerate


def is_silent(audio: np.ndarray) -> bool:
    return audio.size == 0 or float(np.abs(audio).max()) < SILENCE_PEAK


def find_input_device(name: str) -> int | None:
    """Index of the first input device whose name contains `name` (case-insensitive).
    Empty name means the Windows default. The first match is the MME one, which accepts 16 kHz."""
    if not name:
        return None
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and name.lower() in dev["name"].lower():
            return index
    raise RecorderError(f"No microphone matching '{name}' — check input_device in config.toml")


class Recorder:
    def __init__(self, samplerate: int = SAMPLE_RATE, device: int | None = None):
        self.samplerate = samplerate
        self.device = device
        self._stream = None
        self._blocks: list[np.ndarray] = []
        self._lock = threading.Lock()

    @property
    def device_name(self) -> str:
        try:
            if self.device is None:
                return sd.query_devices(kind="input")["name"]
            return sd.query_devices(self.device)["name"]
        except Exception:
            return "unknown microphone"

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._blocks.append(indata[:, 0].copy())

    def start(self) -> None:
        self._close()
        with self._lock:
            self._blocks = []
        try:
            self._stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                          device=self.device, callback=self._callback)
            self._stream.start()
        except Exception as e:  # no device, device busy, driver error
            self._stream = None
            raise RecorderError(str(e)) from e

    def stop(self) -> np.ndarray:
        self._close()
        with self._lock:
            blocks, self._blocks = self._blocks, []
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(blocks).astype(np.float32)

    def cancel(self) -> None:
        self._close()
        with self._lock:
            self._blocks = []

    def _close(self) -> None:
        if self._stream is not None:
            stream, self._stream = self._stream, None
            stream.stop()
            stream.close()
