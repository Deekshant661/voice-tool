"""Settings loaded from config.toml, with defaults for anything missing."""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Heavy files (venv, model, recordings) live outside OneDrive and outside AppData:
# packaged apps get AppData redirected into a private sandbox.
APP_DIR = Path(os.environ["USERPROFILE"]) / ".voice-tool"
MODELS_DIR = APP_DIR / "models"
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass(frozen=True)
class Config:
    talk_key: str = "ctrl_r"
    corrections_key: str = "shift_r"
    delete_last_key: str = "delete"
    model_name: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    fallback_model: str = "small"
    idle_unload_minutes: float = 30
    keep_loaded: bool = False
    min_seconds: float = 0.3
    language: str = "en"
    vocabulary: list[str] = field(default_factory=list)
    fillers: list[str] = field(default_factory=lambda: ["um", "uh", "uhm", "erm", "hmm"])
    replacements: dict[str, str] = field(default_factory=dict)
    logging: bool = True
    warn_gb: float = 5


# Config field -> (toml section, toml key)
_FIELDS = {
    "talk_key": ("hotkeys", "talk"),
    "corrections_key": ("hotkeys", "corrections"),
    "delete_last_key": ("hotkeys", "delete_last"),
    "model_name": ("model", "name"),
    "device": ("model", "device"),
    "compute_type": ("model", "compute_type"),
    "fallback_model": ("model", "fallback"),
    "idle_unload_minutes": ("model", "idle_unload_minutes"),
    "keep_loaded": ("model", "keep_loaded"),
    "min_seconds": ("dictation", "min_seconds"),
    "language": ("dictation", "language"),
    "vocabulary": ("dictation", "vocabulary"),
    "fillers": ("cleanup", "fillers"),
    "replacements": ("cleanup", "replacements"),
    "logging": ("data", "logging"),
    "warn_gb": ("data", "warn_gb"),
}


def load_config(path: Path = CONFIG_PATH) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    values = {}
    for name, (section, key) in _FIELDS.items():
        if key in raw.get(section, {}):
            values[name] = raw[section][key]
    return Config(**values)
