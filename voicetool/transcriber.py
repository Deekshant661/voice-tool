"""faster-whisper loading and transcription."""
import glob
import os
import site

import numpy as np

from voicetool.config import MODELS_DIR, Config


def _add_cuda_dll_dirs() -> None:
    # The CUDA libraries come from the nvidia-* pip packages; Windows only finds their DLLs
    # if their bin folders are registered before ctranslate2 loads.
    for root in site.getsitepackages():
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


_add_cuda_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402  (must follow the DLL setup)


def _open(name: str, device: str, compute_type: str):
    # Offline first: once a model is downloaded, loading must never touch the network.
    try:
        return WhisperModel(name, device=device, compute_type=compute_type,
                            download_root=str(MODELS_DIR), local_files_only=True)
    except FileNotFoundError:
        return WhisperModel(name, device=device, compute_type=compute_type,
                            download_root=str(MODELS_DIR), local_files_only=False)


def load_model(cfg: Config) -> tuple[object, str]:
    try:
        model = _open(cfg.model_name, cfg.device, cfg.compute_type)
        return model, f"{cfg.model_name} ({'GPU' if cfg.device == 'cuda' else cfg.device.upper()})"
    except Exception:
        model = _open(cfg.fallback_model, "cpu", "int8")
        return model, f"{cfg.fallback_model} (CPU fallback)"


def transcribe(model, audio: np.ndarray, cfg: Config) -> str:
    prompt = ", ".join(cfg.vocabulary) + "." if cfg.vocabulary else None
    segments, _ = model.transcribe(audio, beam_size=5, language=cfg.language,
                                   vad_filter=True, initial_prompt=prompt)
    return " ".join(s.text.strip() for s in segments).strip()
