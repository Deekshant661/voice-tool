package dev.voicetool

import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.TextView
import android.widget.Toast
import dev.voicetool.core.BubbleGesture
import dev.voicetool.core.Field
import dev.voicetool.core.Insertion
import dev.voicetool.core.Pipeline
import dev.voicetool.core.TextSink
import java.util.concurrent.Executors
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit

/** A floating mic over every app: hold it, speak, release, and the text goes into the box that
 *  has the cursor, with his normal keyboard left alone. */
class MicBubbleService : AccessibilityService(), TextSink {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var pipeline: Pipeline
    private var bubble: TextView? = null
    private var params: WindowManager.LayoutParams? = null
    private var target: AccessibilityNodeInfo? = null
    private var token = 0
    private var pressed = false
    private val tick = object : Runnable {
        override fun run() { VoiceTool.models(this@MicBubbleService).tick(); main.postDelayed(this, 30_000) }
    }

    override fun onServiceConnected() {
        pipeline = Pipeline(AndroidRecorder(), VoiceTool.models(this), VoiceTool.store(this), this,
            { VoiceTool.settings(this) }, { msg -> main.post { toast(msg) } },
            { s -> main.post { setState(s) } }, worker)
        showBubble()
        main.postDelayed(tick, 30_000)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() { if (::pipeline.isInitialized) pipeline.cancel() }

    override fun onDestroy() {
        main.removeCallbacks(tick)
        if (::pipeline.isInitialized) pipeline.cancel()
        bubble?.let { getSystemService(WindowManager::class.java).removeView(it) }
        worker.shutdown()
        super.onDestroy()
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun showBubble() {
        val size = (56 * resources.displayMetrics.density).toInt()
        val p = WindowManager.LayoutParams(size, size, WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT).apply {
            gravity = Gravity.TOP or Gravity.START
            x = resources.displayMetrics.widthPixels - size - 8
            y = resources.displayMetrics.heightPixels / 3
        }
        val gesture = BubbleGesture(slopPx = 12 * resources.displayMetrics.density)
        var startX = 0; var startY = 0; var downX = 0f; var downY = 0f
        val view = TextView(this).apply {
            text = "🎙"; textSize = 22f; gravity = Gravity.CENTER
            setOnTouchListener { _, e ->
                val events = when (e.actionMasked) {
                    MotionEvent.ACTION_DOWN -> { startX = p.x; startY = p.y; downX = e.rawX; downY = e.rawY; gesture.down(e.rawX, e.rawY) }
                    MotionEvent.ACTION_MOVE -> gesture.move(e.rawX, e.rawY)
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> gesture.up()
                    else -> emptyList()
                }
                for (ev in events) when (ev) {
                    "press" -> press()
                    "cancel" -> { pressed = false; pipeline.cancel() }
                    "drag" -> {
                        p.x = startX + (e.rawX - downX).toInt(); p.y = startY + (e.rawY - downY).toInt()
                        getSystemService(WindowManager::class.java).updateViewLayout(this, p)
                    }
                    "release" -> if (pressed) { pressed = false; pipeline.release() }
                }
                true
            }
        }
        bubble = view; params = p
        getSystemService(WindowManager::class.java).addView(view, p)
        setState("idle")
    }

    private fun press() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            toast("Allow the microphone in the Voice Tool app first")
            return
        }
        val node = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (node == null || !node.isEditable) {
            toast("Tap a text box first")
            return
        }
        target = node
        token++
        pressed = true
        pipeline.press(Field(allowed = !node.isPassword, save = true), token, node.packageName?.toString() ?: "")
    }

    // --- TextSink, called from the worker thread; the box check and the insert run together ---
    override fun commit(text: String, token: Int): Boolean {
        val task = FutureTask { insert(text, token) }
        main.post(task)
        return try { task.get(5, TimeUnit.SECONDS) } catch (e: Exception) { false }
    }

    private fun insert(text: String, expected: Int): Boolean {
        val wanted = target ?: return false
        val now = findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return false
        if (expected != token || now != wanted || now.isPassword || !now.refresh()) return false
        val r = Insertion.apply(now.text?.toString() ?: "", now.textSelectionStart, now.textSelectionEnd,
            now.isShowingHintText, text)
        val set = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, r.text)
        }
        if (!now.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, set)) return false
        now.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, r.cursor)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, r.cursor)
        })
        return true
    }

    private fun setState(s: String) {
        val colour = when (s) { "recording" -> "#DC2626"; "working" -> "#D97706"; else -> "#2563EB" }
        bubble?.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(Color.parseColor(colour)); alpha = 230 }
        bubble?.text = if (s == "working") "…" else "🎙"
    }

    private fun toast(msg: String) {
        Log.i("VoiceTool", msg)
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}
