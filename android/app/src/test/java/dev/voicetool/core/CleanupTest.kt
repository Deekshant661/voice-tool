package dev.voicetool.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** The desktop cases from tests/test_cleanup.py: output must be identical on every device. */
class CleanupTest {
    private val f = listOf("um", "uh")

    @Test fun removesFillers() =
        assertEquals("Check the database.", clean("Um, check the uh database.", f, emptyMap()))

    @Test fun fillerInsideWordUntouched() =
        assertEquals("The umbrella is here.", clean("The umbrella is here.", f, emptyMap()))

    @Test fun replacementsWholeWordCaseInsensitive() =
        assertEquals("Restart pm2 now", clean("restart PM 2 now", f, mapOf("pm 2" to "pm2")))

    @Test fun emptyAndFillerOnly() {
        assertEquals("", clean("", f, emptyMap()))
        assertEquals("", clean("Um.", f, emptyMap()))
    }

    @Test fun doesNotAddOrChangePunctuation() =
        assertEquals("Git status", clean("git status", f, emptyMap()))

    @Test fun replacementTextIsTakenLiterally() =
        assertEquals("Cost $1", clean("cost one", f, mapOf("one" to "$1")))

    @Test fun unicodeSpacesCollapseLikePython() =
        assertEquals("Hello world", clean("hello\u00a0\u00a0world", f, emptyMap()))

    @Test fun accentedLettersCountAsPartOfAWord() =
        assertEquals("Umé stays", clean("umé stays", f, emptyMap()))

    @Test fun spaceBeforePunctuationRemoved() =
        assertEquals("Hello, world.", clean("hello , world .", f, emptyMap()))
}
