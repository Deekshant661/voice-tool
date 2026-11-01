import numpy as np
import soundfile as sf

from voicetool.store import Store


def _audio(s=1.0):
    return np.zeros(int(16000 * s), dtype=np.float32)


def test_add_and_recent(tmp_path):
    st = Store(tmp_path)
    i = st.add(_audio(), "raw", "Raw", "Notepad", "notepad.exe")
    d = st.recent(5)[0]
    assert d.id == i and d.raw_text == "raw" and d.corrected_text is None
    assert d.audio_path.exists() and d.audio_path.suffix == ".flac"
    assert abs(d.duration_s - 1.0) < 0.01
    assert sf.info(d.audio_path).samplerate == 16000


def test_correction(tmp_path):
    st = Store(tmp_path)
    i = st.add(_audio(), "pm 2", "Pm 2", "", "")
    st.set_correction(i, "pm2")
    assert st.recent(1)[0].corrected_text == "pm2"


def test_delete_last_removes_row_and_file(tmp_path):
    st = Store(tmp_path)
    st.add(_audio(), "a", "A", "", "")
    st.add(_audio(), "b", "B", "", "")
    p = st.recent(1)[0].audio_path
    assert st.delete_last() is True and not p.exists()
    assert [d.raw_text for d in st.recent(5)] == ["a"]


def test_delete_last_empty(tmp_path):
    assert Store(tmp_path).delete_last() is False


def test_total_bytes_grows(tmp_path):
    st = Store(tmp_path)
    b = st.total_bytes()
    st.add(_audio(2), "a", "A", "", "")
    assert st.total_bytes() > b
