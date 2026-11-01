import pytest
from pynput.keyboard import Key, KeyCode

from voicetool.hotkeys import HotkeyMachine
from voicetool.win.keyboard import key_name


def mk():
    return HotkeyMachine("ctrl_r", "shift_r", "delete")


def test_hold_and_release():
    m = mk()
    assert m.down("ctrl_r") == ["start"]
    assert m.up("ctrl_r") == ["stop"]


def test_autorepeat_ignored():
    m = mk()
    m.down("ctrl_r")
    assert m.down("ctrl_r") == []


def test_other_key_cancels():
    m = mk()
    m.down("ctrl_r")
    assert m.down("c") == ["cancel"]
    assert m.up("c") == [] and m.up("ctrl_r") == []


def test_corrections_combo():
    m = mk()
    m.down("ctrl_r")
    assert m.down("shift_r") == ["cancel", "corrections"]


def test_delete_last_combo():
    m = mk()
    m.down("ctrl_r")
    assert m.down("delete") == ["cancel", "delete_last"]


def test_keys_without_talk_do_nothing():
    m = mk()
    assert m.down("shift_r") == [] and m.down("delete") == []


def test_left_ctrl_is_not_talk():
    m = mk()
    assert m.down("ctrl_l") == []


def test_works_again_after_cancel():
    m = mk()
    m.down("ctrl_r"); m.down("c"); m.up("c"); m.up("ctrl_r")
    assert m.down("ctrl_r") == ["start"] and m.up("ctrl_r") == ["stop"]


def test_second_extra_key_does_not_cancel_twice():
    m = mk()
    m.down("ctrl_r")
    m.down("c")
    assert m.down("v") == []


def test_key_name_special_and_char():
    assert key_name(Key.ctrl_r) == "ctrl_r"
    assert key_name(Key.delete) == "delete"
    assert key_name(KeyCode.from_char("c")) == "c"
    assert key_name(KeyCode.from_vk(0x41)) == "vk65"
    assert key_name(None) == ""


@pytest.mark.win
def test_real_listener_sees_injected_keys():
    import time
    from pynput.keyboard import Controller
    from voicetool.win.keyboard import start_listener

    events = []
    listener = start_listener(mk(), events.append)
    try:
        time.sleep(0.3)
        kb = Controller()
        kb.press(Key.ctrl_r); time.sleep(0.05); kb.release(Key.ctrl_r)
        kb.press(Key.ctrl_r); kb.press(Key.shift_r); kb.release(Key.shift_r); kb.release(Key.ctrl_r)
        time.sleep(0.3)
    finally:
        listener.stop()
    assert events == ["start", "stop", "start", "cancel", "corrections"]
