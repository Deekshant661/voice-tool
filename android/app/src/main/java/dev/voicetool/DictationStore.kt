package dev.voicetool

import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import dev.voicetool.core.SAMPLE_RATE
import dev.voicetool.core.Store
import dev.voicetool.core.Wav
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

data class Dictation(
    val id: Long, val createdAt: String, val audioPath: String, val durationS: Double,
    val rawText: String, val cleanedText: String, val correctedText: String?,
    val windowTitle: String, val processName: String, val device: String,
)

/** Training-data store: one WAV per dictation plus a SQLite index, in the shared data format
 *  (same columns as the desktop `dictations` table, plus `device`). */
class DictationStore(private val dir: File) : Store {
    private val audioDir = File(dir, "audio").apply { mkdirs() }
    private val db = SQLiteDatabase.openOrCreateDatabase(File(dir, "dictations.db"), null).apply {
        execSQL("""CREATE TABLE IF NOT EXISTS dictations (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, audio_path TEXT NOT NULL,
            duration_s REAL NOT NULL, raw_text TEXT NOT NULL, cleaned_text TEXT NOT NULL,
            corrected_text TEXT, window_title TEXT NOT NULL, process_name TEXT NOT NULL,
            device TEXT NOT NULL)""")
    }

    companion object {
        const val DEVICE = "android-phone"
        private val ISO = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")
        private val FILE = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS")
        fun timestamp(t: LocalDateTime): String = t.format(ISO)
    }

    fun columns(): List<String> = db.rawQuery("PRAGMA table_info(dictations)", null).use { c ->
        generateSequence { if (c.moveToNext()) c.getString(1) else null }.toList()
    }

    @Synchronized
    override fun add(pcm: ShortArray, raw: String, cleaned: String, processName: String): Long {
        val now = LocalDateTime.now()
        var file = File(audioDir, "${now.format(FILE)}.wav")
        var n = 1
        while (file.exists()) file = File(audioDir, "${now.format(FILE)}-${n++}.wav")
        file.writeBytes(Wav.encode(pcm, SAMPLE_RATE))
        return db.insertOrThrow("dictations", null, ContentValues().apply {
            put("created_at", timestamp(now)); put("audio_path", file.name)
            put("duration_s", pcm.size.toDouble() / SAMPLE_RATE); put("raw_text", raw)
            put("cleaned_text", cleaned); put("window_title", ""); put("process_name", processName)
            put("device", DEVICE)
        })
    }

    @Synchronized
    fun recent(n: Int): List<Dictation> = db.rawQuery(
        "SELECT id, created_at, audio_path, duration_s, raw_text, cleaned_text, corrected_text," +
            " window_title, process_name, device FROM dictations ORDER BY id DESC LIMIT ?",
        arrayOf(n.toString())).use { c ->
        generateSequence {
            if (!c.moveToNext()) null else Dictation(c.getLong(0), c.getString(1), c.getString(2),
                c.getDouble(3), c.getString(4), c.getString(5), if (c.isNull(6)) null else c.getString(6),
                c.getString(7), c.getString(8), c.getString(9))
        }.toList()
    }

    fun audioFile(d: Dictation) = File(audioDir, d.audioPath)

    @Synchronized
    fun setCorrection(id: Long, text: String) {
        db.update("dictations", ContentValues().apply { put("corrected_text", text) }, "id = ?",
            arrayOf(id.toString()))
    }

    @Synchronized
    override fun delete(id: Long): Boolean {
        val path = db.rawQuery("SELECT audio_path FROM dictations WHERE id = ?", arrayOf(id.toString()))
            .use { if (it.moveToFirst()) it.getString(0) else null } ?: return false
        db.delete("dictations", "id = ?", arrayOf(id.toString()))
        File(audioDir, path).delete()
        return true
    }

    @Synchronized
    fun deleteLast(): Boolean {
        val last = recent(1).firstOrNull() ?: return false
        delete(last.id)
        return true
    }

    fun totalBytes(): Long =
        (audioDir.listFiles()?.sumOf { it.length() } ?: 0L) + File(dir, "dictations.db").length()

    fun close() = db.close()
}
