"""System-wide key listener for macOS, feeding the shared hotkey state machine.

With Accessibility granted it is an active event tap: it can swallow chord keys (Option+Delete
would otherwise delete a word in the app) and recognise our own Cmd+V by its source process.
Without it macOS only allows listening, so dictation works but chords are not swallowed."""
import ctypes
import logging
import os
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


def make_intercept(router: KeyRouter, own_pid: int, read=_read_quartz):
    def intercept(event_type, event):
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


def start_listener(machine: HotkeyMachine, on_event: Callable[[str], None],
                   trusted: Callable[[], bool] = is_trusted,
                   listener_cls=keyboard.Listener) -> tuple[object, bool]:
    """Returns (listener, full_mode)."""
    router = KeyRouter(machine, on_event)
    if trusted():
        listener = listener_cls(darwin_intercept=make_intercept(router, os.getpid()))
        full = True
    else:
        log.warning("Accessibility not granted: listening only, chords are not swallowed")
        listener = listener_cls(on_press=lambda k: router.press(_key_name(k), False),
                                on_release=lambda k: router.release(_key_name(k), False))
        full = False
    listener.router = router
    listener.start()
    return listener, full
