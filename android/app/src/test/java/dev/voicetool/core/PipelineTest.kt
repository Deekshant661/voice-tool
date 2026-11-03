package dev.voicetool.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.Executor

private const val SR = 16000

class FakeRecorder : Recorder {
    var next = ShortArray(SR) { 3000 }
    var failStart: Exception? = null
    var started = 0
    override fun start() { failStart?.let { throw it }; started++ }
    override fun stop(): ShortArray = next
    var cancelled = 0
    override fun cancel() { cancelled++ }
}

class FakeEngine : SpeechEngine {
    var segments = listOf(Segment(" um restart PM 2 now", 0.05f, -0.2f))
    var error: Throwable? = null
    var prompts = mutableListOf<String?>()
    override fun transcribe(pcm: FloatArray, prompt: String?): List<Segment> {
        prompts += prompt
        error?.let { throw it }
        return segments
    }
}

class FakeStore : Store {
    val added = mutableListOf<Triple<String, String, String>>()  // raw, cleaned, package
    val ops = mutableListOf<String>()
    var addError: Exception? = null
    val deleted = mutableListOf<Long>()
    override fun add(pcm: ShortArray, raw: String, cleaned: String, processName: String): Long {
        addError?.let { throw it }
        ops += "add"; added += Triple(raw, cleaned, processName); return added.size.toLong()
    }
    override fun delete(id: Long): Boolean { ops += "delete $id"; deleted += id; return true }
}

class FakeSink : TextSink {
    var token = 1
    val typed = mutableListOf<String>()
    var accept = true
    override fun commit(text: String, token: Int): Boolean {
        val ok = accept && token == this.token
        if (ok) typed += text
        return ok
    }
}

class Harness(settings: Settings = Settings()) {
    val recorder = FakeRecorder()
    val engine = FakeEngine()
    val store = FakeStore()
    val sink = FakeSink()
    val notes = mutableListOf<String>()
    val states = mutableListOf<String>()
    val p = Pipeline(recorder, ModelHolder({ engine }, {}, 60_000), store, sink, { settings },
                     notes::add, states::add, Executor { it.run() })
    fun dictate(field: Field = Field(true, true), pkg: String = "com.whatsapp") {
        p.press(field, sink.token, pkg); p.release()
    }
}

class PipelineTest {
    @Test fun dictationIsCleanedTypedAndSavedWithTheApp() {
        val h = Harness()
        h.dictate()
        assertEquals(listOf("Restart pm2 now"), h.sink.typed)
        assertEquals(listOf(Triple("um restart PM 2 now", "Restart pm2 now", "com.whatsapp")), h.store.added)
        assertEquals(listOf("recording", "working", "idle"), h.states)
    }

    @Test fun vocabularyIsThePrompt() {
        val h = Harness(Settings(vocabulary = listOf("Vezras", "pm2")))
        h.dictate()
        assertEquals(listOf<String?>("Vezras, pm2."), h.engine.prompts)
    }

    @Test fun passwordFieldRecordsNothing() {
        val h = Harness()
        h.dictate(Field(allowed = false, save = false))
        assertEquals(0, h.recorder.started)
        assertTrue(h.sink.typed.isEmpty() && h.store.added.isEmpty())
        assertEquals(listOf("No dictation in password fields"), h.notes)
    }

    @Test fun releaseUnderThreeTenthsOfASecondDoesNothing() {
        val h = Harness()
        h.recorder.next = ShortArray(SR / 5) { 3000 }
        h.dictate()
        assertTrue(h.engine.prompts.isEmpty() && h.store.added.isEmpty() && h.notes.isEmpty())
        assertEquals("idle", h.states.last())
    }

    @Test fun silenceIsReportedNotIgnored() {
        val h = Harness()
        h.recorder.next = ShortArray(SR) { 10 }
        h.dictate()
        assertEquals(listOf("The microphone sent silence. Is another app using it?"), h.notes)
        assertTrue(h.engine.prompts.isEmpty())
    }

    @Test fun fieldChangedWhileWorkingSavesButDoesNotType() {
        val h = Harness()
        h.p.press(Field(true, true), 1, "com.whatsapp")
        h.sink.token = 2  // he moved to another text box before the text came back
        h.p.release()
        assertTrue(h.sink.typed.isEmpty())
        assertEquals(1, h.store.added.size)
        assertEquals("Restart pm2 now", h.p.lastText)
        assertEquals(listOf("Saved, not typed: the text box changed. Tap Insert last."), h.notes)
    }

    @Test fun typingRefusedByTheAppKeepsTheWords() {
        val h = Harness()
        h.sink.accept = false
        h.dictate()
        assertEquals(1, h.store.added.size)
        assertEquals("Restart pm2 now", h.p.lastText)
    }

