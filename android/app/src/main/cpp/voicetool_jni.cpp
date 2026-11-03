// Bridge from Kotlin (WhisperEngine.kt) to whisper.cpp.
#include <jni.h>
#include <sched.h>
#include <cstring>
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

// Returns { float[] noSpeechProb, float[] avgLogprob, byte[][] utf8Text } per segment, or null.
// Text travels as raw UTF-8 bytes: NewStringUTF needs "modified UTF-8" and aborts on emoji or
// a token boundary that splits a character.
extern "C" JNIEXPORT jobjectArray JNICALL
Java_dev_voicetool_WhisperEngine_nativeTranscribe(
        JNIEnv *env, jclass, jlong handle, jfloatArray pcm, jbyteArray prompt, jintArray cores,
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

    std::string prompt_text;
    if (prompt) {
        jsize len = env->GetArrayLength(prompt);
        prompt_text.resize(len);
        env->GetByteArrayRegion(prompt, 0, len, reinterpret_cast<jbyte *>(&prompt_text[0]));
    }

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
    wp.initial_prompt = prompt ? prompt_text.c_str() : nullptr;

    jsize n = env->GetArrayLength(pcm);
    jfloat *samples = env->GetFloatArrayElements(pcm, nullptr);
    int rc = whisper_full(ctx, wp, samples, n);
    env->ReleaseFloatArrayElements(pcm, samples, JNI_ABORT);
    sched_setaffinity(0, sizeof(old_set), &old_set);
    if (rc != 0) {
        LOG("whisper_full failed: %d", rc);
        return nullptr;
    }

    int segs = whisper_full_n_segments(ctx);
    std::vector<jfloat> no_speech(segs), logprob(segs);
    jclass bytes_class = env->FindClass("[B");
    jobjectArray texts = env->NewObjectArray(segs, bytes_class, nullptr);
    const whisper_token eot = whisper_token_eot(ctx);
    for (int i = 0; i < segs; i++) {
        no_speech[i] = whisper_full_get_segment_no_speech_prob(ctx, i);
        double sum = 0;
        int count = 0;
        for (int j = 0; j < whisper_full_n_tokens(ctx, i); j++) {
            whisper_token_data t = whisper_full_get_token_data(ctx, i, j);
            if (t.id >= eot) continue;  // special tokens, not words
            sum += t.plog;
            count++;
        }
        logprob[i] = count ? static_cast<jfloat>(sum / count) : 0.0f;
        const char *text = whisper_full_get_segment_text(ctx, i);
        jsize len = static_cast<jsize>(strlen(text));
        jbyteArray b = env->NewByteArray(len);
        env->SetByteArrayRegion(b, 0, len, reinterpret_cast<const jbyte *>(text));
        env->SetObjectArrayElement(texts, i, b);
        env->DeleteLocalRef(b);
    }
    jfloatArray ns = env->NewFloatArray(segs);
    env->SetFloatArrayRegion(ns, 0, segs, no_speech.data());
    jfloatArray lp = env->NewFloatArray(segs);
    env->SetFloatArrayRegion(lp, 0, segs, logprob.data());
    jobjectArray out = env->NewObjectArray(3, env->FindClass("java/lang/Object"), nullptr);
    env->SetObjectArrayElement(out, 0, ns);
    env->SetObjectArrayElement(out, 1, lp);
    env->SetObjectArrayElement(out, 2, texts);
    env->DeleteLocalRef(bytes_class);
    return out;
}
