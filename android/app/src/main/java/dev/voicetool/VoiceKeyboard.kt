package dev.voicetool

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import dev.voicetool.core.Field
import dev.voicetool.core.FieldPolicy
import dev.voicetool.core.Pipeline
import dev.voicetool.core.Spacing
import dev.voicetool.core.TextSink
import java.util.concurrent.Executors
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit

/** The dictation keyboard: hold the mic, speak, release. */
class VoiceKeyboard : InputMethodService(), TextSink {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    @Volatile private var token = 0
    private var field = Field(true, true)
    private var status: TextView? = null
    private var mic: Button? = null
    private var state = "idle"
    private lateinit var pipeline: Pipeline
    private val tick = object : Runnable {
        override fun run() { VoiceTool.models(this@VoiceKeyboard).tick(); main.postDelayed(this, 30_000) }
    }

    override fun onCreate() {
        super.onCreate()
        pipeline = Pipeline(AndroidRecorder(), VoiceTool.models(this), VoiceTool.store(this), this,
            { VoiceTool.settings(this) }, { msg -> main.post { show(msg) } },
            { s -> main.post { setState(s) } }, worker)
        main.postDelayed(tick, 30_000)
    }

    override fun onDestroy() {
        main.removeCallbacks(tick)
        worker.shutdown()
        super.onDestroy()
    }

    // --- TextSink, called from the worker thread ---
    /** Types on the main thread, where focus changes happen, so "is this still his box?" and the
     *  typing itself can't be split by a focus change. */
    override fun commit(text: String, token: Int): Boolean {
        val task = FutureTask { commitHere(text, token) }
        main.post(task)
        return try { task.get(5, TimeUnit.SECONDS) } catch (e: Exception) { false }
    }

    private fun commitHere(text: String, expected: Int): Boolean {
        if (expected != token || !field.allowed) return false
        val ic = currentInputConnection ?: return false
        return ic.commitText(Spacing.join(ic.getTextBeforeCursor(1, 0), text), 1)
    }

    override fun onStartInput(info: EditorInfo, restarting: Boolean) {
        super.onStartInput(info, restarting)
        if (!restarting) token++  // a different text box: an old dictation must not land here
        field = FieldPolicy.of(info.inputType, info.imeOptions)
    }

    override fun onFinishInput() {
        token++
        pipeline.cancel()  // e.g. a call comes in mid-hold: the mic must not keep recording
        super.onFinishInput()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        pipeline.cancel()
        super.onFinishInputView(finishingInput)
    }

    override fun onStartInputView(info: EditorInfo, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        VoiceTool.applyModelChoice(this)
        VoiceTool.models(this).preload()  // load while he gets ready to speak
        setState(state)
        when {
            !field.allowed -> show("Password field: dictation is off here")
            VoiceTool.lowOnSpace(this) -> show("Phone storage is almost full")
            !Models.file(this, VoiceTool.settings(this).model).exists() -> show("Model missing: open Voice Tool")
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 16, 16, 24)
            setBackgroundColor(Color.parseColor("#1F2328"))
        }
        status = TextView(this).apply {
            setTextColor(Color.WHITE); textSize = 15f; gravity = Gravity.CENTER; setPadding(8, 8, 8, 16)
        }
        root.addView(status)
        mic = Button(this).apply {
            textSize = 20f
            setOnTouchListener { _, e ->
                when (e.action) {
                    MotionEvent.ACTION_DOWN -> pressMic()
                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> pipeline.release()
                }
                true
            }
        }
        root.addView(mic, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 320))
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 16, 0, 0) }
        fun key(label: String, action: () -> Unit) = row.addView(Button(this).apply {
            text = label; isAllCaps = false; setOnClickListener { action() }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        key("Delete last") { pipeline.deleteLast() }
        key("Insert last") {
            val t = pipeline.lastText
            if (t == null) show("Nothing to insert") else if (!commitHere(t, token)) show("Can't type here")
        }
        key("Recent") { open(RecentActivity::class.java) }
        key("⌨") { if (!switchToPreviousInputMethod()) show("Switch keyboards from the ⌨ icon") }
        root.addView(row)
        setState(state)
        return root
    }

    private fun pressMic() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            show("Allow the microphone first")
            open(SetupActivity::class.java)
            return
        }
        pipeline.press(field, token, currentInputEditorInfo?.packageName ?: "")
    }

    private fun open(cls: Class<*>) =
        startActivity(Intent(this, cls).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))

    private fun setState(s: String) {
        state = s
        mic?.text = when (s) { "recording" -> "● Listening… release to finish"; "working" -> "Writing…"; else -> "🎙  Hold to talk" }
        mic?.isEnabled = s != "working"
        if (s == "idle" && status?.tag == null) status?.text = "Voice Tool"
    }

    private fun show(msg: String) {
        Log.i("VoiceTool", msg)
        status?.text = msg
        status?.tag = msg
        main.postDelayed({ if (status?.tag == msg) { status?.tag = null; status?.text = "Voice Tool" } }, 5000)
    }
}
