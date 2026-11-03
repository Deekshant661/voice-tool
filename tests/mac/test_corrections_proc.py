import numpy as np
import soundfile as sf

from voicetool.mac import corrections
from voicetool.store import Store


class FakeProc:
    def __init__(self):
        self.running = True

    def poll(self):
        return None if self.running else 0


def test_second_open_while_the_window_is_up_does_not_spawn_another():
    spawned = []
    launcher = corrections.CorrectionsLauncher(spawn=lambda: spawned.append(FakeProc()) or spawned[-1])
    assert launcher.open() is True
    assert launcher.open() is False
    assert len(spawned) == 1


def test_opens_again_after_the_window_was_closed():
    spawned = []
    launcher = corrections.CorrectionsLauncher(spawn=lambda: spawned.append(FakeProc()) or spawned[-1])
    launcher.open()
    spawned[0].running = False
    assert launcher.open() is True
    assert len(spawned) == 2


def test_window_store_never_deletes_audio_the_app_is_still_saving(tmp_path):
    Store(tmp_path)  # creates the folders
    being_saved = tmp_path / "audio" / "20261103-120000-000.flac"
    sf.write(being_saved, np.zeros(1600, np.float32), 16000, format="FLAC")  # row not written yet
    corrections.WindowStore(tmp_path)
    assert being_saved.exists()


def test_child_shows_recent_dictations_and_exits_when_closed(tmp_path, root):
    st = Store(tmp_path)
    st.add(np.zeros(1600, np.float32), "hello wrld", "Hello wrld.", "", "com.apple.TextEdit")
    seen = []

    def inspect_then_close():
        win = corrections.current_window()
        seen.extend(win.row_labels())
        win.close()

    root.after(200, inspect_then_close)
    corrections.child_main(tmp_path, root=root)
    assert len(seen) == 1 and "hello wrld" in seen[0]
