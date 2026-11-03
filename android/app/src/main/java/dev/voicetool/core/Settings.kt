package dev.voicetool.core

/** The user's settings, with the same defaults as the desktop config.toml. */
data class Settings(
    val vocabulary: List<String> = parseVocabulary(DEFAULT_VOCABULARY),
    val replacements: Map<String, String> = parseReplacements(DEFAULT_REPLACEMENTS),
    val fillers: List<String> = DEFAULT_FILLERS,
    val model: String = "small.en",
    val saveRecordings: Boolean = true,
    val minSeconds: Double = 0.3,
) {
    companion object {
        val DEFAULT_FILLERS = listOf("um", "uh", "uhm", "erm", "hmm")
        const val DEFAULT_VOCABULARY = "Vezras, RDS, pm2, GitLab, Postgres, AWS, Claude, Jarvis"
        const val DEFAULT_REPLACEMENTS = "pm 2 = pm2"

        /** "what Whisper writes = what you want", one per line; # starts a comment. */
        fun parseReplacements(text: String): Map<String, String> = text.lines()
            .map { it.trim() }
            .filter { it.isNotEmpty() && !it.startsWith("#") && "=" in it }
            .associate { line -> line.substringBefore("=").trim() to line.substringAfter("=").trim() }
            .filterKeys { it.isNotEmpty() }

        fun parseVocabulary(text: String): List<String> =
            text.split(',', '\n').map { it.trim() }.filter { it.isNotEmpty() }

        /** Same as the desktop: the vocabulary list as Whisper's initial prompt. */
        fun prompt(vocabulary: List<String>): String? =
            if (vocabulary.isEmpty()) null else vocabulary.joinToString(", ") + "."
    }
}
