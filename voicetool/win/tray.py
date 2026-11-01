"""Tray icon: shows state by colour and holds the menu."""
from typing import Callable

import pystray
from PIL import Image, ImageDraw

COLORS = {"idle": (128, 128, 128), "recording": (220, 38, 38), "working": (245, 158, 11)}


def icon_image(state: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((4, 4, 60, 60), fill=COLORS[state] + (255,))
    return img


def format_gb(nbytes: int) -> str:
    return f"{nbytes / 1e9:.2f} GB"


class Tray:
    def __init__(self, status: Callable[[], dict], on_toggle_logging, on_unload,
                 on_toggle_keep_loaded, on_open_data, on_open_corrections, on_quit):
        self._status = status
        self._on = {
            "logging": on_toggle_logging, "unload": on_unload, "keep": on_toggle_keep_loaded,
            "data": on_open_data, "corrections": on_open_corrections, "quit": on_quit,
        }
        self.icon = pystray.Icon("voicetool", icon_image("idle"), "Voice Tool", menu=self.menu())

    def _action(self, name: str):
        return lambda icon, item: self._on[name]()

    def menu(self) -> pystray.Menu:
        s = self._status
        return pystray.Menu(
            pystray.MenuItem(lambda item: f"Model: {s()['model'] or 'not loaded'}", None, enabled=False),
            pystray.MenuItem(lambda item: f"Recordings: {format_gb(s()['bytes'])}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Save recordings", self._action("logging"), checked=lambda item: s()["logging"]),
            pystray.MenuItem("Keep model loaded", self._action("keep"),
                             checked=lambda item: s()["keep_loaded"]),
            pystray.MenuItem("Unload model now", self._action("unload")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open recent dictations", self._action("corrections")),
            pystray.MenuItem("Open data folder", self._action("data")),
            pystray.MenuItem("Quit", self._action("quit")),
        )

    def start(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        self.icon.stop()

    def notify(self, msg: str) -> None:
        try:
            self.icon.notify(msg, "Voice Tool")
        except Exception:
            pass  # notifications are best-effort; never break a dictation over one

    def set_state(self, state: str) -> None:
        self.icon.icon = icon_image(state)
