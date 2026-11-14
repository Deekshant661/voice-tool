package dev.voicetool.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FieldPolicyTest {
    // android.text.InputType / EditorInfo values, so the test runs on the JVM.
    private val text = 0x1
    private val number = 0x2
    private val noLearning = 0x1000000

    @Test fun passwordFieldsAreRefused() {
        for (variation in listOf(0x80, 0x90, 0xe0)) {  // password, visible password, web password
            assertFalse("text variation $variation", FieldPolicy.of(text or variation, 0).allowed)
        }
        assertFalse(FieldPolicy.of(number or 0x10, 0).allowed)  // number password (PIN)
    }

    @Test fun ordinaryTextFieldsAreAllowedAndSaved() {
        val f = FieldPolicy.of(text or 0x2c000, 0)  // multi-line + cap sentences, like WhatsApp
        assertTrue(f.allowed)
        assertTrue(f.save)
    }

    @Test fun terminalsWithNoInputTypeAreAllowed() = assertTrue(FieldPolicy.of(0, 0).allowed)

    @Test fun phoneNumberFieldIsNotAPassword() = assertTrue(FieldPolicy.of(0x3, 0).allowed)

    @Test fun incognitoFieldsAreTypedButNeverSaved() {
        val f = FieldPolicy.of(text, noLearning)
        assertTrue(f.allowed)
        assertFalse(f.save)
    }
}

class SettingsTest {
    @Test fun replacementsOnePerLine() = assertEquals(
        mapOf("pm 2" to "pm2", "vizras" to "Vezras"),
        Settings.parseReplacements("pm 2 = pm2\n\n# comment\nvizras=Vezras\nbroken line\n"))

    @Test fun vocabularyCommaOrLineSeparated() = assertEquals(
        listOf("Vezras", "RDS", "pm2"), Settings.parseVocabulary("Vezras, RDS\n pm2 ,,"))

    @Test fun promptMatchesTheDesktopFormat() {
        assertEquals("Vezras, pm2.", Settings.prompt(listOf("Vezras", "pm2")))
        assertEquals(null, Settings.prompt(emptyList()))
    }

    @Test fun defaultsMatchConfigToml() {
        assertEquals(listOf("um", "uh", "uhm", "erm", "hmm"), Settings.DEFAULT_FILLERS)
        assertEquals(mapOf("pm 2" to "pm2"), Settings.parseReplacements(Settings.DEFAULT_REPLACEMENTS))
        assertTrue("Vezras" in Settings.parseVocabulary(Settings.DEFAULT_VOCABULARY))
    }
}
