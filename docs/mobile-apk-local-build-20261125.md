# Local sandbox APK build recipe (equivalent of .github/workflows/mobile-android.yml beta-apk job)

CI reçetesiyle aynı çıktıyı üreten, GitHub Actions dışında çalışabilen yerel
derleme akışı. 2026-11-25'te `376ebd12` (feature/mobile-ux-parity-20261125)
için doğrulandı; üretilen APK `dental-ai-beta-arm64-20261125.apk` (31 MB,
sha256 `b8e955d577e399e1ec8fc47706d40fcb5210458ab24fe614659caaff41bcfd18`).

## Neden yerel derleme?

- `mobile-android.yml` yalnızca iki yolla tetikleniyor: `workflow_dispatch` ve
  `feature/mobile-beta-20261110` tabanına PR. Sandbox PAT'i her ikisinde de
  403 döndürdü (`Resource not accessible by personal access token`:
  actions:write ve pull_requests:write izinleri yok).
- CI'daki en güncel APK koşusu #4970 (2026-11-23, `9620ce08`) — son iki commit
  (`7288993f` mobil UX paritesi, `376ebd12` yasal/destek/⋮ penceresi) bu
  APK'da yok.

## Ortam ve 4 göze çarpan engel

1. **SDK**: cmdline-tools + `platform-tools` + `platforms;android-36` +
   `build-tools;35.0.0` (`sdkmanager --sdk_root` ile, lisanslar `yes |`
   kabul edilerek). CMake 3.22.1'i Gradle ilk native derlemede kendisi
   kuruyor. cmdline-tools kurulduktan sonra silinebilir (295 MB kazanç).
2. **JDK**: Debian sandbox'ının `openjdk-21` paketi JRE-only (javac yok).
   CI ile aynı JDK olan Temurin 17'yi indir; derlemeyi
   `JAVA_HOME=<jdk17>` + `-Dorg.gradle.java.installations.paths=<jdk17>`
   ile yürüt. Hata imzası: `does not provide the required capabilities:
   [JAVA_COMPILER]`.
3. **Maven Central 429** (rate limit): `mirror-init.gradle` Aliyun aynalarını
   `pluginManagement` + her projenin `buildscript`/`project` repo'larına
   **ekler** (silmeden) — expo/react-native özel repo URL'leri korunur.
4. **3.9 GB RAM + 100% disk**: OOM ölümleri sırasıyla native CMake ve
   Metro bundle aşamasında oldu. Ayarlar: `--max-workers=1`,
   `-Dorg.gradle.workers.max=1`, `-Dorg.gradle.jvmargs=-Xmx1536m`,
   `-Pkotlin.daemon.jvm.options=-Xmx512m`, `CMAKE_BUILD_PARALLEL_LEVEL=1`,
   `NODE_OPTIONS=--max-old-space-size=1400` (Metro). Öksüz java süreçlerini
   öldür, ≥1.5 GB boş alan tut; `disk_janitor.sh` boşluk <150 MB'a düşerse
   yenilenebilir önbellekleri (kotlin-dsl, journal, daemon logları) siler.

## Derleme adımları

```bash
export JAVA_HOME=<jdk17>; export PATH="$JAVA_HOME/bin:$PATH"
export ANDROID_HOME=<sdk>; export CMAKE_BUILD_PARALLEL_LEVEL=1
export NODE_OPTIONS="--max-old-space-size=1400"
cd mobile && npx expo prebuild --platform android --no-install
cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a \
  --no-daemon --max-workers=1 -Dorg.gradle.workers.max=1 \
  -Dorg.gradle.jvmargs="-Xmx1536m -XX:MaxMetaspaceSize=512m" \
  -Pkotlin.daemon.jvm.options=-Xmx512m \
  -Dorg.gradle.java.installations.paths=<jdk17> \
  -I ../scripts/local-apk/mirror-init.gradle
```

Çıktı: `mobile/android/app/build/outputs/apk/release/app-release.apk`
(arm64-v8a, debug geliştirme anahtarıyla imzalı — yalnızca dahili test APK'sı,
mağaza imzası değil). Gradle task bazlı incremental: başarısız koşudan sonra
yeniden başlatmak pahalı aşamaları (bundle, native .cxx) yeniden kullanır.

## Doğrulama notları

- `apksigner verify --print-certs` → CN=Android Debug (beklenen).
- Yeni tur metinlerinin APK'da olup olmadığını kontrol ederken dikkat:
  Hermes bundle string tablosu UTF-16 yazıyor; ham `grep` Türkçe/uzun
  stringlerde yanlış negatif verir. `strings -e l` ile ara (örn.
  "Destek Talebi" ×2, "Topluluk Kurallar" ×1 bulundu; "HIZLI" yok —
  Hızlı İşlemler tamamen kaldırılmıştı).
- versionName/versionCode kaynağı `mobile/app.json`: 0.2.0 / 2, paket
  `tr.dentalai.app`.
