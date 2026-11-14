cmake_minimum_required(VERSION 3.22)
project(voicetool C CXX)

# Debug builds of whisper.cpp are ~10x slower; always optimise the speech engine.
set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)

include(FetchContent)
FetchContent_Declare(whisper
    GIT_REPOSITORY https://github.com/ggml-org/whisper.cpp.git
    GIT_TAG v1.9.5            # MIT licence; pinned
    GIT_SHALLOW TRUE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
# The spike's flags: NEON dot-product + fp16 (i8mm measured no faster).
set(GGML_CPU_ARM_ARCH "armv8.2-a+dotprod+fp16" CACHE STRING "" FORCE)
FetchContent_MakeAvailable(whisper)

add_library(voicetool SHARED voicetool_jni.cpp)
target_link_libraries(voicetool whisper log)
