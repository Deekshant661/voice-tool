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
    private var downAt = 0L
    private var lastTapAt: Long? = null  // end of the last short tap, waiting for a second one

    fun down(x: Float, y: Float, atMs: Long = 0): List<String> {
        x0 = x; y0 = y; dragging = false; downAt = atMs
        return listOf("press")
    }

    fun move(x: Float, y: Float): List<String> = when {
        dragging -> listOf("drag")
        hypot(x - x0, y - y0) > slopPx -> { dragging = true; listOf("cancel", "drag") }
        else -> emptyList()
    }

    fun up(atMs: Long = 0): List<String> {
        if (dragging) { lastTapAt = null; return listOf("dropped") }
        val tap = atMs - downAt < TAP_MS
        val double = tap && lastTapAt?.let { downAt - it < GAP_MS } == true
        lastTapAt = if (tap && !double) atMs else null
        // The short "release" is harmless: too short to transcribe, so nothing is saved.
        return if (double) listOf("release", "delete_last") else listOf("release")
    }

    private companion object {
        const val TAP_MS = 250L
        const val GAP_MS = 400L
    }
}
