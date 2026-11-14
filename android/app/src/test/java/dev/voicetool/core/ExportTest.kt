package dev.voicetool.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipInputStream

class ExportTest {
    private fun unzip(bytes: ByteArray): Map<String, String> {
        val out = mutableMapOf<String, String>()
        ZipInputStream(ByteArrayInputStream(bytes)).use { z ->
            while (true) { val e = z.nextEntry ?: break; out[e.name] = z.readBytes().decodeToString() }
        }
        return out
    }

    @Test fun zipHoldsEveryDictationInTheSharedFormatWithItsAudio() {
        val dir = createTempDir()
        File(dir, "a.wav").writeText("RIFF-a")
        val rows = listOf(
            linkedMapOf<String, Any?>("id" to 1L, "created_at" to "2026-11-03T21:00:00", "audio_path" to "a.wav",
                "duration_s" to 2.5, "raw_text" to "say \"hi\"\nnow", "cleaned_text" to "Say \"hi\" now",
                "corrected_text" to null, "window_title" to "", "process_name" to "com.whatsapp", "device" to "android-phone"),
            linkedMapOf<String, Any?>("id" to 2L, "audio_path" to "missing.wav"))
        val buf = ByteArrayOutputStream()
        val count = Export.write(buf, rows) { File(dir, it) }
        val files = unzip(buf.toByteArray())
        assertEquals(2, count)
        assertEquals("RIFF-a", files["audio/a.wav"])
        assertTrue("audio/missing.wav" !in files)  // a lost file doesn't stop the export
        val lines = files.getValue("dictations.jsonl").trim().lines()
        assertEquals(2, lines.size)
        assertEquals("""{"id":1,"created_at":"2026-11-03T21:00:00","audio_path":"audio/a.wav","duration_s":2.5,""" +
            """"raw_text":"say \"hi\"\nnow","cleaned_text":"Say \"hi\" now","corrected_text":null,""" +
            """"window_title":"","process_name":"com.whatsapp","device":"android-phone"}""", lines[0])
    }
}
