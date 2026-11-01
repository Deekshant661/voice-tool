"""Training-data store: one FLAC per dictation plus a SQLite index."""
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16000
log = logging.getLogger("voicetool")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dictations (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    duration_s REAL NOT NULL,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    corrected_text TEXT,
    window_title TEXT NOT NULL,
    process_name TEXT NOT NULL
)
"""


@dataclass
class Dictation:
    id: int
    created_at: str
    audio_path: Path
    duration_s: float
    raw_text: str
    cleaned_text: str
    corrected_text: str | None
    window_title: str
    process_name: str


class Store:
    def __init__(self, data_dir: Path):
        self.audio_dir = Path(data_dir) / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(data_dir) / "dictations.db"
        # Used from the pipeline worker and the correction window, so share one guarded connection.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.execute(_SCHEMA)
        self._db.commit()
        self._remove_orphans()

    def add(self, audio: np.ndarray, raw_text: str, cleaned_text: str,
            window_title: str, process_name: str) -> int:
        now = datetime.now()
        path = self._new_audio_path(now)
        sf.write(path, audio, SAMPLE_RATE, format="FLAC")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO dictations (created_at, audio_path, duration_s, raw_text, cleaned_text,"
                " window_title, process_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now.isoformat(timespec="seconds"), path.name, len(audio) / SAMPLE_RATE,
                 raw_text, cleaned_text, window_title, process_name),
            )
            self._db.commit()
            return cur.lastrowid

    def recent(self, n: int) -> list[Dictation]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created_at, audio_path, duration_s, raw_text, cleaned_text,"
                " corrected_text, window_title, process_name FROM dictations ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [Dictation(r[0], r[1], self.audio_dir / r[2], *r[3:]) for r in rows]

    def set_correction(self, id: int, text: str) -> None:
        with self._lock:
            self._db.execute("UPDATE dictations SET corrected_text = ? WHERE id = ?", (text, id))
            self._db.commit()

    def delete(self, id: int) -> None:
        with self._lock:
            row = self._db.execute("SELECT audio_path FROM dictations WHERE id = ?", (id,)).fetchone()
            if row is None:
                return
            self._db.execute("DELETE FROM dictations WHERE id = ?", (id,))
            self._db.commit()
        try:
            (self.audio_dir / row[0]).unlink(missing_ok=True)
        except OSError as e:  # open in another program; removed on next start instead
            log.warning("Could not delete %s yet: %s", row[0], e)

    def delete_last(self) -> bool:
        last = self.recent(1)
        if not last:
            return False
        self.delete(last[0].id)
        return True

    def total_bytes(self) -> int:
        files = sum(p.stat().st_size for p in self.audio_dir.glob("*.flac"))
        return files + self.db_path.stat().st_size

    def _remove_orphans(self) -> None:
        """Audio files whose row was deleted but the file was locked at the time."""
        with self._lock:
            known = {r[0] for r in self._db.execute("SELECT audio_path FROM dictations")}
        for path in self.audio_dir.glob("*.flac"):
            if path.name not in known:
                try:
                    path.unlink()
                except OSError:
                    pass

    def _new_audio_path(self, now: datetime) -> Path:
        stem = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"
        path = self.audio_dir / f"{stem}.flac"
        n = 1
        while path.exists():  # two dictations in the same millisecond
            path = self.audio_dir / f"{stem}-{n}.flac"
            n += 1
        return path
