package dev.voicetool

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import dev.voicetool.core.Recorder
import dev.voicetool.core.SAMPLE_RATE
import kotlin.concurrent.thread

/** 16 kHz mono 16-bit from the microphone, straight into memory. Capped at 5 minutes. */
class AndroidRecorder : Recorder {
    private val maxSamples = SAMPLE_RATE * 300
    @Volatile private var running = false
    private var worker: Thread? = null
    private var buffer = ShortArray(0)
    private var size = 0

    @SuppressLint("MissingPermission")  // checked by the keyboard before press
    override fun start() {
        val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, SAMPLE_RATE))
        check(rec.state == AudioRecord.STATE_INITIALIZED) { rec.release(); "microphone busy or denied" }
        buffer = ShortArray(SAMPLE_RATE * 10)
        size = 0
        running = true
        rec.startRecording()
        worker = thread(name = "recorder") {
            val chunk = ShortArray(1600)
            try {
                while (running && size < maxSamples) {
                    val n = rec.read(chunk, 0, chunk.size)
                    if (n <= 0) break
                    synchronized(this) {
                        if (size + n > buffer.size) buffer = buffer.copyOf(maxOf(buffer.size * 2, size + n))
                        System.arraycopy(chunk, 0, buffer, size, n)
                        size += n
                    }
                }
            } finally {
                rec.stop()
                rec.release()
            }
        }
    }

    override fun stop(): ShortArray {
        running = false
        worker?.join(1000)
        worker = null
        return synchronized(this) { buffer.copyOf(size) }
    }

    override fun cancel() {
        stop()
    }
}
