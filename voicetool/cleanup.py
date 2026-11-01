"""Rule-based tidy-up of Whisper output. Never rewords, only removes fillers and fixes spellings."""
import re


def clean(text: str, fillers: list[str], replacements: dict[str, str]) -> str:
    for filler in fillers:
        text = re.sub(rf"\b{re.escape(filler)}\b,?", "", text, flags=re.IGNORECASE)
    for wrong, right in replacements.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", lambda _: right, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.?!:])", r"\1", text)
    text = text.strip()
    if not re.search(r"\w", text):
        return ""
    return text[0].upper() + text[1:]
