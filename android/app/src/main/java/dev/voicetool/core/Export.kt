package dev.voicetool.core

import java.io.File
import java.io.OutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** Everything in one zip, so recordings survive an uninstall and can join the desktop ones:
 *  dictations.jsonl (one row per line, shared data format) + audio/<file>.wav. */
object Export {
    fun write(out: OutputStream, rows: List<Map<String, Any?>>, audio: (String) -> File): Int {
        ZipOutputStream(out).use { zip ->
            val jsonl = StringBuilder()
            for (row in rows) {
                val name = row["audio_path"] as? String
                val file = name?.let(audio)
                if (file != null && file.isFile) {
                    zip.putNextEntry(ZipEntry("audio/$name"))
                    file.inputStream().use { it.copyTo(zip) }
                    zip.closeEntry()
                }
                jsonl.append(json(row.mapValues { (k, v) -> if (k == "audio_path" && v != null) "audio/$v" else v })).append('\n')
            }
            zip.putNextEntry(ZipEntry("dictations.jsonl"))
            zip.write(jsonl.toString().toByteArray())
            zip.closeEntry()
        }
        return rows.size
    }

    private fun json(row: Map<String, Any?>) = row.entries.joinToString(",", "{", "}") { (k, v) -> "${str(k)}:${value(v)}" }

    private fun value(v: Any?): String = when (v) {
        null -> "null"
        is Number, is Boolean -> v.toString()
        else -> str(v.toString())
    }

    private fun str(s: String) = buildString {
        append('"')
        for (c in s) when {
            c == '"' -> append("\\\"")
            c == '\\' -> append("\\\\")
            c == '\n' -> append("\\n")
            c == '\r' -> append("\\r")
            c == '\t' -> append("\\t")
            c < ' ' -> append("\\u%04x".format(c.code))
            else -> append(c)
        }
        append('"')
    }
}
