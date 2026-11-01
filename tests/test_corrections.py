import numpy as np
import pytest

from voicetool.store import Store
from voicetool.win.corrections import HEADER, open_window


@pytest.fixture
def store(tmp_path):
    st = Store(tmp_path)
    st.add(np.zeros(16000, np.float32), "restart pm 2", "Restart pm 2", "", "")
    st.add(np.zeros(16000, np.float32), "check the vesras box", "Check the vesras box", "", "")
    return st


def test_lists_recent_newest_first_with_header(root, store):
    w = open_window(root, store)
    assert w.header_text() == HEADER
    labels = w.row_labels()
    assert len(labels) == 2 and "check the vesras box" in labels[0]


def test_select_prefills_raw_text(root, store):
    w = open_window(root, store)
    w.select(0)
    assert w.editor_text() == "check the vesras box"


def test_save_stores_correction_and_marks_row(root, store):
    w = open_window(root, store)
    w.select(0)
    w.set_editor_text("check the Vezras box")
    w.save()
    assert store.recent(1)[0].corrected_text == "check the Vezras box"
    assert "✓" in w.row_labels()[0]


def test_select_prefills_existing_correction(root, store):
    store.set_correction(store.recent(1)[0].id, "check the Vezras box")
    w = open_window(root, store)
    w.select(0)
    assert w.editor_text() == "check the Vezras box"


def test_delete_removes_entry(root, store):
    w = open_window(root, store)
    w.select(0)
    w.delete()
    assert [d.raw_text for d in store.recent(5)] == ["restart pm 2"]
    assert len(w.row_labels()) == 1


def test_save_without_selection_does_nothing(root, store):
    w = open_window(root, store)
    w.save()
    assert all(d.corrected_text is None for d in store.recent(5))


def test_only_one_window(root, store):
    assert open_window(root, store) is open_window(root, store)


def test_reopens_after_close(root, store):
    w = open_window(root, store)
    w.close()
    assert open_window(root, store) is not w
