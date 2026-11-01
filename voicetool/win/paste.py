"""Put text at the cursor of the window that had focus when dictation started."""
import ctypes
import time
from ctypes import wintypes
from enum import Enum

import win32api
import win32clipboard
import win32con
import win32gui
import win32process
import win32security
from pynput.keyboard import Controller, Key

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
RESTORE_DELAY_S = 0.15  # the target app reads the clipboard after it handles Ctrl+V


class PasteResult(Enum):
    PASTED = "pasted"
    COPIED_FOCUS_MOVED = "copied_focus_moved"
    COPIED_ELEVATED = "copied_elevated"


def decide(target_hwnd: int, current_hwnd: int, target_elevated: bool) -> PasteResult:
    if not target_hwnd or target_hwnd != current_hwnd:
        return PasteResult.COPIED_FOCUS_MOVED
    if target_elevated:
        return PasteResult.COPIED_ELEVATED
    return PasteResult.PASTED


def _process_name(pid: int) -> str:
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def foreground() -> tuple[int, str, str]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return 0, "", ""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return hwnd, win32gui.GetWindowText(hwnd), _process_name(pid)


def is_elevated(hwnd: int) -> bool:
    # Unknown counts as elevated: better to fall back to the clipboard than to paste into nothing.
    try:
        if not win32gui.IsWindow(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        token = win32security.OpenProcessToken(proc, win32security.TOKEN_QUERY)
        return bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
    except Exception:
        return True


def _open_clipboard() -> None:
    for _ in range(10):  # other apps hold the clipboard briefly
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(0.02)
    win32clipboard.OpenClipboard()


def snapshot_clipboard() -> dict[int, bytes]:
    snap = {}
    _open_clipboard()
    try:
        fmt = win32clipboard.EnumClipboardFormats(0)
        while fmt:
            try:
                data = win32clipboard.GetClipboardData(fmt)
                if isinstance(data, (bytes, str)):
                    snap[fmt] = data
            except Exception:
                pass  # handle-based formats (bitmaps, metafiles) can't be copied this way
            fmt = win32clipboard.EnumClipboardFormats(fmt)
    finally:
        win32clipboard.CloseClipboard()
    return snap


def restore_clipboard(snap: dict[int, bytes]) -> None:
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        for fmt, data in snap.items():
            try:
                win32clipboard.SetClipboardData(fmt, data)
            except Exception:
                pass
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def get_clipboard_text() -> str:
    _open_clipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return ""
    finally:
        win32clipboard.CloseClipboard()


def deliver(text: str, target_hwnd: int) -> PasteResult:
    current = win32gui.GetForegroundWindow()
    result = decide(target_hwnd, current, is_elevated(target_hwnd) if target_hwnd == current else False)
    if result is not PasteResult.PASTED:
        set_clipboard_text(text)  # left there on purpose so the user can paste it themselves
        return result
    snap = snapshot_clipboard()
    set_clipboard_text(text)
    kb = Controller()
    with kb.pressed(Key.ctrl_l):
        kb.press("v")
        kb.release("v")
    time.sleep(RESTORE_DELAY_S)
    restore_clipboard(snap)
    return result
