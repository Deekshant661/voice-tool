package dev.voicetool.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class ModelHolderTest {
    @Test fun loadsOnceAndReuses() {
        var loads = 0
        val h = ModelHolder({ loads++; "model" }, {}, 1000)
        h.use { } ; h.use { }
        assertEquals(1, loads)
    }

    @Test fun releasedAfterIdleTime() {
        var now = 0L
        val closed = mutableListOf<String>()
        val h = ModelHolder({ "model" }, { closed += it }, 1000, clock = { now })
        h.use { }
        now = 999; h.tick()
        assertTrue(closed.isEmpty())
        now = 1000; h.tick()
        assertEquals(listOf("model"), closed)
    }

    @Test fun neverReleasedWhileADictationUsesIt() {
        var now = 0L
        val closed = mutableListOf<String>()
        val h = ModelHolder({ "model" }, { closed += it }, 1000, clock = { now })
        val inUse = CountDownLatch(1)
        val finish = CountDownLatch(1)
        val t = thread { h.use { inUse.countDown(); finish.await() } }
        inUse.await(2, TimeUnit.SECONDS)
        now = 5000; h.tick()
        assertTrue(closed.isEmpty())
        finish.countDown(); t.join()
    }

    @Test fun preloadStartsLoadingInTheBackground() {
        val loaded = CountDownLatch(1)
        val h = ModelHolder({ loaded.countDown(); "model" }, {}, 1000)
        h.preload()
        assertTrue(loaded.await(2, TimeUnit.SECONDS))
    }
}

class FastCoresTest {
    @Test fun picksTheCoresFasterThanTheSlowest() =
        assertEquals(listOf(4, 5, 6, 7),
            FastCores.pick(listOf(1804000, 1804000, 1804000, 1804000, 2400000, 2400000, 2400000, 2630000)))

    @Test fun allCoresWhenTheyAreTheSame() =
        assertEquals(listOf(0, 1), FastCores.pick(listOf(2000000, 2000000)))
}

class WavTest {
    @Test fun sixteenKilohertzMonoSixteenBit() {
        val wav = Wav.encode(shortArrayOf(1, -2, 3), 16000)
        assertEquals(44 + 6, wav.size)
        val b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals("RIFF", String(wav, 0, 4)); assertEquals("WAVE", String(wav, 8, 4))
        assertEquals(1, b.getShort(22).toInt())        // mono
        assertEquals(16000, b.getInt(24))              // sample rate
        assertEquals(16, b.getShort(34).toInt())       // bits
        assertEquals(6, b.getInt(40))                  // data bytes
        assertArrayEquals(byteArrayOf(1, 0, -2, -1, 3, 0), wav.copyOfRange(44, 50))
    }
}

class AudioCtxTest {
    // Whisper normally works on a fixed 30 s window (1500). Sized to the recording it ran 2x faster.
    @Test fun neverSmallerThanTenSeconds() = assertEquals(512, AudioCtx.forSamples(16000))
    @Test fun eightSecondsUsesTheSpikeValue() = assertEquals(512, AudioCtx.forSamples(8 * 16000))
    @Test fun growsWithLongerSpeech() = assertEquals(1024, AudioCtx.forSamples(18 * 16000))
    @Test fun neverMoreThanTheFullWindow() = assertEquals(1500, AudioCtx.forSamples(60 * 16000))
}

class SpacingTest {
    @Test fun startOfAnEmptyBox() = assertEquals("Hello", Spacing.join(null, "Hello"))
    @Test fun afterAWordAddsASpace() = assertEquals(" Hello", Spacing.join("I said", "Hello"))
    @Test fun afterASpaceOrNewLineAddsNothing() {
        assertEquals("Hello", Spacing.join("I said ", "Hello"))
        assertEquals("Hello", Spacing.join("line\n", "Hello"))
    }
    @Test fun emptyBeforeAddsNothing() = assertEquals("Hello", Spacing.join("", "Hello"))
}
