package dev.voicetool.core

// Written to mean the same on the desktop JVM (where the unit tests run) and on Android's ICU
// regex engine, which rejects the (?U) flag. Spelled out to match Python's Unicode \w, \b and \s.
private const val WORD = "[\\p{L}\\p{N}_]"
private const val START = "(?<!$WORD)"
private const val END = "(?!$WORD)"
private const val SPACE = "[\\s\\p{Z}]"

/** Rule-based tidy-up of Whisper output, a port of the desktop voicetool/cleanup.py.
 *  Never rewords: removes fillers, applies replacements, fixes spacing, capitalises. */
fun clean(text: String, fillers: List<String>, replacements: Map<String, String>): String {
    var t = text
    for (filler in fillers) {
        t = Regex("(?i)$START${Regex.escape(filler)}$END,?").replace(t, "")
    }
    for ((wrong, right) in replacements) {
        t = Regex("(?i)$START${Regex.escape(wrong)}$END").replace(t) { right }
    }
    t = Regex("$SPACE+").replace(t, " ")
    t = Regex("$SPACE+([,.?!:])").replace(t, "$1")
    t = t.trim { it.isWhitespace() || Character.isSpaceChar(it) }
    if (!Regex(WORD).containsMatchIn(t)) return ""
    return t.substring(0, 1).uppercase() + t.substring(1)
}
