"""The shared recorder, rebuilt so closing the mic can't freeze the tool. Inside the app,
CoreAudio sometimes never returned from stopping a stream that called back into Python, and the
control thread waited on it forever (the mic stayed on too). Here a plain thread reads the mic
instead, so CoreAudio never waits on Python, and the close happens off the control thread."""
import threading

import numpy as np
import sounddevice as sd

from voicetool.recorder import SAMPLE_RATE, Recorder, RecorderError

BLOCK = SAMPLE_RATE // 10  # 0.1 s per read


class MacRecorder(Recorder):
    def __init__(self, samplerate: int = SAMPLE_RATE, device: int | None = None):
        super().__init__(samplerate, device)
        self._reading: threading.Event | None = None
        self._reader: threading.Thread | None = None

    def start(self) -> None:
        self._close()
        try:
            stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                    device=self.device, blocksize=BLOCK)
            stream.start()
        except Exception as e:  # no device, device busy, driver error
            raise RecorderError(str(e)) from e
        blocks: list[np.ndarray] = []
        reading = threading.Event(); reading.set()
        self._stream, self._blocks, self._reading = stream, blocks, reading

        def read():
            try:
                while reading.is_set():
                    data, _ = stream.read(BLOCK)
                    if reading.is_set():  # this recording's own list: nothing leaks into the next
                        blocks.append(data[:, 0].copy())
            except Exception:
                pass  # the stream died; stop() returns what we have
            finally:
                try:
                    stream.stop(); stream.close()
                except Exception:
                    pass

        self._reader = threading.Thread(target=read, daemon=True, name="mic")
        self._reader.start()

    def _close(self) -> None:
        if self._reading is None:
            return
        self._reading.clear()
        self._reader.join(0.3)  # one read is 0.1 s; the stream closes on that thread, not ours
        self._stream = self._reading = self._reader = None
