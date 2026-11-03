"""Shared-code changes made for the Mac port. These must pass on Windows too."""
import time
from pathlib import Path

import numpy as np

from voicetool import config
from voicetool.paste_result import PasteResult
from voicetool.pipeline import Pipeline
from tests.test_pipeline import FakeModels, FakeRecorder, FakeStore

REPO = Path(__file__).resolve().parent.parent


def test_app_dir_is_in_the_home_folder():
    assert config.APP_DIR == Path.home() / ".voice-tool"


def test_each_platform_reads_its_own_config_file():
    assert config.config_path_for("darwin") == REPO / "config.mac.toml"
    assert config.config_path_for("win32") == REPO / "config.toml"


def test_mac_config_uses_mac_keys_and_the_default_mic():
    c = config.load_config(REPO / "config.mac.toml")
    assert (c.talk_key, c.corrections_key, c.delete_last_key) == ("alt_r", "shift_r", "backspace")
    assert c.input_device == ""


def _pipeline(result, notices=None):
    notes = []
    deliver = lambda text, target: result  # noqa: E731
    kwargs = {} if notices is None else {"notices": notices}
    p = Pipeline(config.Config(), FakeRecorder(), FakeModels(), FakeStore(), deliver,
                 lambda: (7, "", "com.apple.TextEdit"), lambda m, a, c: "hello there",
                 notes.append, lambda kind: None, **kwargs)
    for event in ("start", "stop"):
        p.on_event(event)
    p.drain(5)
    time.sleep(0.05)
    return notes


def test_platform_can_supply_its_own_paste_notices():
    notes = _pipeline(PasteResult.COPIED_FOCUS_MOVED,
                      {PasteResult.COPIED_FOCUS_MOVED: "Copied, paste it with Cmd+V"})
    assert notes == ["Copied, paste it with Cmd+V"]


def test_default_notices_keep_the_windows_wording():
    assert _pipeline(PasteResult.COPIED_FOCUS_MOVED) == ["Copied — focus moved, paste it with Ctrl+V"]
