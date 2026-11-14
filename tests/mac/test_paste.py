import pytest

from voicetool.mac import paste
from voicetool.paste_result import PasteResult

CONCEALED, TRANSIENT = "org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType"


class FakeBoard:
    def __init__(self):
        self.items = [{"public.utf8-plain-text": b"old secret", "public.rtf": b"{rtf}"}]
        self.count = 1

    def change_count(self):
        return self.count

    def snapshot(self):
        return [dict(i) for i in self.items]

    def restore(self, snap):
        self.items = [dict(i) for i in snap]
        self.count += 1

    def write_text(self, text, private):
        self.items = [paste.text_item(text, private)]
        self.count += 1


def _deliver(board, target=7, current=7, secure=False, during_wait=None):
    sent = []

    def sleep(s):
        if during_wait:
            during_wait()

    result = paste.deliver("hello", target, board=board, current_pid=lambda: current,
                           secure=lambda: secure, send=lambda: sent.append("cmd+v"), sleep=sleep,
                           trusted=lambda: True)
    return result, sent


def test_decide():
    assert paste.decide(7, 7, False) is PasteResult.PASTED
    assert paste.decide(7, 8, False) is PasteResult.COPIED_FOCUS_MOVED
    assert paste.decide(0, 0, False) is PasteResult.COPIED_FOCUS_MOVED
    assert paste.decide(7, 7, True) is PasteResult.COPIED_ELEVATED


def test_dictation_is_marked_private_for_clipboard_managers():
    item = paste.text_item("hi", private=True)
    assert item["public.utf8-plain-text"] == "hi".encode()
    assert CONCEALED in item and TRANSIENT in item
    assert CONCEALED not in paste.text_item("hi", private=False)


def test_normal_paste_sends_cmd_v_and_restores_the_old_clipboard():
    board = FakeBoard()
    result, sent = _deliver(board)
    assert result is PasteResult.PASTED and sent == ["cmd+v"]
    assert board.items == [{"public.utf8-plain-text": b"old secret", "public.rtf": b"{rtf}"}]


def test_focus_moved_leaves_text_on_the_clipboard_without_pasting():
    board = FakeBoard()
    result, sent = _deliver(board, current=8)
    assert result is PasteResult.COPIED_FOCUS_MOVED and sent == []
    assert board.items[0]["public.utf8-plain-text"] == b"hello"


def test_secure_input_falls_back_to_the_clipboard():
    board = FakeBoard()
    result, sent = _deliver(board, secure=True)
    assert result is PasteResult.COPIED_ELEVATED and sent == []


def test_something_copied_during_the_wait_is_not_overwritten():
    board = FakeBoard()

    def user_copies():
        board.items = [{"public.utf8-plain-text": b"new copy"}]
        board.count += 1

    _deliver(board, during_wait=user_copies)
    assert board.items == [{"public.utf8-plain-text": b"new copy"}]


def test_clipboard_is_restored_even_if_sending_keys_fails():
    board = FakeBoard()

    def boom():
        raise RuntimeError("no accessibility")

    with pytest.raises(RuntimeError):
        paste.deliver("hello", 7, board=board, current_pid=lambda: 7, secure=lambda: False,
                      send=boom, sleep=lambda s: None, trusted=lambda: True)
    assert board.items[0]["public.utf8-plain-text"] == b"old secret"


def test_mac_notices_say_cmd_v():
    assert all("Cmd+V" in text for text in paste.MAC_NOTICES.values())


@pytest.mark.mac
def test_real_pasteboard_round_trip_keeps_every_type():
    board = paste.Pasteboard()
    original = board.snapshot()
    try:
        board.restore([{"public.utf8-plain-text": b"one", "public.rtf": b"{\\rtf1 two}"}])
        snap = board.snapshot()
        board.write_text("dictated", private=True)
        assert board.snapshot()[0]["public.utf8-plain-text"] == b"dictated"
        board.restore(snap)
        assert board.snapshot()[0]["public.rtf"] == b"{\\rtf1 two}"
    finally:
        board.restore(original)


def test_without_accessibility_the_text_stays_on_the_clipboard():
    board = FakeBoard()
    sent = []
    result = paste.deliver("hello", 7, board=board, current_pid=lambda: 7, secure=lambda: False,
                           send=lambda: sent.append("cmd+v"), sleep=lambda s: None,
                           trusted=lambda: False)
    assert result is PasteResult.COPIED_ELEVATED and sent == []
    assert board.items[0]["public.utf8-plain-text"] == b"hello"


def test_elevated_notice_mentions_accessibility():
    assert "Accessibility" in paste.MAC_NOTICES[PasteResult.COPIED_ELEVATED]


def test_a_different_window_of_the_same_app_counts_as_focus_moved():
    assert paste.decide((7, 100), (7, 200), False) is PasteResult.COPIED_FOCUS_MOVED
    assert paste.decide((7, 100), (7, 100), False) is PasteResult.PASTED


def test_front_window_is_the_first_normal_window_of_that_app():
    windows = [{"kCGWindowOwnerPID": 9, "kCGWindowLayer": 0, "kCGWindowNumber": 1},
               {"kCGWindowOwnerPID": 7, "kCGWindowLayer": 25, "kCGWindowNumber": 2},  # menu
               {"kCGWindowOwnerPID": 7, "kCGWindowLayer": 0, "kCGWindowNumber": 3},
               {"kCGWindowOwnerPID": 7, "kCGWindowLayer": 0, "kCGWindowNumber": 4}]
    assert paste.front_window(7, windows) == 3
    assert paste.front_window(5, windows) == 0


def test_spacing_rule_matches_the_phone():
    assert paste.join(None, "Okay.") == "Okay."          # cursor unknown: leave it alone
    assert paste.join("", "Okay.") == "Okay."            # empty box
    assert paste.join("Mac.", "Okay.") == " Okay."       # right after a word
    assert paste.join("Mac. ", "Okay.") == "Okay."       # already a space
    assert paste.join("line\n", "Okay.") == "Okay."


def test_a_space_is_added_after_earlier_text():
    board, typed = FakeBoard(), []
    board.write_text = lambda text, private: typed.append(text)
    paste.deliver("Okay.", 7, board=board, current_pid=lambda: 7, secure=lambda: False,
                  send=lambda: None, sleep=lambda s: None, trusted=lambda: True,
                  before_cursor=lambda: "on my Mac.")
    assert typed == [" Okay."]


@pytest.mark.mac
def test_real_before_cursor_never_crashes():
    assert paste.before_cursor() is None or isinstance(paste.before_cursor(), str)
