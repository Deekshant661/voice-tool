import time

import pytest

from voicetool.win.paste import (PasteResult, decide, deliver, foreground, get_clipboard_text,
                                 is_elevated, restore_clipboard, set_clipboard_text,
                                 snapshot_clipboard)


def test_same_window_pastes():
    assert decide(10, 10, False) is PasteResult.PASTED


def test_focus_moved_copies():
    assert decide(10, 11, False) is PasteResult.COPIED_FOCUS_MOVED


def test_elevated_copies():
    assert decide(10, 10, True) is PasteResult.COPIED_ELEVATED


def test_no_target_window_copies():
    assert decide(0, 0, False) is PasteResult.COPIED_FOCUS_MOVED


@pytest.mark.win
def test_clipboard_text_restored():
    set_clipboard_text("before")
    snap = snapshot_clipboard()
    set_clipboard_text("dictated")
    restore_clipboard(snap)
    assert get_clipboard_text() == "before"


@pytest.mark.win
def test_unknown_window_counts_as_elevated():
    assert is_elevated(0x7FFFFFF0) is True


@pytest.mark.win
def test_focus_moved_leaves_text_on_clipboard():
    set_clipboard_text("before")
    assert deliver("dictated", 0x7FFFFFF0) is PasteResult.COPIED_FOCUS_MOVED
    assert get_clipboard_text() == "dictated"


@pytest.mark.win
def test_pastes_into_real_window_and_restores_clipboard():
    import tkinter as tk
    import win32gui

    root = tk.Tk()
    root.title("voicetool paste test")
    entry = tk.Entry(root, width=60)
    entry.pack()
    root.update()
    hwnd = int(root.wm_frame(), 16)
    root.lift(); root.attributes("-topmost", True); root.focus_force(); entry.focus_set()
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    for _ in range(20):
        root.update(); time.sleep(0.05)
    target = foreground()[0]
    assert target == hwnd, "test window did not get focus"
    assert is_elevated(target) is False

    import threading
    set_clipboard_text("before")
    out = {}
    # Paste from another thread so this window keeps processing messages, like a real app would.
    t = threading.Thread(target=lambda: out.update(result=deliver("check the Postgres database", target)))
    t.start()
    while t.is_alive():
        root.update(); time.sleep(0.01)
    for _ in range(10):
        root.update(); time.sleep(0.02)
    result = out["result"]
    try:
        assert result is PasteResult.PASTED
        assert entry.get() == "check the Postgres database"
        assert get_clipboard_text() == "before"
    finally:
        root.destroy()
