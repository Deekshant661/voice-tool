"""'Recent dictations' window: fix words Whisper misheard, which become training data."""
import tkinter as tk
from datetime import datetime

from voicetool.store import Dictation, Store

HEADER = "Fix words Whisper misheard. Don't reword."
RECENT = 20

_open: "CorrectionsWindow | None" = None


class CorrectionsWindow:
    def __init__(self, root: tk.Tk, store: Store):
        self.store = store
        self.rows: list[Dictation] = []
        self.selected: Dictation | None = None
        self.win = tk.Toplevel(root)
        self.win.title("Voice Tool — recent dictations")
        self.win.geometry("720x420")
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._header = tk.Label(self.win, text=HEADER, anchor="w", font=("Segoe UI", 10, "bold"))
        self._header.pack(fill="x", padx=10, pady=(10, 4))
        self.listbox = tk.Listbox(self.win, height=10, font=("Consolas", 10), exportselection=False)
        self.listbox.pack(fill="both", expand=True, padx=10)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._on_list_select())
        self.editor = tk.Text(self.win, height=5, wrap="word", font=("Segoe UI", 11))
        self.editor.pack(fill="x", padx=10, pady=6)
        buttons = tk.Frame(self.win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(buttons, text="Save correction", command=self.save).pack(side="left")
        tk.Button(buttons, text="Delete recording", command=self.delete).pack(side="left", padx=6)
        tk.Button(buttons, text="Close", command=self.close).pack(side="right")
        self.refresh()
        self.win.focus_force()

    def refresh(self) -> None:
        self.rows = self.store.recent(RECENT)
        self.listbox.delete(0, "end")
        for d in self.rows:
            self.listbox.insert("end", self._label(d))

    @staticmethod
    def _label(d: Dictation) -> str:
        when = datetime.fromisoformat(d.created_at).strftime("%d %b %H:%M")
        mark = "✓" if d.corrected_text is not None else " "
        return f"{when}  {mark}  {(d.corrected_text or d.raw_text)[:60]}"

    def _on_list_select(self) -> None:
        sel = self.listbox.curselection()
        if sel:
            self.select(sel[0])

    def select(self, index: int) -> None:
        self.selected = self.rows[index]
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        # Raw text, not cleaned: training data should stay close to word-for-word.
        self.set_editor_text(self.selected.corrected_text or self.selected.raw_text)

    def save(self) -> None:
        if self.selected is None:
            return
        self.store.set_correction(self.selected.id, self.editor_text())
        index = [d.id for d in self.rows].index(self.selected.id)
        self.refresh()
        self.select(index)

    def delete(self) -> None:
        if self.selected is None:
            return
        self.store.delete(self.selected.id)
        self.selected = None
        self.set_editor_text("")
        self.refresh()

    def close(self) -> None:
        global _open
        _open = None
        self.win.destroy()

    def header_text(self) -> str:
        return self._header.cget("text")

    def row_labels(self) -> list[str]:
        return list(self.listbox.get(0, "end"))

    def editor_text(self) -> str:
        return self.editor.get("1.0", "end-1c").strip()

    def set_editor_text(self, text: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)


def open_window(root: tk.Tk, store: Store) -> CorrectionsWindow:
    global _open
    if _open is not None and _open.win.master is root and _open.store is store:
        try:
            if _open.win.winfo_exists():
                _open.win.lift()
                _open.win.focus_force()
                _open.refresh()
                return _open
        except tk.TclError:
            pass  # its Tk instance is gone
    _open = CorrectionsWindow(root, store)
    return _open
