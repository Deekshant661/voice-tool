from voicetool.model_manager import ModelManager


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(idle=1800):
    calls = []

    def loader():
        calls.append(1)
        return object(), "fake"

    clk = Clock()
    return ModelManager(loader, idle, clk), clk, calls


def test_loads_once():
    m, _, calls = make()
    m.ensure_loading()
    m.ensure_loading()
    with m.use() as model:
        assert model is not None
    assert len(calls) == 1 and m.label == "fake"


def test_idle_unload():
    m, clk, _ = make(10)
    with m.use():
        pass
    clk.t = 9
    assert m.tick() is False
    clk.t = 11
    assert m.tick() is True and not m.is_loaded


def test_no_unload_while_in_use():
    m, clk, _ = make(10)
    with m.use():
        clk.t = 100
        assert m.tick() is False and m.is_loaded


def test_keep_loaded():
    m, clk, _ = make(10)
    with m.use():
        pass
    m.keep_loaded = True
    clk.t = 100
    assert m.tick() is False


def test_reload_after_unload():
    m, clk, calls = make(10)
    with m.use():
        pass
    clk.t = 11
    m.tick()
    with m.use():
        pass
    assert len(calls) == 2


def test_manual_unload():
    m, _, _ = make()
    with m.use():
        pass
    m.unload()
    assert not m.is_loaded and m.label is None


def test_load_error_propagates_and_recovers():
    attempts = []

    def loader():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        return object(), "ok"

    m = ModelManager(loader, 10, Clock())
    try:
        with m.use():
            pass
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    with m.use() as model:
        assert model is not None
