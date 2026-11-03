package dev.voicetool

import android.Manifest
import android.text.InputType
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import android.content.pm.PackageManager
import org.junit.Assume.assumeTrue
import dev.voicetool.core.FieldPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class KeyboardOnPhoneTest {
    /** What a real Android text box reports to a keyboard, run through our rule. */
    private fun allowed(type: Int): Boolean {
        var result = false
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val box = EditText(InstrumentationRegistry.getInstrumentation().targetContext)
            box.inputType = type
            val info = EditorInfo()
            box.onCreateInputConnection(info)
            result = FieldPolicy.of(info.inputType, info.imeOptions).allowed
        }
        return result
    }

    @Test fun realPasswordBoxesAreRefused() {
        assertFalse(allowed(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD))
        assertFalse(allowed(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD))
        assertFalse(allowed(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD))
        assertFalse(allowed(InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD))
    }

    @Test fun realMessageBoxIsAllowed() =
        assertTrue(allowed(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE))

    @Test fun recorderDeliversSixteenKilohertzAudio() {
        // OnePlus blocks test tools from granting the mic: allow it once in the app's Setup screen.
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        assumeTrue(ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED)
        val r = AndroidRecorder()
        r.start()
        Thread.sleep(1000)
        val pcm = r.stop()
        assertEquals(16000.0, pcm.size.toDouble(), 2500.0)  // ~1 s at 16 kHz
    }
}
