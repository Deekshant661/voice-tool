import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_root():
    # One Tk for the whole run: creating and destroying many in a row is flaky on Windows.
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


@pytest.fixture
def root(tk_root):
    yield tk_root
    for child in tk_root.winfo_children():
        child.destroy()


def force_foreground(tk_window, root) -> int:
    """Bring a test window to the front. Windows blocks background processes from taking focus,
    so briefly attach to the current foreground thread's input queue first."""
    import time
    import win32gui
    import win32process
    import win32api

    root.update()
    hwnd = int(tk_window.wm_frame(), 16)
    tk_window.attributes("-topmost", True)
    fg = win32gui.GetForegroundWindow()
    fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    me = win32api.GetCurrentThreadId()
    attached = False
    if fg_thread and fg_thread != me:
        win32process.AttachThreadInput(me, fg_thread, True)
        attached = True
    try:
        win32gui.ShowWindow(hwnd, 5)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
    finally:
        if attached:
            win32process.AttachThreadInput(me, fg_thread, False)
    for _ in range(20):
        root.update()
        time.sleep(0.03)
    return hwnd
