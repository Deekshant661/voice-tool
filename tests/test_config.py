from pathlib import Path

from voicetool.config import load_config


def test_defaults_when_file_empty(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("")
    c = load_config(p)
    assert c.talk_key == "ctrl_r" and c.min_seconds == 0.3
    assert c.idle_unload_minutes == 30 and c.warn_gb == 5 and c.logging is True
    assert c.model_name == "large-v3-turbo" and c.fallback_model == "small"


def test_values_override(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[model]\nidle_unload_minutes = 5\n[cleanup.replacements]\n"pm 2" = "pm2"\n')
    c = load_config(p)
    assert c.idle_unload_minutes == 5 and c.replacements == {"pm 2": "pm2"}


def test_repo_config_loads():
    c = load_config(Path(__file__).parent.parent / "config.toml")
    assert "Vezras" in c.vocabulary
