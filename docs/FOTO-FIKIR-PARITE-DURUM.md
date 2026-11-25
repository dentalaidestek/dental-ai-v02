Foto Fikir SocialDent paritesi + UI metin temizliği — durum notu (2026-11-26)

Dal: feature/mobile-ux-parity-20261125

BU DALDA UYGULANMIŞ (GitHub'da canlı):
- mobile/src/fotoFikirApi.ts — FFCreativeAudit tipi + generate-image creative_audit alanı
- mobile/src/NativeFotoFikir.tsx — SocialDent web /foto-fikir ile birebir akış:
  adım göstergesi (1 Konu / 2 Metin onayı / 3 Görsel), slayt sayısı (3-8) ve ton
  (bilgilendirici/samimi/profesyonel/eğitici) seçimi + Metinleri yenile,
  kart başına N/220 karakter sayacı, mevzuat özet satırı, stil kartlarında ipucu,
  Yapı Puanı (creative_audit) paneli + geliştirme önerileri, altyazılı galeri
  (Slayt N — stil / Marka kiti — sahne), DİKKAT rozeti Türkçe İ ile.

YEREL KLONDA COMMITLİ (01239301), BU DALA YAMA OLARAK EKLENECEK:
- mobile/patches/ui-text-cleanup-{A,B,C}.patch — 12 dosyalık gereksiz teorik/
  kullanım metin temizliği (Akademik, ModernScreens, SocialScreens, VoiceExamEntry,
  NativeVoiceRecorder, NativeClinicalReview, NativeAnalysisUpload, NativeAccount,
  NativePatientProfile, NativeToothChart, NativeAuth, NativeProgramEditor).
  Web paritesinde testle sabitlenen klinik/gizlilik metinleri bilinçli olarak korundu.
  Depo kökünden: git apply mobile/patches/ui-text-cleanup-{A,B,C}.patch
- Tam mobil süit bu içerikle 1065/1065 + 22 + 54 test geçer; tsc --noEmit temiz.
- Taban: f2870455a55b86feafffe5612fa3e7145400d992

APK: dental-ai-beta-arm64-20261125.apk (yerel derleme, 32.3 MB, 2026-11-25 14:45 UTC)
f2870455 tabanlıdır; bugünkü Foto Fikir paritesi ve metin temizliğini İÇERMEZ.
Resmi yayın yoktur (KESİN YAYIN KURALI); yalnızca test amaçlıdır.
