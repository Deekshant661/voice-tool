package dev.voicetool.core

import java.util.concurrent.Executor
import kotlin.math.abs

const val SAMPLE_RATE = 16000
private const val SILENCE_PEAK = 33       // 0.001 of full scale, the desktop threshold
private const val NO_SPEECH_MAX = 0.6f    // same cut-off as the Mac: drop Whisper's "Thank you."

interface Recorder {
    fun start()
    fun stop(): ShortArray
    fun cancel()
}

data class Segment(val text: String, val noSpeechProb: Float)

interface SpeechEngine {
    fun transcribe(pcm: FloatArray, prompt: String?): List<Segment>
}

interface Store {
    fun add(pcm: ShortArray, raw: String, cleaned: String, processName: String): Long
    fun deleteLast(): Boolean
}

/** Where text goes. The token changes whenever the keyboard moves to another text box. */
interface TextSink {
    fun currentToken(): Int
    fun commit(text: String): Boolean
}

/** Hold → record, release → transcribe, clean, type, save. press/release run on the UI thread;
 *  the slow part runs on [worker], one dictation at a time and in order. */
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
        worker.execute {
            try {
                process(pcm, field, token, pkg, s)
            } catch (e: Exception) {
                notify("Dictation failed: ${e.message}")
            } finally {
                onState("idle")
            }
        }
    }

    fun deleteLast() = worker.execute {
        notify(if (store.deleteLast()) "Deleted last recording" else "Nothing to delete")
    }

    private fun process(pcm: ShortArray, field: Field, token: Int, pkg: String, s: Settings) {
        val floats = FloatArray(pcm.size) { pcm[it] / 32768f }
        val segments = models.use { it.transcribe(floats, Settings.prompt(s.vocabulary)) }
        val raw = segments.filter { it.noSpeechProb <= NO_SPEECH_MAX }
            .joinToString(" ") { it.text.trim() }.trim()
        val text = clean(raw, s.fillers, s.replacements)
        if (text.isEmpty()) {
            notify("No speech heard")
            return
        }
        lastText = text
        // Only type into the box he started in; anywhere else could be the wrong place.
        val typed = sink.currentToken() == token && sink.commit(text)
        if (!typed) notify("Saved, not typed: the text box changed. Tap Insert last.")
        if (field.save && s.saveRecordings) store.add(pcm, raw, text, pkg)
    }
}
