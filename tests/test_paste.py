import time

import pytest

from tests.conftest import force_foreground

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
def test_pastes_into_real_window_and_restores_clipboard(root):
    import tkinter as tk

    win = tk.Toplevel(root)
    win.title("voicetool paste test")
    entry = tk.Entry(win, width=60)
    entry.pack()
    hwnd = force_foreground(win, root)
    entry.focus_force()
    root.update()
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
        win.destroy()


def _pretend_target_is_focused(monkeypatch):
    from voicetool.win import paste
    monkeypatch.setattr(paste.win32gui, "GetForegroundWindow", lambda: 1234)
    monkeypatch.setattr(paste, "is_elevated", lambda hwnd: False)


@pytest.mark.win
def test_clipboard_restored_even_if_sending_keys_fails(monkeypatch):
    from voicetool.win import paste
    _pretend_target_is_focused(monkeypatch)

    class Broken:
        def pressed(self, key):
            raise OSError("SendInput failed")
    monkeypatch.setattr(paste, "Controller", Broken)
    set_clipboard_text("my token")
    with pytest.raises(OSError):
        deliver("dictated", 1234)
    assert get_clipboard_text() == "my token"


@pytest.mark.win
def test_user_copy_during_paste_is_not_overwritten(monkeypatch):
    from voicetool.win import paste
    _pretend_target_is_focused(monkeypatch)

    class NoKeys:
        def pressed(self, key):
            from contextlib import nullcontext
            return nullcontext()
        def press(self, k): pass
        def release(self, k): pass
    monkeypatch.setattr(paste, "Controller", NoKeys)
    monkeypatch.setattr(paste.time, "sleep", lambda s: set_clipboard_text("copied meanwhile"))
    set_clipboard_text("before")
    deliver("dictated", 1234)
    assert get_clipboard_text() == "copied meanwhile"


def test_restore_waits_long_enough_for_slow_apps():
    from voicetool.win import paste
    assert paste.RESTORE_DELAY_S >= 0.4


@pytest.mark.win
def test_dictation_text_is_kept_out_of_clipboard_history_and_cloud():
    import struct
    import win32clipboard
    deliver("private words", 0x7FFFFFF0)  # focus-moved path leaves it on the clipboard
    win32clipboard.OpenClipboard()
    try:
        def fmt(name):
            return win32clipboard.RegisterClipboardFormat(name)
        assert win32clipboard.IsClipboardFormatAvailable(fmt("ExcludeClipboardContentFromMonitorProcessing"))
        for name in ("CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
            assert struct.unpack("<I", win32clipboard.GetClipboardData(fmt(name))[:4])[0] == 0
    finally:
        win32clipboard.CloseClipboard()
