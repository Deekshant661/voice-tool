import pytest

from voicetool.app import App, acquire_single_instance, beep_tone, fallback_notice
from voicetool.config import Config


def test_beep_tones():
    assert beep_tone("start") == (880, 60)
    assert beep_tone("stop") == (660, 60)


def test_fallback_notice():
    assert fallback_notice("large-v3-turbo (GPU)") is None
    assert fallback_notice("small (CPU fallback)") == "GPU unavailable — using small model on CPU"


def test_single_instance():
    first = acquire_single_instance("VoiceTool.Test.SingleInstance")
    assert first is not None
    assert acquire_single_instance("VoiceTool.Test.SingleInstance") is None


class FakeTray:
    def __init__(self):
        self.notes, self.states, self.started, self.stopped = [], [], False, False

    def notify(self, msg):
        self.notes.append(msg)

    def set_state(self, s):
        self.states.append(s)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeModels:
    def __init__(self):
        self.keep_loaded = False
        self.label = None
        self.on_loaded = None
        self.unloaded = 0
        self.ticks = 0

    def unload(self):
        self.unloaded += 1

    def tick(self):
        self.ticks += 1
        return False


class FakePipeline:
    def __init__(self, logging=True):
        self.logging = logging
        self.open_corrections = None


class FakeStore:
    def total_bytes(self):
        return 123


@pytest.fixture
def app(root):
    opened = []
    a = App(Config(), root, FakeStore(), FakeModels(),
            make_pipeline=lambda app: FakePipeline(),
            make_tray=lambda app: FakeTray(),
            opener=opened.append,
            open_corrections_window=lambda r, s: opened.append("window"))
    a.opened = opened
    return a


def pump(app, until=lambda: False, seconds=1.0):
    # The app hands work to the Tk thread on a 50 ms timer, so run the loop long enough to see it.
    import time
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        app.root.update()
        time.sleep(0.01)


def test_status(app):
    app.models.label = "large-v3-turbo (GPU)"
    assert app.status() == {"model": "large-v3-turbo (GPU)", "bytes": 123,
                            "logging": True, "keep_loaded": False}


def test_toggles(app):
    app.toggle_logging()
    app.toggle_keep_loaded()
    assert app.pipeline.logging is False and app.models.keep_loaded is True


def test_open_data_folder(app):
    app.open_data()
    assert app.opened == [str(app.store_dir)]


def test_corrections_marshalled_to_tk_thread(app):
    app.pipeline.open_corrections()
    assert app.opened == []  # not opened from the calling thread
    pump(app, until=lambda: app.opened)
    assert app.opened == ["window"]


def test_fallback_load_notifies(app):
    app.models.on_loaded("small (CPU fallback)")
    app.models.on_loaded("large-v3-turbo (GPU)")
    assert app.tray.notes == ["GPU unavailable — using small model on CPU"]


def test_unload_runs_in_background(app):
    import time
    app.unload()
    for _ in range(50):
        if app.models.unloaded:
            break
        time.sleep(0.01)
    assert app.models.unloaded == 1


def test_tick_scheduled(app):
    app.start(tick_ms=1)
    pump(app, until=lambda: app.models.ticks)
    assert app.models.ticks >= 1 and app.tray.started


def test_quit_stops_tray_and_loop(app):
    app.quit()
    pump(app, seconds=0.2)
    assert app.tray.stopped and app.stopping


def test_crash_log_captures_uncaught_errors(tmp_path):
    import sys
    import threading
    from voicetool.app import setup_crash_log

    log = tmp_path / "voicetool.log"
    old_sys, old_thread = sys.excepthook, threading.excepthook
    try:
        setup_crash_log(log)
        try:
            raise ValueError("main thread boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        t = threading.Thread(target=lambda: (_ for _ in ()).throw(RuntimeError("worker boom")))
        t.start(); t.join()
    finally:
        sys.excepthook, threading.excepthook = old_sys, old_thread
        import logging
        for h in logging.getLogger("voicetool").handlers[:]:
            h.close(); logging.getLogger("voicetool").removeHandler(h)
    text = log.read_text()
    assert "main thread boom" in text and "worker boom" in text and "Traceback" in text


class FakeRoot:
    def __init__(self):
        self.scheduled = []
        self.quit_called = False
        self.report_callback_exception = None

    def after(self, ms, fn):
        self.scheduled.append(fn)

    def quit(self):
        self.quit_called = True

    def run_scheduled(self):
        jobs, self.scheduled = self.scheduled, []
        for fn in jobs:
            fn()


def fake_root_app():
    root = FakeRoot()
    a = App(Config(), root, FakeStore(), FakeModels(),
            make_pipeline=lambda app: FakePipeline(), make_tray=lambda app: FakeTray(),
            opener=lambda p: None, open_corrections_window=lambda r, s: None)
    return a, root


def test_pump_survives_a_failing_call(caplog):
    import logging
    a, root = fake_root_app()
    ran = []
    a.call_soon(lambda: 1 / 0)
    a.call_soon(lambda: ran.append("next"))
    with caplog.at_level(logging.ERROR, logger="voicetool"):
        root.run_scheduled()
    assert ran == ["next"]
    assert any("ZeroDivisionError" in (r.exc_text or "") or r.exc_info for r in caplog.records)
    assert root.scheduled, "pump must keep rescheduling itself"


def test_tk_callback_errors_go_to_log(caplog):
    import logging
    a, root = fake_root_app()
    with caplog.at_level(logging.ERROR, logger="voicetool"):
        try:
            raise ValueError("tk boom")
        except ValueError:
            import sys
            root.report_callback_exception(*sys.exc_info())
    assert any("tk boom" in str(r.exc_info) for r in caplog.records)


def test_quit_from_tray_thread_never_touches_tk_directly():
    import threading
    a, root = fake_root_app()
    before = len(root.scheduled)
    t = threading.Thread(target=a.quit)
    t.start(); t.join()
    assert len(root.scheduled) == before  # only the queue was used
    root.run_scheduled()
    assert root.quit_called and a.tray.stopped