    @Test fun incognitoFieldIsTypedButNotSaved() {
        val h = Harness()
        h.dictate(Field(allowed = true, save = false))
        assertEquals(listOf("Restart pm2 now"), h.sink.typed)
        assertTrue(h.store.added.isEmpty())
    }

    @Test fun savingTurnedOffStillTypes() {
        val h = Harness(Settings(saveRecordings = false))
        h.dictate()
        assertEquals(1, h.sink.typed.size)
        assertTrue(h.store.added.isEmpty())
    }

    @Test fun segmentsWhisperRatesAsNotSpeechAreDropped() {
        val h = Harness()
        h.engine.segments = listOf(Segment(" Deploy it.", 0.05f, -0.3f), Segment(" Thank you.", 0.9f, -1.5f))
        h.dictate()
        assertEquals(listOf("Deploy it."), h.sink.typed)
    }

    @Test fun nothingHeardSaysSo() {
        val h = Harness()
        h.engine.segments = listOf(Segment(" Thank you.", 0.9f, -1.4f))
        h.dictate()
        assertTrue(h.sink.typed.isEmpty() && h.store.added.isEmpty())
        assertEquals(listOf("No speech heard"), h.notes)
    }

    @Test fun engineFailureIsShownAndTheKeyboardRecovers() {
        val h = Harness()
        h.engine.error = IllegalStateException("model file missing")
        h.dictate()
        assertEquals(listOf("Dictation failed: model file missing"), h.notes)
        assertEquals("idle", h.states.last())
        h.engine.error = null
        h.dictate()
        assertEquals(1, h.sink.typed.size)
    }

    @Test fun micThatWontStartIsReported() {
        val h = Harness()
        h.recorder.failStart = IllegalStateException("no permission")
        h.dictate()
        assertEquals(listOf("Microphone unavailable: no permission"), h.notes)
        assertEquals("idle", h.states.last())
    }

    @Test fun deleteLastRunsAfterTheDictationBeforeIt() {
        val h = Harness()
        h.dictate()
        h.p.deleteLast()
        assertEquals(listOf("add", "delete 1"), h.store.ops)
        assertEquals(listOf("Deleted last recording"), h.notes)
    }

    @Test fun deleteLastNeverDeletesAnOlderRecordingWhenTheLastWasntSaved() {
        val h = Harness()
        h.dictate()
        h.dictate(Field(allowed = true, save = false))  // incognito: typed, not saved
        h.p.deleteLast()
        assertTrue(h.store.deleted.isEmpty())
        assertEquals(listOf("The last dictation wasn't saved"), h.notes)
    }

    @Test fun deleteLastTwiceDeletesOnlyOnce() {
        val h = Harness()
        h.dictate()
        h.p.deleteLast(); h.p.deleteLast()
        assertEquals(listOf(1L), h.store.deleted)
    }

    @Test fun confidentSpeechIsKeptEvenWhenNoSpeechIsHigh() {
        // Desktop rule: drop only if no_speech > 0.6 AND avg_logprob < -1.0.
        val h = Harness()
        h.engine.segments = listOf(Segment(" Deploy it.", 0.7f, -0.2f))
        h.dictate()
        assertEquals(listOf("Deploy it."), h.sink.typed)
    }

    @Test fun modelLoadErrorDoesNotCrashTheKeyboard() {
        val h = Harness()
        h.engine.error = OutOfMemoryError("model too big")
        h.dictate()
        assertEquals("idle", h.states.last())
        assertTrue(h.notes.single().startsWith("Dictation failed: model too big"))
    }

    @Test fun failedTranscriptionStillKeepsTheRecording() {
        val h = Harness()
        h.engine.error = IllegalStateException("whisper failed")
        h.dictate()
        assertEquals(listOf(Triple("", "", "com.whatsapp")), h.store.added)
    }

    @Test fun saveFailureAfterTypingSaysSoAccurately() {
        val h = Harness()
        h.store.addError = IllegalStateException("disk full")
        h.dictate()
        assertEquals(listOf("Restart pm2 now"), h.sink.typed)
        assertEquals(listOf("Typed, but the recording wasn't saved: disk full"), h.notes)
    }

    @Test fun keyboardClosingMidHoldStopsTheMicAndDiscards() {
        val h = Harness()
        h.p.press(Field(true, true), 1, "com.whatsapp")
        h.p.cancel()
        h.p.release()
        assertTrue(h.engine.prompts.isEmpty() && h.store.added.isEmpty())
        assertEquals(1, h.recorder.cancelled)
        assertEquals("idle", h.states.last())
        h.dictate()
        assertEquals(1, h.sink.typed.size)  // the next press works
    }
}
