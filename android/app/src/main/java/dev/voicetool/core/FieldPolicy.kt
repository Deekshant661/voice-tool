package dev.voicetool.core

/** What the keyboard may do in a text field. A keyboard sees everything typed, so passwords are
 *  refused outright, and fields that ask for no learning (incognito) are typed but never saved. */
data class Field(val allowed: Boolean, val save: Boolean)

object FieldPolicy {
    // android.text.InputType and EditorInfo constants (kept here so this runs on the JVM).
    private const val CLASS_MASK = 0xf
    private const val VARIATION_MASK = 0xff0
    private const val CLASS_TEXT = 0x1
    private const val CLASS_NUMBER = 0x2
    private val TEXT_PASSWORDS = setOf(0x80, 0x90, 0xe0)  // password, visible, web
    private const val NUMBER_PASSWORD = 0x10
    private const val IME_FLAG_NO_PERSONALIZED_LEARNING = 0x1000000

    fun of(inputType: Int, imeOptions: Int): Field {
        val cls = inputType and CLASS_MASK
        val variation = inputType and VARIATION_MASK
        val password = (cls == CLASS_TEXT && variation in TEXT_PASSWORDS) ||
            (cls == CLASS_NUMBER && variation == NUMBER_PASSWORD)
        if (password) return Field(allowed = false, save = false)
        return Field(allowed = true, save = imeOptions and IME_FLAG_NO_PERSONALIZED_LEARNING == 0)
    }
}
