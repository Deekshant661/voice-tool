package dev.voicetool

import android.content.Context
import dev.voicetool.core.AudioCtx
import dev.voicetool.core.FastCores
import dev.voicetool.core.Segment
import dev.voicetool.core.SpeechEngine
import java.io.File

/** Where models live: the app's own folder, filled over USB (the app has no internet access). */
object Models {
    val NAMES = listOf("small.en", "base.en")
    fun dir(ctx: Context): File = File(ctx.getExternalFilesDir(null), "models").apply { mkdirs() }
    fun file(ctx: Context, name: String) = File(dir(ctx), "ggml-$name-q5_1.bin")
}

class WhisperEngine private constructor(private var handle: Long, private val cores: IntArray) :
    SpeechEngine {

    companion object {
        init { System.loadLibrary("voicetool") }

        fun load(model: File): WhisperEngine {
            require(model.exists()) { "Model not found: ${model.name}. Copy it with the README's adb push" }
            val h = nativeLoad(model.absolutePath)
            check(h != 0L) { "Could not load ${model.name}" }
            return WhisperEngine(h, fastCores())
        }

        private fun fastCores(): IntArray {
            val freqs = (0 until Runtime.getRuntime().availableProcessors()).map { cpu ->
                runCatching {
                    File("/sys/devices/system/cpu/cpu$cpu/cpufreq/cpuinfo_max_freq").readText().trim().toInt()
                }.getOrDefault(0)
            }
            return FastCores.pick(freqs).toIntArray()
        }

        @JvmStatic private external fun nativeLoad(path: String): Long
        @JvmStatic private external fun nativeFree(handle: Long)
        @JvmStatic private external fun nativeTranscribe(handle: Long, pcm: FloatArray, prompt: String?,
                                                         cores: IntArray, audioCtx: Int): Array<String>?
    }

    @Synchronized
    override fun transcribe(pcm: FloatArray, prompt: String?): List<Segment> {
        check(handle != 0L) { "model was released" }
        val raw = nativeTranscribe(handle, pcm, prompt, cores, AudioCtx.forSamples(pcm.size))
            ?: throw IllegalStateException("Whisper could not transcribe this recording")
        return raw.map { Segment(it.substringAfter('\t'), it.substringBefore('\t').toFloatOrNull() ?: 0f) }
    }

    @Synchronized
    fun close() {
        if (handle != 0L) nativeFree(handle)
        handle = 0
    }
}
