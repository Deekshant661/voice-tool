import sys
from types import SimpleNamespace

import pytest

from voicetool.hotkeys import HotkeyMachine
from voicetool.win.keyboard import KeyRouter, make_filter, name_for_vk


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


# --- vk names (the hook reports virtual-key codes) ---

@pytest.mark.skipif(sys.platform == "darwin", reason="Windows virtual-key codes / file locking")
def test_name_for_vk():
    assert name_for_vk(0xA3) == "ctrl_r"
    assert name_for_vk(0xA2) == "ctrl_l"
    assert name_for_vk(0xA1) == "shift_r"
    assert name_for_vk(0x2E) == "delete"
    assert name_for_vk(0x43) == "vk67"  # the C key


# --- router: runs on the hook thread ---

def router():
    events = []
    return KeyRouter(mk(), events.append), events


def test_router_posts_events():
    r, events = router()
    r.press("ctrl_r", injected=False)
    r.release("ctrl_r", injected=False)
    assert events == ["start", "stop"]


def test_router_ignores_injected_keys():
    # Our own Ctrl+V paste must not cancel a dictation the user is recording.
    r, events = router()
    assert r.injected_ignored == 0
    r.press("ctrl_r", injected=False)
    r.press("ctrl_l", injected=True)
    r.press("vk86", injected=True)
    r.release("vk86", injected=True)
    r.release("ctrl_l", injected=True)
    r.release("ctrl_r", injected=False)
    assert events == ["start", "stop"]


def test_router_suppresses_its_own_chords():
    r, events = router()
    assert r.press("ctrl_r", injected=False) is False
    assert r.press("delete", injected=False) is True   # the app must not see Ctrl+Delete
    assert r.release("delete", injected=False) is True
    assert r.release("ctrl_r", injected=False) is False
    assert events == ["start", "cancel", "delete_last"]


def test_router_does_not_suppress_ordinary_shortcuts():
    r, _ = router()
    r.press("ctrl_r", injected=False)
    assert r.press("vk67", injected=False) is False
    assert r.release("vk67", injected=False) is False


def test_router_never_raises():
    def boom(event):
        raise RuntimeError("post failed")
    r = KeyRouter(mk(), boom)
    assert r.press("ctrl_r", injected=False) is False


# --- the low-level filter ---

def _data(vk, injected=False):
    return SimpleNamespace(vkCode=vk, flags=0x10 if injected else 0)


@pytest.mark.skipif(sys.platform == "darwin", reason="Windows virtual-key codes / file locking")
def test_filter_routes_and_suppresses():
    events, suppressed = [], []
    f = make_filter(KeyRouter(mk(), events.append), lambda: suppressed.append(1))
    assert f(0x100, _data(0xA3)) is False          # WM_KEYDOWN right ctrl: handled, not suppressed
    f(0x100, _data(0x2E))                          # delete while held
    assert suppressed == [1]
    f(0x101, _data(0x2E))
    f(0x101, _data(0xA3))
    assert events == ["start", "cancel", "delete_last"] and suppressed == [1, 1]


@pytest.mark.skipif(sys.platform == "darwin", reason="Windows virtual-key codes / file locking")
def test_filter_handles_syskey_messages():
    events = []
    f = make_filter(KeyRouter(mk(), events.append), lambda: None)
    f(0x104, _data(0xA3))   # WM_SYSKEYDOWN
    f(0x105, _data(0xA3))   # WM_SYSKEYUP
    assert events == ["start", "stop"]


def test_filter_ignores_injected():
    events = []
    f = make_filter(KeyRouter(mk(), events.append), lambda: None)
    f(0x100, _data(0xA3, injected=True))
    assert events == []


@pytest.mark.win
def test_real_listener_ignores_injected_keys():
    import time
    from pynput.keyboard import Controller, Key
    from voicetool.win.keyboard import start_listener

    events = []
    listener = start_listener(mk(), events.append)
    try:
        time.sleep(0.3)
        kb = Controller()
        kb.press(Key.ctrl_r); time.sleep(0.05); kb.release(Key.ctrl_r)
        time.sleep(0.3)
    finally:
        listener.stop()
    assert events == []
    assert listener.router.injected_ignored == 2  # the hook saw both and skipped them
