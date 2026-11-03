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
