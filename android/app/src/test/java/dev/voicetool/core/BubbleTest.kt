package dev.voicetool.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** Putting dictated text into a box's existing text at the cursor (the bubble can't "type"). */
class InsertionTest {
    @Test fun intoAnEmptyBox() =
        assertEquals(Insertion.Result("Hello", 5), Insertion.apply("", 0, 0, false, "Hello"))

    @Test fun theHintIsNotRealText() =
        assertEquals(Insertion.Result("Hello", 5), Insertion.apply("Type a message", 0, 0, true, "Hello"))

    @Test fun atTheEndAfterAWordAddsASpace() =
        assertEquals(Insertion.Result("I said Hello", 12), Insertion.apply("I said", 6, 6, false, "Hello"))

    @Test fun inTheMiddleKeepsWhatFollows() =
        assertEquals(Insertion.Result("A Hello B", 7), Insertion.apply("A B", 2, 2, false, "Hello"))

    @Test fun replacesSelectedText() =
        assertEquals(Insertion.Result("Say Hello", 9), Insertion.apply("Say this", 4, 8, false, "Hello"))

    @Test fun unknownCursorMeansTheEnd() =
        assertEquals(Insertion.Result("Hi Hello", 8), Insertion.apply("Hi", -1, -1, false, "Hello"))

    @Test fun selectionBackwardsIsHandled() =
        assertEquals(Insertion.Result("Say Hello", 9), Insertion.apply("Say this", 8, 4, false, "Hello"))
}

/** Hold the bubble to talk; move it to reposition (which must not count as a dictation). */
class BubbleGestureTest {
    private fun run(vararg steps: Pair<String, Float>): List<String> {
        val g = BubbleGesture(slopPx = 30f)
        return steps.flatMap { (kind, x) ->
            when (kind) {
                "down" -> g.down(x, 0f)
                "move" -> g.move(x, 0f)
                else -> g.up()
            }
        }
    }

    @Test fun holdAndReleaseIsADictation() =
        assertEquals(listOf("press", "release"), run("down" to 0f, "move" to 5f, "up" to 0f))

    @Test fun draggingCancelsTheRecordingAndMovesTheBubble() =
        assertEquals(listOf("press", "cancel", "drag", "drag", "dropped"),
            run("down" to 0f, "move" to 40f, "move" to 80f, "up" to 0f))
}
