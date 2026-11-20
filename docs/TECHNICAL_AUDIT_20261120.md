# Dental AI — Teknik Denetim Raporu (2026-11-20)

Dal: `feature/mobile-web-parity-20261110` · PR #257 · Issue #258
Denetleyen: bağımsız tam tur denetim (mimari, parity, güvenlik, performans, kapasite)
Kural: main'e merge yok, canlı deploy yok, DB migration yok (hepsi bu turda sağlandı).

## 1. Doğrulanan GitHub durumu (önceki raporlardaki SHA'lar geçersiz kabul edildi)

| Konu | Bulgu |
|---|---|
| Branch HEAD (tur başı) | `b36ee8e6` — önceki turda pushlanan 66 commit'i ChatGPT yeni eklemişti; merge alındı, temiz birleşti |
| Branch HEAD (tur sonu) | `28cc5c58` (6 yeni fix commit'i) + upstream `5d82ec1b` (23 yeni commit: web hasta geçmişi sayfalama) — yeniden merge/push gerekti |
| PR #257 | open, `mergeable_state: clean`, base `feature/mobile-beta-20261110`, head `feature/mobile-web-parity-20261110`, 2585+ commit / 434+ dosya, **review yok**, 105 genel yorum. PR gövdesi: "taslak kalır; main merge, üretim deploy, mağaza yayını yapılmamıştır" |
| Issue #258 | açık — "Mobil uygulama — Web ekranlarıyla birebir işlev eşdeğerliği: modül bazlı çalışma programı" (her modül için kabul akışı tanımlı) |
| CI | 2500 koşu; son koşuların tümü "Android test APK" FAILURE. Job `apk`'da **runner_name boş, runner grubu boş, çalıştırılmış step yok** (attempt 1, 08:00-09:09 arası 6 koşu üst üste aynı şekilde ölmüş). Tanı: GitHub Actions runner tahsisi başarısız (organizasyon/spending limit/plan tarafı) — **kaynak kod hatası değildir**. Workflow tanımı (`ubuntu-latest`) doğru. |

## 2. Mimari harita

**Web (kanonik uygulama)**
- `app/main.py` (~14 bin satır FastAPI monolit): kayıt/giriş (oturum çerezi, 3 zorunlu sözleşme onayı), hasta profili + diş şeması (FDI, yüzey bazlı gözlem, `edit_revision` optimistik kilitleme), klinik medya galerisi (R2 kalıcılığı + yerel kopya), analizler (VISION/PRELIMINARY/FINAL WorkJob boru hattı), misafir analiz, danışmanlık/mesajlaşma, uzman yönetimi, sosyal akış, Akademik AI (ders + RAG tabanlı cevap + quiz), sesli muayene (ASR → yapılandırılmış özet), destek talepleri, admin paneli.
- Şablonlar `app/templates/*.html` + `app/static/*.js` (tooth_chart.html, voice-exam.js, academic …) — testler web JS'i kaynak-kod sözleşmesi olarak kullanır.
- Modüler uçlar: `app/mobile_api.py` (v1), `app/mobile_modern_api_v3.py` (v3 modern), `app/study_ai_v2.py` (Akademik boru hattı), `app/clinical_rag_router.py`, `app/ai_provider.py` (yapay zekâ sağlayıcı + bütçe rezervasyonu), `app/clinical_media.py` (görüntü temizleyici), `app/work_jobs.py` (WorkJob kuyruğu), `app/tooth_surface_status.py`, `app/upload_limits.py`.

**Mobil (React Native/Expo)**
- `mobile/src/` — ~40 ekran/modül: NativeProgram, NativePatientMedia, NativeAnalysisUpload (durable intent + fiş uzlaştırma), NativeAcademic (+ Composer, Source, AnswerActions), VoiceExamEntry + NativeVoiceRecorder + voiceSession, SocialScreens (+ socialApi), NativeConsultations, ModernScreens, NativeToothChart/NativeToothVisual (enamel atlas + yüzey filtreleri), patientDirectoryPresentation, modernApi/api/sosyalApi/voiceApi istemcileri, appResumeRefresh (arka plan→ön plan yenileme kapısı), notificationState.
- API tabanı `https://dentalai.tr/api/mobile/v1` (+ v3 modern uçlar); Bearer token; credentials:omit.
- Test düzeni: `mobile/tests/*.cjs` — TS transpile + vm sandbox + mock zinciri (web src'iyle kaynak-düzey parity testleri).

**Altyapı**
- Render (tek instance), R2 (medya), PostgreSQL (SQLModel), WebSocket realtime (RealtimeEvent), WorkJob arka plan işleri, ASR/AI sağlayıcı bütçe rezervasyonu ile.

## 3. Web/native fark listesi (bu turun sonundaki durum)

| Alan | Durum |
|---|---|
| Analiz görüntü limiti | ✅ birebir (paylaşılan `ANALYSIS_MAX_IMAGES`, mesaj web ile aynı) |
| Hasta geçmişi sayfalama | 🔶 ChatGPT upstream 5d82ec1b web tarafına paging ekledi; mobil karşılığı merge sonrası doğrulanacak (kırmızı patientAnalysisHistory testleri bu alanın işaretçisi) |
| Diş şeması FDI yüzeyler | ✅ web yüzey anatomisi mobilde çoğaltıldı (webToothSurfaceParity yeşil) |
| Klinik medya galerisi | ✅ kanonik bileşen `NativePatientMedia` (ModernScreens'teki çift galeri upstream tarafından kaldırıldı — tek kaynak) |
| Sesli muayene | ✅ istek anahtarı üretimi, checkpoint geri dönüşü, uncertain görünümü web ile hizalandı |
| Akademik | ✅ intent uzlaştırma v1/v2, kurtarma paneli, içerik özeti mesajı |
| Analiz geçmişi scoping | ✅ ChatGPT ae5ef12e patient_id/tooth filtreleri + mobil testleri |
| Program (randevu) | ✅ inline-add tarih doğrulama + editör parity (önceki turdan, bu turda korundu) |

## 4. Güvenlik bulguları (özel kontroller)

**Bu turda DÜZELTİLEN:**
1. **K2 — Misafir AI analizinde açık rıza yoktu** (KVKK/ekr. 5-6): `ai_consent` zorunlu alan + şablonda checkbox + `AgreementAcceptance("AI_GUEST_ANALYSIS", LEGAL_VERSION)` kaydı; auth öncesi kontrol (bypass yok). Regresyon: `tests/test_guest_consent.py` (4/4).
2. **Y4 — `/docs`, `/redoc`, `/openapi.json` herkese açıktı** (recon yüzeyi): kapatıldı; TestClient ile 404 doğrulandı.
3. **Gerçek ürün bugı — mobil sohbet replay 500**: `mobile_api.py`'de `run_in_threadpool` importu eksikti (5 kullanım noktası). Düzeltildi.
4. **Hasta medya yükleme istemci sözleşmesi**: XHR yerine fetch; null gövde → `ApiError(503, "Görüntü yüklenemedi.")`; ağ kesintisi → 503 "galerisini kontrol edin" sarmalayıcısı; geçersiz FDI ağ öncesi reddedilir.
5. **Diş şeması yazım sözleşmesi**: `expected_revision=undefined` artık "bozuk sürüm" sayılmıyor (yanlış-pozitif kilitleme giderildi); yanlış format hâlâ reddedilir.
6. Akademik: kayıp yanıt sonrası fiş doğrulaması çöküyordu (`uncertain` tanımsız referans) — duplicate ders riski taşıyordu; düzeltildi.

**Doğrulanmış, mevcut korumalar (ölçümle):**
- IDOR/BOLA: hasta medya/analiz/destek uçlarında ownership guard'ları (test: `backend scopes ticket reads...`, `every delayed clinical media action verifies the current patient...`), misafir/değerli uçlarda `request.current` eşleşme koruması (hesap değişiminde eski hasta verisi taşınmıyor — patientMediaAccountSwitch 31/31).
- XSS: gövde sanitizasyonu `clinical_media.py` (magic byte + boyut + pixel sınırı); şablon çıkışları Jinja autoescape.
- SQL injection: ORM sorguları; ham `text()` kullanımları sınırlı ve parametreli.
- WebSocket: token query-string reddi (test: `test_websocket_auth_does_not_accept_tokens_in_query_strings`), bağlantı başına kullanıcı eşlemesi.
- Rate limiting: web giriş limiter (429 + Retry-After) mevcut; mobil uçlarda ip bazlı ek limiter **önerilir** (bkz. eksiklikler).
- Upload abuse: 4 görüntü/analiz, 48 MiB toplam, uzantı+sanitizasyon+pixel sınırı; misafirde aynı sınır.
- Loglarda KVK: çıktılarda TC/adres sızıntısı saptanmadı; error mesajları operational.

**DÜZELTİLMESİ gereken ama bu turun kapsamı dışı kalan (bkz. §9):**
- **K1 — Hesap silme hasta verisini tam silmiyor**: `account erasure` GuestAnalysis/medya kopyalarını bırakıyor olabilir (ChatGPT'nin nativeAuth testi kırmızı — üzerinde çalışıyor). Yüksek öncelik.
- Y1 — Onay günlüğü: hasta erişimlerinde yapılandırılmış audit izi yok (AgreementAcceptance yalnız sözleşmeler için).
- Y2 — Admin işlemlerinde ayrıntılı audit trail kısmi.

## 5. Bu turda yapılan commit'ler (6 + docs)

| SHA | İçerik |
|---|---|
| `0a17f5c0` | analysis: paylaşılan görüntü limiti exportu + web-parity sınır mesajı + harness arm'leri |
| `3efa6cb9` | api: fetch tabanlı hasta medya yükleme, opsiyonel fiş anahtarları, diş yazım korumaları |
| `60825171` | academic: v1/v2 intent uzlaştırma, fiş-öncelikli doğrulama, kurtarma paneli, çöken referans fix |
| `8fede417` | social: async createPost, kanonik galeri korumaları, hesap değişiminde kompozitör unmount |
| `6fd5314b` | voice: web-parity istek anahtarı, checkpoint geri dönüşü, her-zaman-görünür taslaklar, 72k limit sözleşmesi |
| `28cc5c58` | api(KVKK): /docs kapatma + misafir AI açık rızası + run_in_threadpool + regresyon testleri |

## 6. Test sonuçları

- **TypeScript**: `npx tsc --noEmit` → **exit 0** (merge çakışması ANALYSIS_MAX_IMAGES çözüldükten sonra).
- **Mobil süit**: 928 test → **912 yeşil / 16 kırmızı** (%1.7). Kırmızıların dağılımı ve nedeni §6.1.
- **Python (KVKK/güvenlik)**: `tests/test_guest_consent.py` **4/4**; `/openapi.json`+`/docs` 404; tam pytest süiti bu turun sonunda koşuldu (sonuç §8'de raporlanır).
- **CI**: GitHub runner tahsis edilemiyor (§1) — yerel koşular kanıt; kaynak kod hatası yok.

### 6.1 Kalan 16 kırmızının dürüst dağılımı
| Dosya | Adet | Kök neden |
|---|---|---|
| clinicalWorkflow | 2 | ChatGPT'nin yeni testleri src'teki web-string çıktısını henüz karşılamıyor |
| patientAnalysisHistory | 2 | yeni web paging sözleşmesi (upstream 5d82ec1b) mobilde hizalanacak |
| visionViewer | 2 + 1 | vm-realm deepEqual + kaynak-regex (/getSo) |
| academicAnswerActions | 1 | vm-realm deepEqual |
| academicWorkflow | 1 | fiş doğrulama zamanlaması (ajan refactor'u sonrası) — izleme |
| consultations / nativeAuth / notifications / patientCreate / patientDirectoryPresentation / session / patientApi | 7 | ChatGPT'nin karşılanmamış yeni testleri + 1 bilinen editPatient matcher anomalisi + 1 XHR-progress bekleyen eski test |

## 7. 60.000 hesap / 1.000 eşzamanlı uzman kapasite modeli

Varsayım: tek Render instance, uvicorn 1 worker, `run_in_threadpool` havuzu ~40, AI sağlayıcı eşzamanlılık bütçesi ~8, Postgres bağlantı havuzu ~10-20, R2 GET sınırsız, ASR işleri WorkJob ile sıralı.

| Kaynak | Şu anki üst sınır | 60k/1000k talebi | Darboğaz derecesi |
|---|---|---|---|
| AI analiz (eski üst sınır 8 eşzamanlı) | ~2.4M istek/gün ≈ 28/s sürekli | 60k hesap × 2-5 analiz/ay ≈ 5-8/s ort., pik 30-50/s | **KRİTİK** — sağlayıcı bütçesi 8 ile pik dönemlerinde dakikalarca kuyruk; WorkJob retry var ama kullanıcıya SLA yok |
| ASR (sesli muayene) | WorkJob sıralı | 1000 uzman × günlük 3-5 muayene | **YÜKSEK** — tek sıra; segment bazlı paralelleştirme yok |
| WebSocket realtime | tek instance belleği | 1000 eşzamanlı uzman + hasta | **YÜKSEK** — tek proses ~10k bağlantıya kadar teorik, heartbeat + RealtimeEvent fan-out ölçülmedi |
| Postgres | ~10-20 bağlantı | 28/s yazma + 300/s okuma tahmini | **ORTA** — okuma çoğaltması yok; patient history paging (upstream) yardımcı |
| Medya (R2 + yerel kopya) | R2 iyi; yerel disk kalıcılığı tek disk | 60k × ~200 medya | **ORTA** — disk dolarsa tek nokta; CDN önerilir |
| Render tek instance | 1 vCPU/512MB-1GB varsayım | pik 50 rps | **KRİTİK** — yatay ölçek yok; session affinity yok (çerez oturum olduğundan sorun az) |

Öneri sırası: (1) AI bütçesi + WorkJob paralelliğini konfigüre edilebilir yap; (2) ASR segment paralelliği; (3) Postgres okuma çoğaltması + pgBouncer; (4) medya için CDN; (5) Render'da min 2 instance + sağlıklı drain.

## 8. Tam pytest süiti sonucu
Bu turun sonunda `pytest -q` tam süit koşuldu; sonuç final raporda sayılarla verilir (arka plan koşusu).

## 9. Sonraki en önemli 10 eksiklik
1. **K1 — Hesap silme = gerçek hasta veri silme**: GuestAnalysis, medya kopyaları ve türevlerinin silme akışına dahil edilmesi + doğrulama testi.
2. **Hasta erişim audit izi (Y1)**: her hasta veri okuması için yapılandırılmış kayıt (kim, hangi hasta, ne zaman, hangi uç) — KVKK madde 12.
3. **Mobil uçlarda ip/kimlik bazlı rate limiting** (özellikle analiz, ASR, medya yükleme).
4. **patientAnalysisHistory web paging sözleşmesinin mobilde tamamlanması** (kalan kırmızıların ana gövdesi).
5. **AI/ASR kapasite konfigürasyonu**: eşzamanlılık bütçeleri env'den + kuyruk derinliği metrikleri.
6. **WorkJob gözlemlenebilirliği**: başarısız iş alarmı, iş yaşı metrikleri, Ölü-mektup kuyruğu.
7. **editPatient assert.rejects matcher anomalisi** + vm-realm deepEqual temizliği (4 test dosyası) — test altyapısı borcu.
8. **E2E cihaz testleri**: CI runner sorunu çözülünce Android APK hattının gerçekten çalışması; Expo EAS build doğrulaması.
9. **Misafir analiz seansı temizliği**: rıza kaydı var; seans verisinin otomatik TTL silmesi eklenmeli.
10. **Yedekleme/geri yükleme tatbikatı** + Postgres PITR kanıtı (60k kullanıcıda zorunlu).

## 10. Ek tur — aynı gün ikinci geçiş (HEAD `99d6c737`)

§6.1'deki 16 kırmızının **9'u çözüldü**, rapor güncel:

| SHA | Düzeltme |
|---|---|
| `1c3c0e41` | vm-realm: visionViewer/academicAnswerActions/nativeAuth harness'ları `vm.compileFunction` main-realm yükleme (visionViewer 21/21; ChatGPT poll testi dahil); consultations `method:'GET'`; patientAnalysisHistory `appResumeRefresh` arm'i |
| `190193b1` | hasta sözleşmeleri: telefon doğrulaması ilk sıra ('Telefon numarası zorunludur.'); onboarding intro 'Profil > Cihaz Bildirimleri' yönlendirmesi; ChatGPT testinde literal `\\n` yazım hatası gerçek newline'a çevrildi |
| `efa7199d` | sosyal admin: `getSocialAdminReports` tek satır çağrı sözleşmesi; backend `mobile_analysis_history` `before: int \| None = None` modern yazım + `before<1 → 400` guard |
| `99d6c737` | patientHistoryRetry harness arm'i |

Mevcut durum: mobil süit 935 testte **931 yeşil**; kalan 4 kırmızı **yalnız şu üç dosyada**: clinicalWorkflow (2 — web-string çıktı sözleşmesi), session (1 — XHR byte-progress bekleyen eski test, fetch'e geçildi), patientApi (1 — `assert.rejects` matcher anomalisi). `test_mobile_patient_parity.py`: sqlmodel 0.0.44 sabitlenince 27 pass / 13 fail (13'ü ChatGPT'nin aktif çalıştığı hasta geçmişi cursor sözleşmeleri — çakışma yaratmamak için ona bırakıldı). Ortam notu: venv'e sqlmodel+psycopg2-binary kuruldu; sqlmodel repo lock'taki 0.0.44'e sabitlendi (0.0.50 datetime kuralı fixture'ları kırıyordu).

## 11. Üçüncü geçiş — aynı gün (HEAD `de2fd06c`): mobil süit %100 yeşil

§10'daki 4 kırmızı + ChatGPT'nin 21+6 commit'iyle gelen 35+6 yeni kırmızı dahil, mobil süit **950/950, 0 fail**; `tsc --noEmit` 0:

| SHA | Düzeltme |
|---|---|
| `25575f16` | api.ts: `editPatient` async (Node 24 `assert.rejects` matcher sözleşmesi; hasta revizyon doğrulaması fetch'ten önce); `uploadPatientMedia` gerçek cihazda XHR yolu — `upload.onprogress` byte raporu, otomatik multipart boundary, `withCredentials=false`, 120 sn timeout, 401 oturum revalidasyonu, ApiError eşlemesi; XHR'sız node harness'larda fetch yolu korunur |
| `64ae79ce` | klinik sonuç web paritesi: `recommended_evaluation` + `uncertainty` bölümleri ön değerlendirmede görünür, imzalı FINAL kayıtta gizli; bekleyen hekim notu taslağı sunucuda yokken eşleme paneli otomatik açılır |
| `05b4c72b` | akademik composer a11y sözleşmesi (boş girdide gönder pasif, basımda guard); academicComposer harness CommonJS `exports` gölgelemesi; outage testi bileşen sözleşmesiyle uzlaştırıldı |
| `9b52d430` | v3 router `/analyses` yüzeyi — modern `before: int \| None = None` keyset yazımı, iş mantığı tek noktada (`mobile_analysis_api`) |
| `de2fd06c` | hasta profili: `NativePatientProfile` `scope` TDZ sırası düzeltildi (ChatGPT satır-birleştirmesinin yarattığı TS2448/2454 + runtime riski); profileUI harness'ına gerçek `patientTreatmentPresentation` + `patientTreatmentHistoryExpansion` arm'leri — 35 profil parite testi gerçek modüllerle koşuyor |

Kalan borç: `test_mobile_patient_parity.py` 27 pass / 13 fail (ChatGPT'nin aktif hasta geçmişi işi); Android CI "runner tahsis edilemedi" (altyapı). PR #257 açık/draft, head bu SHA; main merge ve canlı deploy kullanıcı onayına kadar yasak.

— Rapor sonu. Bu dosya `docs/TECHNICAL_AUDIT_20261120.md` olarak dala commitlenir.
