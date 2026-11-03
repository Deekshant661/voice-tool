"""mlx-whisper loading and transcription on Apple silicon. Same interface as the Windows
transcriber, plus release(): MLX keeps the weights in a class-level holder and its own memory
cache, so dropping our reference alone would leave the model in RAM."""
from dataclasses import dataclass
from pathlib import Path

import mlx_whisper
import numpy as np
from mlx.core import clear_cache, float16
from mlx_whisper.transcribe import ModelHolder

from voicetool.config import MODELS_DIR, Config


@dataclass(frozen=True)
class MlxModel:
    path: Path


def load_model(cfg: Config) -> tuple[MlxModel, str]:
    path = MODELS_DIR / cfg.model_name
    if not path.is_dir():
        raise FileNotFoundError(
            f"Model not found at {path}. Download it with: HF_HUB_DISABLE_XET=1 "
            f"hf download mlx-community/{cfg.model_name} --local-dir {path}")
    ModelHolder.get_model(str(path), float16)
    return MlxModel(path), f"{cfg.model_name} (Apple GPU)"


def transcribe(model: MlxModel, audio: np.ndarray, cfg: Config) -> str:
    prompt = ", ".join(cfg.vocabulary) + "." if cfg.vocabulary else None
    # One short utterance at a time: carrying text between windows only invites repetition.
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=str(model.path), language=cfg.language,
                                    initial_prompt=prompt, condition_on_previous_text=False,
                                    verbose=None)
    return result["text"].strip()


def release(model: MlxModel | None = None) -> None:
    ModelHolder.model = None
    ModelHolder.model_path = None
    clear_cache()
