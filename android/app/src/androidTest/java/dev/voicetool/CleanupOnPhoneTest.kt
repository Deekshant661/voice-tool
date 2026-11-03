package dev.voicetool

import androidx.test.ext.junit.runners.AndroidJUnit4
import dev.voicetool.core.clean
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** Android's regex engine (ICU) is not the desktop JVM's: the same cases must pass on the phone. */
@RunWith(AndroidJUnit4::class)
class CleanupOnPhoneTest {
    private val f = listOf("um", "uh", "uhm", "erm", "hmm")

    @Test fun desktopCasesOnThePhone() {
        assertEquals("Check the database.", clean("Um, check the uh database.", f, emptyMap()))
        assertEquals("The umbrella is here.", clean("The umbrella is here.", f, emptyMap()))
        assertEquals("Restart pm2 now", clean("restart PM 2 now", f, mapOf("pm 2" to "pm2")))
        assertEquals("", clean("Um.", f, emptyMap()))
        assertEquals("Git status", clean("git status", f, emptyMap()))
        assertEquals("Cost $1", clean("cost one", f, mapOf("one" to "$1")))
        assertEquals("Hello world", clean("hello  world", f, emptyMap()))
        assertEquals("Hello, world.", clean("hello , world .", f, emptyMap()))
    }

    @Test fun accentedLettersCountAsPartOfAWord() =
        assertEquals("Umé stays", clean("umé stays", f, emptyMap()))
}
