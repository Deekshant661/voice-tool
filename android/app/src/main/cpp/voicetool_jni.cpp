// Bridge from Kotlin (WhisperEngine.kt) to whisper.cpp.
#include <jni.h>
#include <sched.h>
#include <string>
#include <vector>
#include <android/log.h>
#include "whisper.h"

#define LOG(...) __android_log_print(ANDROID_LOG_INFO, "VoiceTool", __VA_ARGS__)

extern "C" JNIEXPORT jlong JNICALL
Java_dev_voicetool_WhisperEngine_nativeLoad(JNIEnv *env, jclass, jstring path) {
    const char *p = env->GetStringUTFChars(path, nullptr);
    whisper_context_params cp = whisper_context_default_params();
    cp.use_gpu = false;
    cp.flash_attn = true;
    whisper_context *ctx = whisper_init_from_file_with_params(p, cp);
    env->ReleaseStringUTFChars(path, p);
    return reinterpret_cast<jlong>(ctx);
}

extern "C" JNIEXPORT void JNICALL
Java_dev_voicetool_WhisperEngine_nativeFree(JNIEnv *, jclass, jlong ctx) {
    whisper_free(reinterpret_cast<whisper_context *>(ctx));
}

// Returns one "no_speech_prob<TAB>text" string per segment, or null on failure.
extern "C" JNIEXPORT jobjectArray JNICALL
Java_dev_voicetool_WhisperEngine_nativeTranscribe(
        JNIEnv *env, jclass, jlong handle, jfloatArray pcm, jstring prompt, jintArray cores,
        jint audioCtx) {
    auto *ctx = reinterpret_cast<whisper_context *>(handle);

    // Run on the fast cores only; whisper's worker threads inherit this from the calling thread.
    cpu_set_t old_set, fast;
    sched_getaffinity(0, sizeof(old_set), &old_set);
    CPU_ZERO(&fast);
    jsize n_cores = env->GetArrayLength(cores);
    std::vector<jint> ids(n_cores);
    env->GetIntArrayRegion(cores, 0, n_cores, ids.data());
    for (jint c : ids) CPU_SET(c, &fast);
    if (n_cores > 0) sched_setaffinity(0, sizeof(fast), &fast);

    whisper_full_params wp = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    wp.language = "en";
    wp.n_threads = n_cores > 0 ? (n_cores < 4 ? n_cores : 4) : 4;
    wp.audio_ctx = audioCtx;
    wp.no_context = true;
    wp.no_timestamps = true;
    wp.print_progress = false;
    wp.print_realtime = false;
    wp.print_timestamps = false;
    wp.print_special = false;
    const char *pr = prompt ? env->GetStringUTFChars(prompt, nullptr) : nullptr;
    wp.initial_prompt = pr;

    jsize n = env->GetArrayLength(pcm);
    jfloat *samples = env->GetFloatArrayElements(pcm, nullptr);
    int rc = whisper_full(ctx, wp, samples, n);
    env->ReleaseFloatArrayElements(pcm, samples, JNI_ABORT);
    if (pr) env->ReleaseStringUTFChars(prompt, pr);
    sched_setaffinity(0, sizeof(old_set), &old_set);
    if (rc != 0) {
        LOG("whisper_full failed: %d", rc);
        return nullptr;
    }

    int segs = whisper_full_n_segments(ctx);
    jobjectArray out = env->NewObjectArray(segs, env->FindClass("java/lang/String"), nullptr);
    for (int i = 0; i < segs; i++) {
        std::string s = std::to_string(whisper_full_get_segment_no_speech_prob(ctx, i)) + "\t" +
                        whisper_full_get_segment_text(ctx, i);
        jstring js = env->NewStringUTF(s.c_str());
        env->SetObjectArrayElement(out, i, js);
        env->DeleteLocalRef(js);
    }
    return out;
}
