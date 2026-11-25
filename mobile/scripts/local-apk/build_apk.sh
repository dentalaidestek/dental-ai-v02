#!/bin/bash
# CI reçetesiyle aynı yerel APK derlemesi (mobile-android.yml · beta-apk job).
# arm64-v8a release APK, dev anahtarıyla imzalı — yalnızca iç test için.
set -euo pipefail
SDK=/home/z/my-project/android-sdk
REPO=/home/z/my-project/dental-ai-v02
OUT=/home/z/my-project/download
export ANDROID_HOME=$SDK
export ANDROID_SDK_ROOT=$SDK
PHASE=${1:-all}

if [[ "$PHASE" == "sdk" || "$PHASE" == "all" ]]; then
  echo "=== [1/4] SDK paketleri (platform-tools, android-36, build-tools 35)"
  if [ ! -d "$SDK/platforms/android-36" ]; then
    yes | "$SDK/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$SDK" \
      "platform-tools" "platforms;android-36" "build-tools;35.0.0" \
      >"$SDK/sdkmanager.log" 2>&1 || { tail -20 "$SDK/sdkmanager.log"; exit 1; }
  fi
  echo "SDK-OK: $(ls "$SDK/platforms" 2>/dev/null) / $(ls "$SDK/build-tools" 2>/dev/null)"
fi

if [[ "$PHASE" == "prebuild" || "$PHASE" == "all" ]]; then
  echo "=== [2/4] expo prebuild (android)"
  cd "$REPO/mobile"
  npx expo prebuild --platform android --no-install 2>&1 | tail -5
  [ -d android ] && echo "PREBUILD-OK"
fi

if [[ "$PHASE" == "gradle" || "$PHASE" == "all" ]]; then
  echo "=== [3/4] gradlew assembleRelease (arm64-v8a, Temurin 17, tek işçi/tek ninja işi)"
  export JAVA_HOME=/home/z/my-project/jdk17
  export PATH="$JAVA_HOME/bin:$PATH"
  # 3.9 GB RAM'li sandbox: native CMake derlemesinde çok paralellik OOM öldürür.
  export CMAKE_BUILD_PARALLEL_LEVEL=1
  export CMAKE_BUILD_PARALLEL_LEVELS=1
  # Metro (createBundleReleaseJsAndAssets) Node sürecinin heap'ini sınırla;
  # önceki OOM ölümleri tam bu aşamada oldu.
  export NODE_OPTIONS="--max-old-space-size=1400"
  cd "$REPO/mobile/android"
  ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a \
    --no-daemon --max-workers=1 \
    -Dorg.gradle.workers.max=1 \
    -Dorg.gradle.jvmargs="-Xmx1536m -XX:MaxMetaspaceSize=512m" \
    -Pkotlin.daemon.jvm.options=-Xmx512m \
    -Dorg.gradle.java.installations.paths=/home/z/my-project/jdk17 \
    -I /home/z/my-project/scripts/mirror-init.gradle \
    >"$REPO/mobile/gradle-build.log" 2>&1 || { echo "GRADLE-FAIL"; tail -40 "$REPO/mobile/gradle-build.log"; exit 1; }
  ls -lh app/build/outputs/apk/release/ && echo "GRADLE-OK"
fi

if [[ "$PHASE" == "collect" || "$PHASE" == "all" ]]; then
  echo "=== [4/4] APK → download/"
  mkdir -p "$OUT"
  cp "$REPO/mobile/android/app/build/outputs/apk/release/app-release.apk" \
     "$OUT/dental-ai-beta-arm64-20261125.apk"
  ls -lh "$OUT"/dental-ai-beta-arm64-20261125.apk
  sha256sum "$OUT"/dental-ai-beta-arm64-20261125.apk
  echo "COLLECT-OK"
fi
