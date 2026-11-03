import runpy
import sys
import types

from voicetool.config import Config
from voicetool.mac import app as mac_app


def test_only_one_copy_can_run(tmp_path):
    lock = tmp_path / "voicetool.lock"
    first = mac_app.acquire_single_instance(lock)
    assert first is not None
    assert mac_app.acquire_single_instance(lock) is None
    first.close()
    assert mac_app.acquire_single_instance(lock) is not None


def test_beeps_play_system_sounds_without_waiting():
    runs = []
    mac_app.beep("start", run=runs.append)
    mac_app.beep("stop", run=runs.append)
    assert runs == [["afplay", "/System/Library/Sounds/Pop.aiff"],
                    ["afplay", "/System/Library/Sounds/Tink.aiff"]]


class Recorder:
    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        return lambda *a, **k: self.log.append((name,) + a)


class FakeModels:
    def __init__(self, log, tick_result=True):
        self.log, self.tick_result = log, tick_result
        self.label, self.keep_loaded = "m (Apple GPU)", False

    def tick(self):
        self.log.append(("tick",))
        return self.tick_result

    def unload(self):
        self.log.append(("unload",))


class FakeStore:
    def total_bytes(self):
        return 42


def _app(log, tick_result=True):
    pipeline = Recorder(log)
    pipeline.logging = True
    a = mac_app.MacApp(Config(), FakeStore(), FakeModels(log, tick_result), pipeline,
                       bar=Recorder(log), launcher=Recorder(log), listener=Recorder(log),
                       release=lambda: log.append(("release",)), run=log.append)
    return a


def test_quit_waits_for_a_dictation_in_progress_before_stopping():
    log = []
    _app(log).quit()
    assert log == [("stop",), ("drain", 2.0), ("stop",)]  # listener, pipeline, menu bar


def test_idle_unload_also_frees_mlx_memory():
    log = []
    _app(log).tick()
    assert log == [("tick",), ("release",)]


def test_no_release_when_nothing_was_unloaded():
    log = []
    _app(log, tick_result=False).tick()
    assert log == [("tick",)]


def test_unload_now_frees_mlx_memory_off_the_main_thread():
    log = []
    _app(log).unload(wait=True)
    assert log == [("unload",), ("release",)]


def test_menu_actions():
    log = []
    a = _app(log)
    a.open_data()
    a.open_corrections()
    a.toggle_logging()
    a.toggle_keep_loaded()
    assert log[:2] == [["open", str(a.data_dir)], ("open",)]  # Finder, then the window
    assert a.pipeline.logging is False and a.models.keep_loaded is True
    assert a.status() == {"model": "m (Apple GPU)", "bytes": 42, "logging": False,
                          "keep_loaded": True}


def test_python_m_voicetool_starts_the_mac_app(monkeypatch):
    started = []
    fake = types.ModuleType("voicetool.mac.app")
    fake.main = lambda: started.append("mac")
    monkeypatch.setitem(sys.modules, "voicetool.mac.app", fake)
    monkeypatch.setattr(sys, "platform", "darwin")
    runpy.run_module("voicetool", run_name="__main__")
    assert started == ["mac"]
