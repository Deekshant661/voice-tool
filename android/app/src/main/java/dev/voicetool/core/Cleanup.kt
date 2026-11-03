package dev.voicetool.core

/** Rule-based tidy-up of Whisper output, a port of the desktop voicetool/cleanup.py.
 *  Never rewords: removes fillers, applies replacements, fixes spacing, capitalises. */
fun clean(text: String, fillers: List<String>, replacements: Map<String, String>): String {
    var t = text
    // (?U): Unicode word characters, as Python's re does by default.
    for (filler in fillers) {
        t = Regex("(?iU)\\b${Regex.escape(filler)}\\b,?").replace(t, "")
    }
    for ((wrong, right) in replacements) {
        t = Regex("(?iU)\\b${Regex.escape(wrong)}\\b").replace(t) { right }
    }
    t = Regex("(?U)\\s+").replace(t, " ")
    t = Regex("(?U)\\s+([,.?!:])").replace(t, "$1")
    t = t.trim()
    if (!Regex("(?U)\\w").containsMatchIn(t)) return ""
    return t.substring(0, 1).uppercase() + t.substring(1)
}
