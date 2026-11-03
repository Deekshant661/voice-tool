import threading

from voicetool.mac import menubar


def _status():
    return {"model": "whisper-large-v3-turbo-q4 (Apple GPU)", "bytes": 1_250_000_000,
            "logging": True, "keep_loaded": False}


def _bar(notes=None):
    calls = []
    names = ["logging", "keep", "unload", "corrections", "data", "quit"]
    handlers = {n: (lambda n=n: calls.append(n)) for n in names}
    runner = (notes.append if notes is not None else (lambda args: None))
    return menubar.MenuBar(_status, handlers, run=runner), calls


def test_titles_show_the_state():
    assert menubar.title_for("idle") == "VT"
    assert menubar.title_for("recording") == "VT ●"
    assert menubar.title_for("working") == "VT …"


def test_state_change_from_a_worker_thread_waits_for_the_main_thread():
    bar, _ = _bar()
    t = threading.Thread(target=bar.set_state, args=("recording",))
    t.start(); t.join()
    assert bar.app.title == "VT"
    bar.pump()
    assert bar.app.title == "VT ●"


def test_a_failing_queued_action_does_not_block_later_ones():
    bar, _ = _bar()
    bar.call_soon(lambda: 1 / 0)
    bar.set_state("working")
    bar.pump()
    assert bar.app.title == "VT …"


def test_status_rows_show_model_and_size():
    bar, _ = _bar()
    bar.refresh_status()
    titles = [item.title for item in bar.app.menu.values() if hasattr(item, "title")]
    assert "Model: whisper-large-v3-turbo-q4 (Apple GPU)" in titles
    assert "Recordings: 1.25 GB" in titles
    assert bar.app.menu["Save recordings"].state == 1
    assert bar.app.menu["Keep model loaded"].state == 0


def test_menu_items_call_their_handlers():
    bar, calls = _bar()
    for title in ["Save recordings", "Keep model loaded", "Unload model now",
                  "Open recent dictations", "Open data folder", "Quit Voice Tool"]:
        bar.app.menu[title].callback(bar.app.menu[title])
    assert calls == ["logging", "keep", "unload", "corrections", "data", "quit"]


def test_notify_uses_osascript_with_quotes_escaped():
    notes = []
    bar, _ = _bar(notes)
    bar.notify('Copied "x" \\ y')
    assert notes == [["osascript", "-e",
                      'display notification "Copied \\"x\\" \\\\ y" with title "Voice Tool"']]
