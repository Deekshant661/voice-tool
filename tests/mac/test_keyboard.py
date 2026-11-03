from voicetool.hotkeys import HotkeyMachine
from voicetool.mac import keyboard as mk
from voicetool.win.keyboard import KeyRouter

KEY_DOWN, KEY_UP, FLAGS = 10, 11, 12
RALT, RSHIFT = 0x40, 0x04
OWN_PID = 4242


def test_right_option_down_and_up_from_flags():
    assert mk.classify(FLAGS, 61, RALT) == ("alt_r", "down")
    assert mk.classify(FLAGS, 61, 0) == ("alt_r", "up")


def test_right_option_up_while_left_option_still_held():
    assert mk.classify(FLAGS, 61, 0x20) == ("alt_r", "up")


def test_ordinary_keys():
    assert mk.classify(KEY_DOWN, 51, 0) == ("backspace", "down")
    assert mk.classify(KEY_UP, 0, 0) == ("vk0", "up")


def test_unknown_modifier_is_ignored():
    assert mk.classify(FLAGS, 63, 0x800000) is None  # fn


def _intercept():
    posted = []
    router = KeyRouter(HotkeyMachine("alt_r", "shift_r", "backspace"), posted.append)
    fields = {}
    read = lambda event: fields[event]  # noqa: E731  (keycode, flags, source_pid)
    return mk.make_intercept(router, OWN_PID, read), fields, posted


def test_chord_key_is_swallowed_and_posts_delete_last():
    hook, fields, posted = _intercept()
    fields.update({"opt": (61, RALT, 1), "bs": (51, RALT, 1), "bs_up": (51, RALT, 1)})
    assert hook(FLAGS, "opt") == "opt"
    assert hook(KEY_DOWN, "bs") is None
    assert hook(KEY_UP, "bs_up") is None
    assert posted == ["start", "cancel", "delete_last"]


def test_plain_dictation_passes_keys_through():
    hook, fields, posted = _intercept()
    fields.update({"down": (61, RALT, 1), "up": (61, 0, 1)})
    assert hook(FLAGS, "down") == "down" and hook(FLAGS, "up") == "up"
    assert posted == ["start", "stop"]


def test_our_own_injected_paste_is_ignored():
    hook, fields, posted = _intercept()
    fields.update({"opt": (61, RALT, 1), "cmd_v": (9, 0x100000, OWN_PID)})
    hook(FLAGS, "opt")
    assert hook(KEY_DOWN, "cmd_v") == "cmd_v"
    assert posted == ["start"]  # no "cancel"


class FakeListener:
    def __init__(self, **kw):
        self.kw = kw
        self.started = False

    def start(self):
        self.started = True


def test_full_mode_when_accessibility_is_granted():
    listener, full = mk.start_listener(HotkeyMachine("alt_r", "shift_r", "backspace"), print,
                                       trusted=lambda: True, listener_cls=FakeListener)
    assert full and listener.started and "darwin_intercept" in listener.kw


def test_listen_only_mode_without_accessibility():
    posted = []
    listener, full = mk.start_listener(HotkeyMachine("alt_r", "shift_r", "backspace"),
                                       posted.append, trusted=lambda: False,
                                       listener_cls=FakeListener)
    assert not full and "darwin_intercept" not in listener.kw
    from pynput.keyboard import Key
    listener.kw["on_press"](Key.alt_r)
    listener.kw["on_release"](Key.alt_r)
    assert posted == ["start", "stop"]
