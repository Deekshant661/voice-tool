package dev.voicetool

import android.app.Activity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.ListView
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Android 15+ draws apps behind the status bar; nothing of ours may end up hidden under it. */
@RunWith(AndroidJUnit4::class)
class ScreensOnPhoneTest {
    private fun top(v: View) = IntArray(2).also { v.getLocationOnScreen(it) }[1]

    private fun <T : Activity> checkBelowStatusBar(cls: Class<T>, find: (Activity) -> View) {
        ActivityScenario.launch(cls).use { s ->
            s.onActivity { a ->
                val root = a.window.decorView
                val bar = root.rootWindowInsets.getInsets(WindowInsets.Type.statusBars()).top
                val v = find(a)
                assertTrue("${cls.simpleName}: content at ${top(v)} is under the status bar (${bar})", top(v) >= bar)
                assertTrue("${cls.simpleName}: system title bar still shown", a.actionBar?.isShowing != true)
            }
        }
    }

    private fun firstText(v: View): TextView? = when (v) {
        is TextView -> v
        is ViewGroup -> (0 until v.childCount).firstNotNullOfOrNull { firstText(v.getChildAt(it)) }
        else -> null
    }

    @Test fun recentDictationsHeaderAndListAreVisible() =
        checkBelowStatusBar(RecentActivity::class.java) { a ->
            val list = generateSequence(listOf(a.window.decorView)) { level ->
                level.flatMap { if (it is ViewGroup) (0 until it.childCount).map(it::getChildAt) else emptyList() }
                    .ifEmpty { null }
            }.flatten().first { it is ListView }
            assertTrue("list must fill the space below the header", list.layoutParams.height == 0)
            firstText(a.window.decorView.findViewById(android.R.id.content))!!
        }

    @Test fun setupScreenTitleIsVisible() =
        checkBelowStatusBar(SetupActivity::class.java) { a -> firstText(a.window.decorView.findViewById(android.R.id.content))!! }

    @Test fun settingsTitleIsVisible() =
        checkBelowStatusBar(SettingsActivity::class.java) { a -> firstText(a.window.decorView.findViewById(android.R.id.content))!! }
}
