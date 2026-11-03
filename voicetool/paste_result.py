"""What happened to a dictation's text at paste time. Shared by every platform."""
from enum import Enum


class PasteResult(Enum):
    PASTED = "pasted"
    COPIED_FOCUS_MOVED = "copied_focus_moved"
    COPIED_ELEVATED = "copied_elevated"
