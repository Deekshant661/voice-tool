"""Put text at the cursor of the app that was frontmost when dictation started (macOS)."""
import ctypes
import time
from typing import Callable

from voicetool.paste_result import PasteResult

# The app reads the pasteboard some time after it handles Cmd+V; restoring too early pastes the
# user's OLD clipboard instead of the dictation. Same value as Windows.
RESTORE_DELAY_S = 0.5
_TEXT = "public.utf8-plain-text"
# nspasteboard.org markers: clipboard managers skip these, so dictations stay out of histories.
_PRIVATE_TYPES = ("org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType")

MAC_NOTICES = {
    PasteResult.COPIED_FOCUS_MOVED: "Copied — the app changed, paste it with Cmd+V",
    PasteResult.COPIED_ELEVATED: "Copied — can't type here (password field, or Accessibility is "
                                 "off for the terminal). Paste it with Cmd+V",
}


def decide(target_pid: int, current_pid: int, secure: bool) -> PasteResult:
    if not target_pid or target_pid != current_pid:
        return PasteResult.COPIED_FOCUS_MOVED
    if secure:
        return PasteResult.COPIED_ELEVATED
    return PasteResult.PASTED


def text_item(text: str, private: bool) -> dict[str, bytes]:
    item = {_TEXT: text.encode()}
    if private:
        item.update({t: b"" for t in _PRIVATE_TYPES})
    return item


class Pasteboard:
    """The real general pasteboard, as lists of {type: bytes} items."""

    def __init__(self):
        from AppKit import NSPasteboard
        self._pb = NSPasteboard.generalPasteboard()

    def change_count(self) -> int:
        return self._pb.changeCount()

    def snapshot(self) -> list[dict[str, bytes]]:
        snap = []
        for item in self._pb.pasteboardItems() or []:
            data = {}
            for t in item.types():
                d = item.dataForType_(t)
                if d is not None:  # promised data that never arrived
                    data[str(t)] = bytes(d)
            snap.append(data)
        return snap

    def restore(self, snap: list[dict[str, bytes]]) -> None:
        from AppKit import NSPasteboardItem
        from Foundation import NSData
        self._pb.clearContents()
        items = []
        for data in snap:
            item = NSPasteboardItem.alloc().init()
            for t, b in data.items():
                item.setData_forType_(NSData.dataWithBytes_length_(b, len(b)), t)
            items.append(item)
        if items:
            self._pb.writeObjects_(items)

    def write_text(self, text: str, private: bool) -> None:
        self.restore([text_item(text, private)])


def front_window(pid: int, windows: list[dict]) -> int:
    """Window number of the app's frontmost normal window (the list is front-to-back)."""
    for w in windows:
        if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer") == 0:
            return w.get("kCGWindowNumber", 0)
    return 0


def _onscreen_windows() -> list[dict]:
    import Quartz
    return list(Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID) or [])


def current_target() -> tuple[int, int]:
    """(pid, window number): tells apart two windows of the same app, not two tabs of one."""
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return 0, 0
    pid = app.processIdentifier()
    return pid, front_window(pid, _onscreen_windows())


def foreground() -> tuple[tuple[int, int], str, str]:
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return (0, 0), "", ""
    # Window titles need extra permissions; the app's bundle id is enough to know where it went.
    return current_target(), "", app.bundleIdentifier() or app.localizedName() or ""


def secure_input_on() -> bool:
    carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
    carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
    return carbon.IsSecureEventInputEnabled()


def send_cmd_v() -> None:
    from pynput.keyboard import Controller, Key
    kb = Controller()
    with kb.pressed(Key.cmd):
        kb.press("v")
        kb.release("v")


def _trusted() -> bool:
    from voicetool.mac.keyboard import is_trusted
    return is_trusted()


def join(before: str | None, text: str) -> str:
    """Same rule as the phone: a space when dictating straight after a word."""
    return text if not before or before[-1].isspace() else " " + text


def before_cursor() -> str | None:
    """The character just before the cursor in the focused text box, via Accessibility.
    None when the app doesn't say (Terminal, some Electron apps): then we add nothing."""
    try:
        import ApplicationServices as AX
        err, el = AX.AXUIElementCopyAttributeValue(AX.AXUIElementCreateSystemWide(),
                                                   "AXFocusedUIElement", None)
        if err or el is None:
            return None
        err, value = AX.AXUIElementCopyAttributeValue(el, "AXValue", None)
        err2, rng = AX.AXUIElementCopyAttributeValue(el, "AXSelectedTextRange", None)
        if err or err2 or not isinstance(value, str) or rng is None:
            return None
        ok, r = AX.AXValueGetValue(rng, AX.kAXValueCFRangeType, None)
        if not ok:
            return None
        return value[max(0, r.location - 1):r.location]
    except Exception:
        return None


def deliver(text: str, target_pid, board=None,
            current_pid: Callable[[], object] = current_target,
            secure: Callable[[], bool] = secure_input_on,
            send: Callable[[], None] = send_cmd_v,
            sleep: Callable[[float], None] = time.sleep,
            trusted: Callable[[], bool] = _trusted,
            before_cursor: Callable[[], str | None] = before_cursor) -> PasteResult:
    board = board or Pasteboard()
    current = current_pid()
    # Without Accessibility macOS drops our Cmd+V without a word; restoring afterwards would
    # then wipe the dictation off the clipboard too.
    blocked = target_pid == current and (not trusted() or secure())
    result = decide(target_pid, current, blocked)
    if result is not PasteResult.PASTED:
        board.write_text(text, private=True)  # left there on purpose for the user to paste
        return result
    text = join(before_cursor(), text)
    snap = board.snapshot()
    board.write_text(text, private=True)
    ours = board.change_count()
    try:
        send()
        sleep(RESTORE_DELAY_S)
    finally:
        if board.change_count() == ours:  # only if nobody copied something new meanwhile
            board.restore(snap)
    return result
