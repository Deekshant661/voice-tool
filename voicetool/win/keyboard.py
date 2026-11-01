"""System-wide keyboard hook feeding the hotkey state machine.

Everything here runs on Windows' low-level keyboard hook, which stalls typing in every app
while it runs. So it only updates the state machine and posts events; the real work happens
on the pipeline's own threads."""
import logging
from typing import Callable

from pynput import keyboard

from voicetool.hotkeys import HotkeyMachine

log = logging.getLogger("voicetool")

_PRESS = {0x100, 0x104}    # WM_KEYDOWN, WM_SYSKEYDOWN
_RELEASE = {0x101, 0x105}  # WM_KEYUP, WM_SYSKEYUP
_INJECTED = 0x10 | 0x02    # LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED

_VK_NAMES: dict[int, str] = {}
for _k in keyboard.Key:
    vk = getattr(_k.value, "vk", None)
    if vk is not None and vk not in _VK_NAMES:  # first wins: alt_r before alt_gr
        _VK_NAMES[vk] = _k.name


def name_for_vk(vk: int) -> str:
    return _VK_NAMES.get(vk, f"vk{vk}")


class KeyRouter:
    def __init__(self, machine: HotkeyMachine, post: Callable[[str], None]):
        self.machine = machine
        self.post = post
        self._suppressed: set[str] = set()
        self.injected_ignored = 0

    def press(self, name: str, injected: bool) -> bool:
        """Returns True when the key must be hidden from the focused app."""
        if injected:  # our own Ctrl+V; never let it cancel a dictation
            self.injected_ignored += 1
            return False
        try:
            events = self.machine.down(name)
            for event in events:
                self.post(event)
            if "corrections" in events or "delete_last" in events:
                self._suppressed.add(name)  # e.g. Ctrl+Delete would delete a word in the app
                return True
        except Exception:
            log.exception("key press handling failed")
        return False

    def release(self, name: str, injected: bool) -> bool:
        if injected:
            self.injected_ignored += 1
            return False
        try:
            events = self.machine.up(name)
            for event in events:
                self.post(event)
            if name in self._suppressed:
                self._suppressed.discard(name)
                return True
        except Exception:
            log.exception("key release handling failed")
        return False


def make_filter(router: KeyRouter, suppress: Callable[[], None]):
    def event_filter(msg, data) -> bool:
        injected = bool(data.flags & _INJECTED)
        name = name_for_vk(data.vkCode)
        hide = False
        if msg in _PRESS:
            hide = router.press(name, injected)
        elif msg in _RELEASE:
            hide = router.release(name, injected)
        if hide:
            suppress()
        return False  # handled here; skip pynput's own callbacks
    return event_filter


def start_listener(machine: HotkeyMachine, on_event: Callable[[str], None]) -> keyboard.Listener:
    router = KeyRouter(machine, on_event)
    listener = keyboard.Listener(win32_event_filter=lambda msg, data: filter_fn(msg, data))
    filter_fn = make_filter(router, listener.suppress_event)
    listener.router = router
    listener.start()
    return listener
