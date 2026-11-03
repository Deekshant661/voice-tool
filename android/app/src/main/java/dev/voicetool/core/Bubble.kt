package dev.voicetool.core

import kotlin.math.hypot

/** The bubble can't type like a keyboard; it sets the box's whole text. This works out the new
 *  text with the dictation at the cursor, and where the cursor goes afterwards. */
object Insertion {
    data class Result(val text: String, val cursor: Int)

    fun apply(existing: String, selStart: Int, selEnd: Int, isHint: Boolean, dictation: String): Result {
        val base = if (isHint) "" else existing
        var s = minOf(selStart, selEnd)
        var e = maxOf(selStart, selEnd)
        if (s < 0 || e > base.length) { s = base.length; e = base.length }
        val before = base.substring(0, s)
        val after = base.substring(e)
        val inserted = Spacing.join(before, dictation)
        val gap = if (after.isNotEmpty() && after.first().isLetterOrDigit()) " " else ""
        return Result(before + inserted + gap + after, s + inserted.length)  // cursor right after the words
    }
}

/** Hold the bubble to talk; moving it past [slopPx] repositions it instead. */
class BubbleGesture(private val slopPx: Float) {
    private var x0 = 0f
    private var y0 = 0f
    private var dragging = false

    fun down(x: Float, y: Float): List<String> {
        x0 = x; y0 = y; dragging = false
        return listOf("press")
    }

    fun move(x: Float, y: Float): List<String> = when {
        dragging -> listOf("drag")
        hypot(x - x0, y - y0) > slopPx -> { dragging = true; listOf("cancel", "drag") }
        else -> emptyList()
    }

    fun up(): List<String> = listOf(if (dragging) "dropped" else "release")
}
