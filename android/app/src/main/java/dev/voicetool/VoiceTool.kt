package dev.voicetool

import android.content.Context
import dev.voicetool.core.ModelHolder
import dev.voicetool.core.Settings
import dev.voicetool.core.SpeechEngine
import java.io.File

/** App-wide pieces shared by the keyboard and the screens (same process). */
object VoiceTool {
    const val IDLE_RELEASE_MS = 2 * 60 * 1000L
    const val LOW_SPACE_BYTES = 1_000_000_000L
    private const val PREFS = "settings"

    @Volatile private var store: DictationStore? = null
    @Volatile private var models: ModelHolder<SpeechEngine>? = null

    @Synchronized
    fun store(ctx: Context): DictationStore =
        store ?: DictationStore(File(ctx.filesDir, "data")).also { store = it }

    @Synchronized
    fun models(ctx: Context): ModelHolder<SpeechEngine> = models ?: ModelHolder<SpeechEngine>(
        loader = { WhisperEngine.load(Models.file(ctx, settings(ctx).model)) },
        close = { (it as WhisperEngine).close() },
        idleMs = IDLE_RELEASE_MS,
    ).also { models = it }

    fun settings(ctx: Context): Settings {
        val p = ctx.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return Settings(
            vocabulary = Settings.parseVocabulary(p.getString("vocabulary", Settings.DEFAULT_VOCABULARY)!!),
            replacements = Settings.parseReplacements(p.getString("replacements", Settings.DEFAULT_REPLACEMENTS)!!),
            model = p.getString("model", "small.en")!!,
            saveRecordings = p.getBoolean("save", true),
        )
    }

    fun rawSetting(ctx: Context, key: String, default: String): String =
        ctx.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(key, default)!!

    fun saveSettings(ctx: Context, vocabulary: String, replacements: String, model: String, save: Boolean) {
        ctx.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("vocabulary", vocabulary).putString("replacements", replacements)
            .putString("model", model).putBoolean("save", save).apply()
    }

    fun lowOnSpace(ctx: Context): Boolean = ctx.filesDir.usableSpace < LOW_SPACE_BYTES
}
