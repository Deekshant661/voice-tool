"""System-wide keyboard listener feeding the hotkey state machine."""
from typing import Callable

from pynput import keyboard

from voicetool.hotkeys import HotkeyMachine


def key_name(key) -> str:
    if key is None:
        return ""
    if isinstance(key, keyboard.Key):
        return key.name
    if key.char:
        return key.char
    return f"vk{key.vk}"


def start_listener(machine: HotkeyMachine, on_event: Callable[[str], None]) -> keyboard.Listener:
    def on_press(key):
        for event in machine.down(key_name(key)):
            on_event(event)

    def on_release(key):
        for event in machine.up(key_name(key)):
            on_event(event)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    return listener
