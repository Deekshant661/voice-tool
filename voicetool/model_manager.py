"""Loads the speech model on demand and frees the GPU after a period of no use."""
import gc
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator


class ModelManager:
    def __init__(self, loader: Callable[[], tuple[object, str]], idle_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._idle_seconds = idle_seconds
        self._clock = clock
        self._cond = threading.Condition()
        self._model: object | None = None
        self._loading = False
        self._error: BaseException | None = None
        self._in_use = 0
        self._last_used = clock()
        self.keep_loaded = False
        self.label: str | None = None
        self.on_loaded: Callable[[str], None] | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def ensure_loading(self) -> None:
        with self._cond:
            if self._model is not None or self._loading:
                return
            self._loading = True
            self._error = None
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            model, label = self._loader()
        except BaseException as e:  # surfaced to the waiting user of the model
            with self._cond:
                self._loading = False
                self._error = e
                self._cond.notify_all()
            return
        with self._cond:
            self._model, self.label = model, label
            self._loading = False
            self._last_used = self._clock()
            self._cond.notify_all()
        if self.on_loaded:
            self.on_loaded(label)

    @contextmanager
    def use(self) -> Iterator[object]:
        self.ensure_loading()
        with self._cond:
            while self._model is None and self._loading:
                self._cond.wait()
            if self._model is None:
                error, self._error = self._error, None
                raise error or RuntimeError("model failed to load")
            self._in_use += 1
            model = self._model
        try:
            yield model
        finally:
            with self._cond:
                self._in_use -= 1
                self._last_used = self._clock()
                self._cond.notify_all()

    def tick(self) -> bool:
        with self._cond:
            if (self._model is None or self._in_use or self.keep_loaded
                    or self._clock() - self._last_used < self._idle_seconds):
                return False
            self._drop()
        gc.collect()
        return True

    def unload(self) -> None:
        with self._cond:
            while self._in_use:
                self._cond.wait()
            self._drop()
        gc.collect()

    def _drop(self) -> None:
        self._model = None
        self.label = None
