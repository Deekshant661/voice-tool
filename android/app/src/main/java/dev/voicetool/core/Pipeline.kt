package dev.voicetool.core

import java.util.concurrent.Executor
import kotlin.math.abs

const val SAMPLE_RATE = 16000
private const val SILENCE_PEAK = 33  // 0.001 of full scale, the desktop threshold
// The desktop rule (faster-whisper): a segment is "not speech" only when Whisper both thinks
// it's silence AND was unsure of the words. High no_speech alone can still be real speech.
private const val NO_SPEECH_MAX = 0.6f
private const val LOGPROB_MIN = -1.0f

interface Recorder {
    fun start()
    fun stop(): ShortArray
    fun cancel()
}

data class Segment(val text: String, val noSpeechProb: Float, val avgLogprob: Float)

interface SpeechEngine {
    fun transcribe(pcm: FloatArray, prompt: String?): List<Segment>
}

interface Store {
    fun add(pcm: ShortArray, raw: String, cleaned: String, processName: String): Long
    fun delete(id: Long): Boolean
}

/** Where text goes. [commit] types only if [token] is still the text box being edited; it
 *  checks that and types in one step, so the box can't change in between. */
interface TextSink {
    fun commit(text: String, token: Int): Boolean
}

/** Hold → record, release → transcribe, clean, type, save. press/release/cancel run on the UI
 *  thread; the slow part runs on [worker], one dictation at a time and in order. */
class Pipeline(
    private val recorder: Recorder,
    private val models: ModelHolder<SpeechEngine>,
    private val store: Store,
    private val sink: TextSink,
    private val settings: () -> Settings,
    private val notify: (String) -> Unit,
    private val onState: (String) -> Unit,
    private val worker: Executor,
) {
    @Volatile var lastText: String? = null
        private set
    private var lastSavedId: Long? = null  // worker thread only
    private var recording = false
    private var field = Field(true, true)
    private var token = 0
    private var pkg = ""

    fun press(field: Field, token: Int, pkg: String) {
        if (recording) return
        if (!field.allowed) {
            notify("No dictation in password fields")
            return
        }
        models.preload()  // hidden behind him speaking
        try {
            recorder.start()
        } catch (e: Exception) {
            notify("Microphone unavailable: ${e.message}")
            onState("idle")
            return
        }
        this.field = field; this.token = token; this.pkg = pkg
        recording = true
        onState("recording")
    }

    /** The keyboard went away mid-hold: stop the microphone and keep nothing. */
    fun cancel() {
        if (!recording) return
        recording = false
        recorder.cancel()
        onState("idle")
    }

    fun release() {
        if (!recording) return
        recording = false
        val pcm = recorder.stop()
        val s = settings()
        if (pcm.size < s.minSeconds * SAMPLE_RATE) {
            onState("idle")
            return
        }
        if (pcm.all { abs(it.toInt()) < SILENCE_PEAK }) {
            notify("The microphone sent silence. Is another app using it?")
            onState("idle")
            return
        }
        onState("working")
        val field = field; val token = token; val pkg = pkg
        worker.execute { guarded { process(pcm, field, token, pkg, s) } }
    }

    fun deleteLast() = worker.execute {
        guarded {
            // Only the recording this keyboard just saved; never an older, unrelated one.
            val id = lastSavedId
            notify(when {
                id == null && lastText != null -> "The last dictation wasn't saved"
                id == null -> "Nothing to delete"
                store.delete(id) -> "Deleted last recording"
                else -> "Nothing to delete"
            })
            lastSavedId = null
        }
    }

    /** A crash here would kill the keyboard; report everything instead, even Errors. */
    private fun guarded(block: () -> Unit) {
        try {
            block()
        } catch (e: Throwable) {
            notify("Dictation failed: ${e.message}")
        } finally {
            onState("idle")
        }
    }

    private fun process(pcm: ShortArray, field: Field, token: Int, pkg: String, s: Settings) {
        val keep = field.save && s.saveRecordings
        val floats = FloatArray(pcm.size) { pcm[it] / 32768f }
        val segments = try {
            models.use { it.transcribe(floats, Settings.prompt(s.vocabulary)) }
        } catch (e: Throwable) {
            if (keep) lastSavedId = store.add(pcm, "", "", pkg)  // the audio is still worth keeping
            throw e
        }
        val raw = segments
            .filterNot { it.noSpeechProb > NO_SPEECH_MAX && it.avgLogprob < LOGPROB_MIN }
            .joinToString(" ") { it.text.trim() }.trim()
        val text = clean(raw, s.fillers, s.replacements)
        if (text.isEmpty()) {
            notify("No speech heard")
            return
        }
        lastText = text
        lastSavedId = null
        if (!sink.commit(text, token)) notify("Saved, not typed: the text box changed. Tap Insert last.")
        if (!keep) return
        try {
            lastSavedId = store.add(pcm, raw, text, pkg)
        } catch (e: Exception) {
            notify("Typed, but the recording wasn't saved: ${e.message}")
        }
    }
}
