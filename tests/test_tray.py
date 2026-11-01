from voicetool.win.tray import COLORS, Tray, format_gb, icon_image


def test_icon_colour_per_state():
    for state, rgb in COLORS.items():
        img = icon_image(state)
        assert img.size == (64, 64)
        assert img.getpixel((32, 32))[:3] == rgb
    assert set(COLORS) == {"idle", "recording", "working"}


def test_format_gb():
    assert format_gb(0) == "0.00 GB"
    assert format_gb(1_234_000_000) == "1.23 GB"


def make_tray(status):
    calls = []
    t = Tray(lambda: status,
             on_toggle_logging=lambda: calls.append("logging"),
             on_unload=lambda: calls.append("unload"),
             on_toggle_keep_loaded=lambda: calls.append("keep"),
             on_open_data=lambda: calls.append("data"),
             on_open_corrections=lambda: calls.append("corrections"),
             on_quit=lambda: calls.append("quit"))
    return t, calls


def _items(tray):
    return {item.text: item for item in tray.menu().items if item.text}


def test_menu_shows_status():
    t, _ = make_tray({"model": "large-v3-turbo (GPU)", "bytes": 500_000_000,
                      "logging": True, "keep_loaded": False})
    items = _items(t)
    assert "Model: large-v3-turbo (GPU)" in items
    assert "Recordings: 0.50 GB" in items
    assert items["Save recordings"].checked is True
    assert items["Keep model loaded"].checked is False


def test_menu_when_model_not_loaded():
    t, _ = make_tray({"model": None, "bytes": 0, "logging": False, "keep_loaded": True})
    items = _items(t)
    assert "Model: not loaded" in items
    assert items["Save recordings"].checked is False
    assert items["Keep model loaded"].checked is True


def test_menu_actions_call_callbacks():
    t, calls = make_tray({"model": None, "bytes": 0, "logging": True, "keep_loaded": False})
    items = _items(t)
    for label in ["Save recordings", "Keep model loaded", "Unload model now",
                  "Open recent dictations", "Open data folder", "Quit"]:
        items[label](None)
    assert calls == ["logging", "keep", "unload", "corrections", "data", "quit"]


def test_set_state_changes_icon():
    t, _ = make_tray({"model": None, "bytes": 0, "logging": True, "keep_loaded": False})
    t.set_state("recording")
    assert t.icon.icon.getpixel((32, 32))[:3] == COLORS["recording"]
