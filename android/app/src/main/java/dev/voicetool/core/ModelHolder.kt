package dev.voicetool.core

import kotlin.concurrent.thread

/** Loads the speech model on demand and frees it after [idleMs] unused, like the desktop
 *  model_manager. Never frees it while a dictation is using it. */
class ModelHolder<T : Any>(
    private val loader: () -> T,
    private val close: (T) -> Unit,
    private val idleMs: Long,
    private val clock: () -> Long = { System.nanoTime() / 1_000_000 },
) {
    private val lock = Object()
    private var model: T? = null
    private var loading = false
    private var error: Throwable? = null
    private var inUse = 0
    private var lastUsed = clock()

    fun preload() {
        synchronized(lock) {
            if (model != null || loading) return
            loading = true
            error = null
        }
        thread(isDaemon = true, name = "model-load") {
            try {
                val m = loader()
                synchronized(lock) { model = m; lastUsed = clock() }
            } catch (e: Throwable) {
                synchronized(lock) { error = e }
            } finally {
                synchronized(lock) { loading = false; lock.notifyAll() }
            }
        }
    }

    fun <R> use(block: (T) -> R): R {
        preload()
        val m: T
        synchronized(lock) {
            while (model == null && loading) lock.wait()
            m = model ?: throw (error ?: IllegalStateException("model failed to load")).also { error = null }
            inUse++
        }
        try {
            return block(m)
        } finally {
            synchronized(lock) { inUse--; lastUsed = clock() }
        }
    }

    /** Call periodically; returns true if it freed the model. */
    fun tick(): Boolean = free { clock() - lastUsed >= idleMs }

    /** Free it now if no dictation is using it (e.g. a different model was chosen). */
    fun releaseNow(): Boolean = free { true }

    private fun free(due: () -> Boolean): Boolean {
        val m: T
        synchronized(lock) {
            m = model ?: return false
            if (inUse > 0 || !due()) return false
            model = null
        }
        close(m)
        return true
    }
}
