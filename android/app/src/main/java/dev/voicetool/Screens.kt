package dev.voicetool

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaPlayer
import android.os.Bundle
import android.provider.Settings as AndroidSettings
import android.view.inputmethod.InputMethodManager
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import dev.voicetool.core.Settings

private fun Context.column(vararg views: android.view.View) = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(40, 60, 40, 40)
    views.forEach { addView(it) }
}

private fun Context.label(text: String, size: Float = 16f) =
    TextView(this).apply { this.text = text; textSize = size; setPadding(0, 16, 0, 8) }

private fun Context.button(text: String, action: () -> Unit) =
    Button(this).apply { this.text = text; isAllCaps = false; setOnClickListener { action() } }

/** First screen: everything the keyboard needs, with the fix for anything missing. */
class SetupActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = label("", 17f)
        setContentView(ScrollView(this).apply {
            addView(column(
                label("Voice Tool", 26f), status,
                button("Allow the microphone") { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1) },
                button("Turn on the Voice Tool keyboard") { startActivity(Intent(AndroidSettings.ACTION_INPUT_METHOD_SETTINGS)) },
                button("Switch keyboard now") { getSystemService(InputMethodManager::class.java).showInputMethodPicker() },
                button("Recent dictations") { startActivity(Intent(this@SetupActivity, RecentActivity::class.java)) },
                button("Settings") { startActivity(Intent(this@SetupActivity, SettingsActivity::class.java)) },
            ))
        })
    }

    override fun onResume() { super.onResume(); refresh() }

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        refresh()
    }

    private fun refresh() {
        val mic = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        val enabled = getSystemService(InputMethodManager::class.java).enabledInputMethodList
            .any { it.packageName == packageName }
        val model = VoiceTool.settings(this).model
        val have = Models.NAMES.filter { Models.file(this, it).exists() }
        val store = VoiceTool.store(this)
        status.text = buildString {
            appendLine((if (mic) "✓" else "✗") + " Microphone " + if (mic) "allowed" else "not allowed")
            appendLine((if (enabled) "✓" else "✗") + " Keyboard " + if (enabled) "turned on" else "not turned on")
            appendLine((if (model in have) "✓" else "✗") + " Model $model " + if (model in have) "ready" else "missing")
            if (model !in have) appendLine("   Copy it from the Mac:\n   adb push ggml-$model-q5_1.bin ${Models.dir(this@SetupActivity)}/")
            appendLine("Recordings: %.1f MB".format(store.totalBytes() / 1e6))
            if (VoiceTool.lowOnSpace(this@SetupActivity)) appendLine("⚠ Phone storage is almost full")
            append("Uninstalling this app deletes its recordings.")
        }
    }
}

/** Fix words Whisper misheard; corrected entries are the valuable training data. */
class RecentActivity : Activity() {
    private var player: MediaPlayer? = null
    private lateinit var list: ListView
    private var rows: List<Dictation> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        list = ListView(this)
        setContentView(column(label("Fix words Whisper misheard. Don't reword.", 17f), list))
        list.setOnItemClickListener { _, _, i, _ -> edit(rows[i]) }
        refresh()
    }

    override fun onDestroy() { player?.release(); super.onDestroy() }

    private fun refresh() {
        rows = VoiceTool.store(this).recent(30)
        list.adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, rows.map {
            val mark = if (it.correctedText != null) "✓ " else ""
            "${it.createdAt.replace('T', ' ')}  $mark${(it.correctedText ?: it.rawText).take(70)}"
        })
    }

    private fun edit(d: Dictation) {
        // Raw text, not cleaned: training data should stay word-for-word.
        val box = EditText(this).apply { setText(d.correctedText ?: d.rawText) }
        AlertDialog.Builder(this).setTitle("What you really said").setView(box)
            .setPositiveButton("Save") { _, _ -> VoiceTool.store(this).setCorrection(d.id, box.text.toString().trim()); refresh() }
            .setNeutralButton("Play") { _, _ -> play(d); edit(d) }
            .setNegativeButton("Delete") { _, _ ->
                AlertDialog.Builder(this).setMessage("Delete this recording?")
                    .setPositiveButton("Delete") { _, _ -> VoiceTool.store(this).delete(d.id); refresh() }
                    .setNegativeButton("Keep", null).show()
            }.show()
    }

    private fun play(d: Dictation) {
        player?.release()
        player = MediaPlayer().apply {
            setDataSource(VoiceTool.store(this@RecentActivity).audioFile(d).absolutePath)
            prepare(); start()
        }
    }
}

class SettingsActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val vocab = EditText(this).apply { setText(VoiceTool.rawSetting(this@SettingsActivity, "vocabulary", Settings.DEFAULT_VOCABULARY)) }
        val repl = EditText(this).apply {
            setText(VoiceTool.rawSetting(this@SettingsActivity, "replacements", Settings.DEFAULT_REPLACEMENTS)); minLines = 3
        }
        val current = VoiceTool.settings(this)
        val models = RadioGroup(this)
        Models.NAMES.forEach { name ->
            models.addView(RadioButton(this).apply {
                text = if (name == "small.en") "small.en (most accurate, ~5 s)" else "base.en (faster, ~2 s, more mistakes)"
                id = name.hashCode(); isChecked = name == current.model
            })
        }
        val save = CheckBox(this).apply { text = "Save recordings (training data)"; isChecked = current.saveRecordings }
        setContentView(ScrollView(this).apply {
            addView(column(
                label("Settings", 24f),
                label("Words Whisper should spell your way (comma separated)"), vocab,
                label("Replacements, one per line: what Whisper writes = what you want"), repl,
                label("Model (a change applies within 2 minutes)"), models, save,
                button("Save") {
                    val model = Models.NAMES.first { it.hashCode() == models.checkedRadioButtonId }
                    VoiceTool.saveSettings(this@SettingsActivity, vocab.text.toString(), repl.text.toString(), model, save.isChecked)
                    finish()
                },
            ))
        })
    }
}
