"""Turns raw key presses into dictation events. Platform-neutral: keys are plain names."""


class HotkeyMachine:
    def __init__(self, talk: str, corrections: str, delete_last: str):
        self.talk = talk
        self.corrections = corrections
        self.delete_last = delete_last
        self._held = False
        self._cancelled = False

    def down(self, key: str) -> list[str]:
        if key == self.talk:
            if self._held:  # auto-repeat while held
                return []
            self._held, self._cancelled = True, False
            return ["start"]
        if not self._held or self._cancelled:
            return []
        # Talk key combined with anything else is a shortcut, not a dictation.
        self._cancelled = True
        events = ["cancel"]
        if key == self.corrections:
            events.append("corrections")
        elif key == self.delete_last:
            events.append("delete_last")
        return events

    def up(self, key: str) -> list[str]:
        if key != self.talk or not self._held:
            return []
        self._held = False
        return [] if self._cancelled else ["stop"]
