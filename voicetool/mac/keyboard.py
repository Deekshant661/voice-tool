"""System-wide key listener for macOS, feeding the shared hotkey state machine.

With Accessibility granted it is an active event tap: it can swallow chord keys (Option+Delete
would otherwise delete a word in the app) and recognise our own Cmd+V by its source process.
Without it macOS only allows listening, so dictation works but chords are not swallowed."""
import ctypes
import logging
import os
import time
from typing import Callable

from pynput import keyboard

from voicetool.hotkeys import HotkeyMachine
from voicetool.win.keyboard import KeyRouter  # pure logic, shared with Windows

log = logging.getLogger("voicetool")

_KEY_DOWN, _KEY_UP, _FLAGS_CHANGED = 10, 11, 12
_SOURCE_PID_FIELD, _KEYCODE_FIELD = 41, 9
# Device-dependent modifier bits: they tell left from right, and down from up.
_MODIFIER_BITS = {54: 0x10, 55: 0x08, 56: 0x02, 60: 0x04, 58: 0x20, 61: 0x40, 59: 0x01, 62: 0x2000}

_NAMES: dict[int, str] = {}
for _k in keyboard.Key:
    if _k.name.startswith("media_"):  # system-defined events, their numbers clash with keycodes
        continue
    _vk = getattr(_k.value, "vk", None)
    if _vk is not None and _vk not in _NAMES:  # first wins: alt_r before alt_gr
        _NAMES[_vk] = _k.name


def classify(event_type: int, keycode: int, flags: int) -> tuple[str, str] | None:
    name = _NAMES.get(keycode, f"vk{keycode}")
    if event_type == _KEY_DOWN:
        return name, "down"
    if event_type == _KEY_UP:
        return name, "up"
    if event_type == _FLAGS_CHANGED and keycode in _MODIFIER_BITS:
        return name, "down" if flags & _MODIFIER_BITS[keycode] else "up"
    return None


def _read_quartz(event) -> tuple[int, int, int]:
    import Quartz
    return (Quartz.CGEventGetIntegerValueField(event, _KEYCODE_FIELD), Quartz.CGEventGetFlags(event),
            Quartz.CGEventGetIntegerValueField(event, _SOURCE_PID_FIELD))


_TAP_DISABLED = {0xFFFFFFFE, 0xFFFFFFFF}  # by timeout (a slow moment, e.g. swapping), by user input
MAX_RECORDING_S = 300


def make_intercept(router: KeyRouter, own_pid: int, read=_read_quartz,
                   reenable: Callable[[], None] = lambda: None):
    def intercept(event_type, event):
        if event_type in _TAP_DISABLED:
            # macOS switches a slow tap off and never back on; the hotkey would just go dead.
            log.warning("macOS disabled the key listener (%#x); switching it back on", event_type)
            reenable()
            return event
        keycode, flags, source_pid = read(event)
        kind = classify(event_type, keycode, flags)
        if kind is None:
            return event
        name, direction = kind
        injected = source_pid == own_pid  # our own Cmd+V must never cancel a dictation
        hide = (router.press if direction == "down" else router.release)(name, injected)
        return None if hide else event
    return intercept


def is_trusted() -> bool:
    ax = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    return ax.AXIsProcessTrusted()


def _key_name(key) -> str:
    return getattr(key, "name", None) or f"vk{getattr(key, 'vk', None)}"


class StuckKeyGuard:
    """If the talk key's release is missed (secure input can swallow it), stop the recording
    after MAX_RECORDING_S instead of recording forever."""

    def __init__(self, router: KeyRouter, talk: str, clock: Callable[[], float] = time.monotonic,
                 max_s: float = MAX_RECORDING_S):
        self._router, self._talk, self._clock, self._max = router, talk, clock, max_s
        self._since: float | None = None

    def wrap(self, post: Callable[[str], None]) -> Callable[[str], None]:
        def guarded(event: str) -> None:
            if event == "start":
                self._since = self._clock()
            elif event in ("stop", "cancel"):
                self._since = None
            post(event)
        return guarded

    def check(self) -> None:
        if self._since is not None and self._clock() - self._since >= self._max:
            log.warning("talk key held for %d s: stopping the recording", self._max)
            self._router.release(self._talk, False)


class MacListener(keyboard.Listener):
    """pynput's listener, keeping hold of its event tap so it can be switched back on."""
    tap = None

    def _create_event_tap(self):
        self.tap = super()._create_event_tap()
        return self.tap


def _listen_only(router: KeyRouter, listener_cls):
    return listener_cls(on_press=lambda k: router.press(_key_name(k), False),
                        on_release=lambda k: router.release(_key_name(k), False))


def start_listener(machine: HotkeyMachine, on_event: Callable[[str], None],
                   trusted: Callable[[], bool] = is_trusted,
                   listener_cls=MacListener) -> tuple[object, bool]:
    """Returns (listener, full_mode). listener.guard must be checked periodically."""
    router = KeyRouter(machine, on_event)
    guard = StuckKeyGuard(router, machine.talk)
    router.post = guard.wrap(on_event)
    listener = None
    if trusted():
        holder: dict = {}

        def reenable():
            import Quartz
            Quartz.CGEventTapEnable(holder["l"].tap, True)

        listener = listener_cls(darwin_intercept=make_intercept(router, os.getpid(),
                                                                reenable=reenable))
        holder["l"] = listener
        listener.start()
        getattr(listener, "wait", lambda: None)()  # the tap is made on the listener's thread
        if listener.tap is None:
            log.warning("Could not create the key tap: falling back to listening only")
            getattr(listener, "stop", lambda: None)()
            listener = None
    else:
        log.warning("Accessibility not granted: listening only, chords are not swallowed")
    full = listener is not None
    if listener is None:
        listener = _listen_only(router, listener_cls)
        listener.start()
    listener.router, listener.guard = router, guard
    return listener, full
