"""Microphone capture straight to 16 kHz mono float32, the format Whisper wants."""
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class RecorderError(Exception):
    pass


def too_short(audio: np.ndarray, min_seconds: float, samplerate: int = SAMPLE_RATE) -> bool:
    return len(audio) < min_seconds * samplerate


class Recorder:
    def __init__(self, samplerate: int = SAMPLE_RATE):
        self.samplerate = samplerate
        self._stream = None
        self._blocks: list[np.ndarray] = []
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._blocks.append(indata[:, 0].copy())

    def start(self) -> None:
        self._close()
        with self._lock:
            self._blocks = []
        try:
            self._stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                          callback=self._callback)
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
