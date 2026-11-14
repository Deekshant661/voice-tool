package dev.voicetool.core

import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Which CPU cores to run Whisper on. Phones mix fast and battery-saving cores; on his phone,
 *  running on all of them was twice as slow as the four fast ones. */
object FastCores {
    fun pick(maxFreqKhz: List<Int>): List<Int> {
        val slowest = maxFreqKhz.minOrNull() ?: return emptyList()
        val fast = maxFreqKhz.indices.filter { maxFreqKhz[it] > slowest }
        return fast.ifEmpty { maxFreqKhz.indices.toList() }
    }
}

/** 16-bit PCM mono WAV, the shared data format's audio on Android. */
object Wav {
    fun encode(pcm: ShortArray, rate: Int): ByteArray {
        val data = pcm.size * 2
        val b = ByteBuffer.allocate(44 + data).order(ByteOrder.LITTLE_ENDIAN)
        b.put("RIFF".toByteArray()).putInt(36 + data).put("WAVE".toByteArray())
        b.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1)
            .putInt(rate).putInt(rate * 2).putShort(2).putShort(16)
        b.put("data".toByteArray()).putInt(data)
        pcm.forEach { b.putShort(it) }
        return b.array()
    }
}

/** Whisper's encoder window. It defaults to a fixed 30 s (1500); sizing it to the recording ran
 *  twice as fast on his phone. Floor of 512 (~10 s), the value tested for accuracy. */
object AudioCtx {
    fun forSamples(n: Int): Int {
        val needed = n * 50 / SAMPLE_RATE
        val rounded = (needed + 255) / 256 * 256
        return rounded.coerceIn(512, 1500)
    }
}

/** A space before the dictation when the cursor sits right after a word. */
object Spacing {
    fun join(before: CharSequence?, text: String): String =
        if (before.isNullOrEmpty() || before.last().isWhitespace()) text else " $text"
}
