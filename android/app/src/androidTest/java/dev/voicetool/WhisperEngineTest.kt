package dev.voicetool

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.nio.ByteBuffer
import java.nio.ByteOrder

@RunWith(AndroidJUnit4::class)
class WhisperEngineTest {
    @Test fun transcribesASpokenSentenceOnThePhone() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val model = Models.file(ctx, "base.en")
        assumeTrue("push the model first (see android/README.md)", model.exists())
        val wav = InstrumentationRegistry.getInstrumentation().context.assets.open("say.wav").readBytes()
        val pcm = ByteBuffer.wrap(wav, 44, wav.size - 44).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        val floats = FloatArray(pcm.remaining()) { pcm.get(it) / 32768f }
        val engine = WhisperEngine.load(model)
        try {
            val text = engine.transcribe(floats, "Vezras, RDS, pm2, GitLab, Postgres.").joinToString(" ") { it.text }
            assertTrue(text, "Postgres" in text && "merge request" in text)
        } finally {
            engine.close()
        }
    }
}
