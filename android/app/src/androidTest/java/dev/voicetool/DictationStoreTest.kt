package dev.voicetool

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDateTime

@RunWith(AndroidJUnit4::class)
class DictationStoreTest {
    private lateinit var dir: File
    private lateinit var store: DictationStore

    @Before fun open() {
        dir = File(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir, "store-test")
        dir.deleteRecursively()
        store = DictationStore(dir)
    }

    @After fun close() { store.close(); dir.deleteRecursively() }

    @Test fun columnsMatchTheSharedDataContract() {
        assertEquals(listOf("id", "created_at", "audio_path", "duration_s", "raw_text", "cleaned_text",
            "corrected_text", "window_title", "process_name", "device"), store.columns())
    }

    @Test fun savesAudioAndRowForThePhone() {
        store.add(ShortArray(16000) { 100 }, "restart PM 2", "Restart pm2", "com.whatsapp")
        val d = store.recent(1).single()
        assertEquals("restart PM 2", d.rawText)
        assertEquals("Restart pm2", d.cleanedText)
        assertNull(d.correctedText)
        assertEquals("", d.windowTitle)
        assertEquals("com.whatsapp", d.processName)
        assertEquals("android-phone", d.device)
        assertEquals(1.0, d.durationS, 1e-9)
        val wav = File(dir, "audio/${d.audioPath}")
        assertEquals(44 + 32000L, wav.length())
    }

    @Test fun timestampAlwaysHasSeconds() {
        assertEquals("2026-11-03T20:15:00", DictationStore.timestamp(LocalDateTime.of(2026, 11, 3, 20, 15, 0, 5)))
    }

    @Test fun correctionIsSavedAlongsideTheOriginal() {
        val id = store.add(ShortArray(16000), "vizras", "Vizras", "com.whatsapp")
        store.setCorrection(id, "Vezras")
        val d = store.recent(1).single()
        assertEquals("Vezras", d.correctedText)
        assertEquals("vizras", d.rawText)
    }

    @Test fun deleteLastRemovesRowAndAudio() {
        store.add(ShortArray(16000), "first", "First", "a")
        store.add(ShortArray(16000), "second", "Second", "a")
        val wav = File(dir, "audio/${store.recent(1).single().audioPath}")
        assertTrue(store.deleteLast())
        assertFalse(wav.exists())
        assertEquals(listOf("first"), store.recent(5).map { it.rawText })
        assertTrue(store.deleteLast())
        assertFalse(store.deleteLast())
    }

    @Test fun reportsItsSize() {
        store.add(ShortArray(16000), "a", "A", "a")
        assertTrue(store.totalBytes() > 32000)
    }
}
