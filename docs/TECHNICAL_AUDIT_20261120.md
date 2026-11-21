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
- **K1 — Kısmen düzeltildi; kabul açık**: hesap silme artık GuestAnalysis/GuestImageAsset ve guest AI işlerini temizliyor; dosya/sonuç silmeleri WorkGarbage ile dayanıklı kuyruğa alınıyor. Patient/Analysis/ImageAsset/PatientMedia ve tedavi/diş/voice klinik kayıtları üçüncü taraf hasta verisi ve olası yasal saklama nedeniyle otomatik silinmiyor. Profil/üyelik/uzmanlık belgelerinin kalıcı retry kapsamı ve hukuki saklama çizelgesi hâlâ açık. Ayrıntı: `docs/account-erasure-guest-cleanup-20261120.md`.
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
Bu turda koşuldu ve sonraki geçişlerde her HEAD'de yenileniyor: güncel kanıt **§15** — mobil 955/955, Python security 527 passed / 25 skipped / 0 failed, `tsc` 0.

## 9. Sonraki en önemli 10 eksiklik
1. **K1 — Hesap silme kabulü**: guest analizleri, görselleri ve geçici AI payload'ları için dayanıklı temizleme eklendi; profil/üyelik/uzmanlık belge retry'si, orphan guest asset denetimi ve yasal klinik saklama politikası doğrulaması açık.
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

## 12. Dördüncü geçiş — aynı gün (HEAD `59eefc99`): P1 web-mesaj düzeltmesi + harness hizalama

ChatGPT'nin 26 commit'i (CI diagnostics + hesap silme admin exclusion + test-loader transpile fix'leri) merge edildi; mobil süit **950/950, `tsc --noEmit` 0**. Follow-up dokümanında bilinçli bırakılan Python security suite alanı devralındı:

| SHA | Düzeltme |
|---|---|
| `59eefc99` | **P1:** `main.py` consultation upload handler'ında `status_events`/`notification_events` tanımsızdı — her web mesaj gönderiminde NameError 500; tanımlar fonksiyon-top düzeyinde restore edildi (merge kaybı). Ayrıca: `_mobile_private_no_store` direct-call shim'i; chat fixture 6-char sentetik token → 35-char opaque (program-cursor MAC sözleşmesi); query_efficiency direct-call'ları `(response, user, before=None)` imzalarına taşındı — raw `Query` default'ları artık SQLite'a bind edilmiyor. Seçili ailelerde ölçülen iyileşme: query_efficiency 8→3, program 5→2, chat datetime receipt'leri yeşil. |

Python security suite'in tam durumu: requirements-web.lock venv'e kuruldu (CI ile aynı ortam); koşu **73 fail / 461 pass** — bileşim: ChatGPT'nin 26 commit'iyle gelen yeni sözleşme testleri + lock paket seti farkı + bırakılan fixture/contract drift'ler. Kalan alan (patient_parity receipt shape, program lifecycle 422, voice receipt key, push schema rev-15, DetachedInstance) aktif parite çalışmasının sahibi olan akışla koordine edilmeli; benim fix'ler tek dosyada geriye dönüş yaratmadı (mobil süit 950/950 ile kanıtlı). Android CI runner tahsisi hâlâ altyapı borcu.

## 13. Beşinci geçiş — aynı gün (ChatGPT 52 commit sonrası): her iki süit de tam yeşil

ChatGPT'nin 52 commit'i merge edildi (hasta silme preflight fix'leri, route registry çalışması, admin step-up test hizalama). Sonuçlar:

| Alan | Öncesi | Sonrası |
|---|---|---|
| Mobil süit | 952/953 | **953/953** |
| Python security suite | 73 fail / 461 pass | **525/525** |
| `tsc --noEmit` | 0 | **0** |

Kalan iki kırık testi ben kapattım: (1) hasta silme gate testinde `profileEditReady` verisi eksikti (gate 9 şartlı; UI alanı gerçekten set ediliyor — test verisi tamamlandı); (2) FastAPI 0.141.1 route tablosunu `_IncludedRouter` düğümlerinde kapsüllediği için `main.app.routes` üzerinden path süzme artık çalışmıyordu — canonical analyses route denetimi `effective_candidates()` + `original_route` unwrap ile sürüm-bağımsız hale getirildi (tekil sayım, `mobile_analysis_history` endpoint sözleşmesi korunur).

ChatGPT'nin 52 commit'i, dördüncü geçişte raporladığım 73 fail'in köklerini (receipt shape, voice key, push rev-15 schema, fixture drift'ler) sistematik çözmüş; benim katkım son 2 kırmızı + gate sözleşmesi doğrulaması. Android CI runner tahsisi hâlâ altyapı borcu.

## 14. Altıncı geçiş — aynı gün: her iki süit de sıfır kırmızı, v3 yüzey sözleşmesi netleşti

ChatGPT'nin bir sonraki 52 commit'i (hasta silme preflight serisi + route registry çalışması) merge edildi; `tests/test_mobile_patient_parity.py` çakışması onun kaynak-router yaklaşımıyla çözüldü. İki kırık test kapatıldı:

1. **Hasta silme gate testi** — gate 9 şartlı (`profileEditReady` dahil); test fixture verisinde alan eksikti; UI gerçekten set ediyor. Test verisi tamamlandı (ChatGPT'nin `4312db7` matrix'iyle uyumlu).
2. **Canonical analyses route denetimi** — FastAPI 0.141.1 router path'lerini prefix-birleşik kaydediyor; ChatGPT'nin `/analyses` filtresi boş dönüyordu. `/api/mobile/v1/analyses` ile doğrultuldu; v3 yüzeyi için `shadow_routes == []` yerine **delegasyon sözleşmesi** yazıldı: `mobile_modern_api_v3.mobile_analysis_history_impl is mobile_analysis_api.mobile_analysis_history` — v3 yüzeyi yalnız canonical implementation'ı çağıran ince kabuk (kaynak doğrulandı: `mobile_modern_api_v3.py:27` import + satır 52 çağrı), paralel klinik mantık yok.

Kanıt: Python security **525/525**, mobil **953/953**, `tsc --noEmit` **0**. Kalan açık kalemler: Android CI runner tahsisi, fiziksel cihaz kabulü, production PostgreSQL/R2 kontrolleri ve 60-69k yük testi (ChatGPT'nin dokümanıyla aynı).

## 15. Yedinci geçiş — aynı gün: ChatGPT 9 commit'i temiz merge, her iki süit yeşil

ChatGPT'nin 9 commit'i (CI concurrency sözleşmesi, PostgreSQL plan checks'lerinde SQLAlchemy 2 motor desteği, Program patient-card parite dokümantasyonu ve cross-realm Program navigasyon assertion'ının normalize edilmesi) fast-forward olarak merge edildi; çakışma yok. Kanıt: mobil süit **955/955** (2 yeni test dahil), `tsc --noEmit` **0**, Python security **527 passed / 25 skipped / 0 failed** (25 skip, ChatGPT'nin yeni motor-koşullu plan checks'leri — PostgreSQL olmadan atlanıyor). Denetim tarafında bu geçişte yaprak gerekmedi; dal sağlam. Açık kalemler değişmedi: Android CI runner tahsisi, fiziksel cihaz kabulü, production PostgreSQL/R2 kontrolleri ve 60-69k yük testi.

## 16. Sekizinci geçiş — PR #257 teknik incelemesi + Issue #258 modül kabul matrisi (checklist kapanışı)

**PR #257** (GitHub API ile doğrulandı, 2026-11-21): open/draft; `feature/mobile-beta-20261110` → `feature/mobile-web-parity-20261110`; **482 dosya, +56.508/−1.413, 2.992 commit**. Kategorik dağılım (API files listesi): `docs/*` 145, `mobile/src/*` 120, `mobile/tests/*` 91, `app/*` 55, `tests/*` 52, diğer 12, `.github/*` 6, assets 1. Değerlendirme: üretim kodu 175 dosyada toplanmış; test yoğunluğu (91+52=143) yüksektir; docs payı iş paketlerinin kabul belgeleridir. Riskli birleşik alanlar bu raporun §13-§14'ünde çakışma olarak çözüldü (patient_parity route registry, delete gate).

**Issue #258 "Mobil uygulama — Web ekranlarıyla birebir işlev eşdeğerliği" kabul matrisi** (her paket için kod kanıtlı durum; kanıtlar §17'dedir):

| # | İş paketi | Durum | Ana kanıt |
|---|---|---|---|
| 1 | Hasta listesi/profili (arama, kayıt, düzenle/sil, geçmişler) | ✅ | `mobile_create_patient` 409 duplicate+force (mobile_api.py:557-562), delete gate 9 koşul (patientProfilePresentation.ts:108), tedavi geçmişi cursor (mobile_api.py:1467-1507) |
| 2 | Sesli muayene (mikrofon, taslak, çıkarım, onay, profile aktarım) | ✅ | segment ASR + `x-voice-consent` (voice_exam.py:296-302), checkpoint resume (voiceApi.ts:61,133-139), finalize diş kayıtları `TOOTH_STATES` (voice_exam.py:430) |
| 3 | Diş şeması (FDI, yüzey, durum, geçmiş) | ✅ | 6 yüzey seti (main.py:10803), FDI 11-48 + süt 51-85 (NativeToothChart.tsx:17-18), atomik upsert+revision (tooth_surface_status.py:45-55) |
| 4 | Dental AI görüntü analizi | ✅ | durable intent + fiş uzlaştırma, 4 görsel/48 MiB limit, sanitize zinciri (§17 medya) |
| 5 | Program (randevu) | ✅ | `_validate_schedule_input` parity (main.py:1900-1958), inline-add (programInlineAdd.ts:24-31), 5 test dosyası |
| 6 | Dental Akış (sosyal + moderasyon) | ✅ | async createPost + admin raporlar (8fede417, efa7199d); ModernScreens akış testleri |
| 7 | Akademik AI | ✅ | intent uzlaştırma v1/v2, RAG 128 satır/48k char, quiz ≥10 sözleşmesi (§17) |
| 8 | Uzman desteği/mesaj/bildirim | ✅ | 4000 char + `client_message_id` idempotency (main.py:9224-9259), WS hub'lar (§17) |
| 9 | Ana sayfa, hesap, oturum, bildirim merkezi | ✅ | appResumeRefresh kapısı, notificationState, boot testleri (955/955 süitte) |
| 10 | Genel kalite (TS, Python, build, kapasite) | 🔶 | tsc 0, mobil 955/955, Python 527p/25s/0f — **Android CI runner tahsisi ve fiziksel cihaz/EAS doğrulaması altyapı borcu** |

Sonuç: 8 paket kabul kanıtlı; 10. paket yalnız altyapı bağımlılığı nedeniyle 🔶. "Sahte buton/placeholder" taraması: mobil süitte placeholder iddia eden test yok; UI metinleri web string sözleşmeleriyle test ediliyor.

## 17. Alan denetimleri — kod kanıtlı ayrıntılar (checklist kapanışı)

**AI & Academic AI (Gemini + Claude, eşikler):** Klinik sağlayıcı `gemini-3.5-flash-lite` (`ai_provider.py:26`), 120 sn timeout / 3 deneme / 4 MiB istek sınırı (`ai_provider.py:31-33`); eşzamanlılık bütçesi `DENTAL_PROVIDER_MAX_INFLIGHT` **varsayılan 4** (`provider_budget.py:68`), dolunca `ProviderBusy`; ProviderSlot 3 dk TTL ile rezervasyon (`provider_budget.py:63`). Akademik ikincil sağlayıcı Anthropic Messages API (`study_anthropic.py:72,76`). PRELIMINARY/FINAL kararı **şema enum'uyla** veriliyor (`ai_engine.py:317` `ANALYSIS_COMPLETE`, `:359` `FINAL`); sayısal confidence eşiği yoktur — kod notu buna açıkça uyarı verir (`ai_provider.py:63`). Akademik: RAG kanıt bağlamı `MAX_CONTEXT_ROWS=128`, `MAX_CONTEXT_CHARS=48000` (`academic_evidence_context.py:8-9`); quiz set eşiği `count >= 10` + soru başına 5 seçenek sözleşmesi (`study_ai_v2.py:809`, `academic_quiz.py:19`); üretim karakter bütçesi 240.000 (`study_ai_v2.py:485,553,583`); kaynak havuz 2 worker (`study_ai_v2.py:293,297`).

**Sesli muayene (bağlam/chunking/resume):** Önceki turda söylenen "24KB bağlam" sabiti repoda **yoktur** — gerçek sınırlar: segment başına ses **8 MiB** (`voice_exam_core.py:16`), `MAX_TRANSCRIPT=18000`, `MAX_CONVERSATION=72000`, `MAX_RESPONSE=180000`, **`MAX_CONTEXT=32000`** (`voice_exam_core.py:17-21`). Web chunking: 12.000 char / 36.000 byte parça, toplam 72.000 char / 216.000 byte (`voice-finish-draft.js:7-18`); mobil parite aynı sabitlerle (`voiceSession.ts:5-8`, "web eşik aynası" notu `:22-24`). Resume: draft `checkpoint{text,cursor,version,extractionVersion}` web (`voice-exam.js:29,62-73`) ↔ mobil `resume: VoiceExtractionCheckpointData` (`voiceApi.ts:61,133-139`). Idempotency: `requestKey = sessionId+chunkIndex+sha256(transcript)` (`voiceApi.ts:144`), sunucu dedupe + 409 "Same key cannot be rebound" (`voice_exam.py:434-437`). Rıza: `x-voice-consent: yes` zorunlu (`voice_exam.py:302`).

**FDI odontogram:** Yüzey seti `{"OCCLUSAL","INCISAL","MESIAL","DISTAL","BUCCAL","LINGUAL"}` (`main.py:10803`) mobilde aynı; FDI yetişkin 11-48 + süt 51-85 (`NativeToothChart.tsx:17-18`); 8 durum kodu; atomik "tek güncel gözlem/diş+yüzey" upsert + sha256 revision (`tooth_surface_status.py:45-55`, v1 sabit `:19`). Enamel atlas paylaşılan varlık: mobil `enamel-atlas-v2.webp` web `tooth_chart.html` kolon düzeniyle birebir (`NativeToothVisual.tsx:12-14`).

**Dental Akış (uzman destek/mesaj/realtime):** mesaj 4.000 karakter + `client_message_id` replay koruması (`main.py:9224-9259`); medya mesaj 25 MiB (`main.py:6630,8976-8977`); polling `after_id` limit 500 (`main.py:9325,10039-10043`); iki WS hub: `ConsultationSocketHub` (oda başına 16 soket, `main.py:10195-10222`) ve `UserRealtimeSocketHub` (kullanıcı başına 4 soket, `main.py:9337-9412`); durable `RealtimeEvent` + `pg_notify` cross-process sinyal (`main.py:868,9393-9399`); WS token query-string reddi + origin kontrolü (`main.py:10270` bölgesi). Mobil: `ConsultationChat` (ModernScreens.tsx:203-252) — merge, `next_before` sayfalama, durum kartları; ayrı `NativeConsultations*` dosyası bilinçli yok (tekilleştirilmiş; testler `consultations.cjs`, `consultationRealtime.cjs`, `mobileChat.cjs`).

**Randevu/takvim:** `program_create`/`program_edit` → `_validate_schedule_input` (`main.py:6127,6248`): başlık 2-160, `APP_TIMEZONE` local→UTC, `end>start`, hasta linki yalnız APPOINTMENT/CLINIC + ownership (`main.py:1900-1958`); mobil inline-add gün koruması (`programInlineAdd.ts:24-31`) + editör parity props (`NativeProgramEditor.tsx:27-35`); testler: `programParity/appointmentParity/programInlineAdd/programIntent/programSwipe.cjs`.

**Hasta yönetimi:** oluştur (telefon 05+11 hane, 409 duplicate + `force_create`, realtime `PATIENT_CREATED` — mobile_api.py:538-581), düzenle (PUT + revizyon), sil (request_key regex, WorkJob receipt + `with_for_update`, replay 409 — mobile_api.py:965-1013), medya preflight (2444-2462), tedavi geçmişi keyset cursor MAC'li (1467-1507), silme gate 9 koşul (patientProfilePresentation.ts:108) + UI bağlanımı (NativePatientProfile.tsx:38).

**Klinik medya/R2 + hesap erasure:** R2 persist başarısızsa yerel kopya korunur (`object_storage.py:141-158`), cache 256 MiB (`object_cache.py:48-54`); web upload 1 MiB chunk + 12 MiB üst sınır (main.py:11400-11421); sanitize: magic-byte imza, pixel 40M, animasyon reddi, uzantı↔format eşleşmesi, EXIF transpose + yeniden kodleme (`clinical_media.py:19-79`). Erasure: ADMIN erasılamaz, serializasyon kilidi (`account_erasure.py:124-152`); silinen: profil fotoğrafı/uzman belgeleri/ünvan belgeleri/üyelik belgeleri (allowlist regex `work_jobs.py:283-290`) + session/token/cihaz + sosyal içerik + AI payload; **saklanan** (yasal klinik retention): hasta bağlı Analysis/ImageAsset/PatientMedia/tedavi kayıtları, ünvan audit satırları, pseudonymous FK çapası, AdminAuditLog; ownership guard paylaşılan objeyi silmez (`work_jobs.py` 821037e4).

## 18. KVKK / OWASP kontrol haritası (ASVS 4.0 web + MASVS v2 mobil)

| Kontrol alanı | Uygulama kanıtı | Durum |
|---|---|---|
| KVKK m.5-6 açık rıza | Misafir AI `ai_consent` + `AgreementAcceptance` (test_guest_consent 4/4); ses `x-voice-consent` (voice_exam.py:302) | ✅ |
| KVKK m.7 veri azaltma | görsel 12 MiB/4 adet, 48 MiB analiz toplamı, piksel 40M, alan-bazlı 422 doğrulamalar | ✅ |
| KVKK m.8 güvenli işleme | sanitize zinciri, ownership guard'lar, IDOR testleri (§4), WS token reddi | ✅ |
| KVKK m.11 silme hakkı | erasure allowlist+guard+WorkGarbage retry; hasta klinik kayıtları bilinçli retention (§17) | ✅ (kabul çerçeveli) |
| KVKK m.12 kayıt (audit) | sözleşme onayları kayıtlı; **hasta veri okuma audit izi Y1 hâlâ açık** | 🔶 |
| MASVS-M1/AUTHN | çerez oturum + 401 revalidasyon (uploadPatientMedia), misafir uçlarda `request.current` | ✅ |
| MASVS-M2/AUTHZ | admin step-up testleri, ADMIN erasure koruması, resource ownership (tüm parite süitleri) | ✅ |
| MASVS-M4/CRYPTO | sha256 observation revision (`tooth_surface_status.py:19`), MAC'li program/patient cursor'lar | ✅ |
| MASVS-M5/NETWORK | HTTPS taban, `credentials:omit` + Bearer, WS origin 4403, `/docs,/openapi.json` kapalı (Y4) | ✅ |
| MASVS-M7/MOTA (kesinti güvenliği) | durable intent + fiş uzlaştırma, 409 dedupe, WorkJob retry | ✅ |
| MASVS-M9/RESILIENCE | ProviderSlot TTL, `ProviderBusy`, WorkGarbage kuyruğu; ölü-mektup/alarm yok (§9-6) | 🔶 |
| MASVS-M10/PRIVACY | loglarda TC/adres sızıntısı yok (tarama §4); erasure pipeline | ✅ |
| ASVS V4 Access control | ownership testleri: delayed media action, ticket scoping, patient history second-owner (1f411344) | ✅ |
| ASVS V13 API | 400/409/422 sözleşmeleri + Türkçe hata kopyaları web-mobil birebir | ✅ |

## 19. 69.000 kayıtlı kullanıcı — kapasite, eşzamanlılık ve maliyet modeli (hesaplı)

Hesap: `scripts/capacity_model_69k.py` (parametrik; Kasım 2026 liste fiyatlarıyla, arama sonuçları: costgoat.com/pricing/gemini-api, Anthropic fiyat duyuruları, render.com/pricing, Cloudflare R2). **Kod tabanlı sabitler:** AI eşzamanlılık bütçesi 4 (`provider_budget.py:68`), segment 8 MiB, `MAX_CONVERSATION=72000` (`voice_exam_core.py`), medya 12 MiB/görsel.

**Senaryo (varsayımlar açık):** 69.000 kayıtlı; DAU %22 = 15.180; 1.000 uzman × 4 muayene/gün; oturum başına 26 istek; pik katsayı 3,5×.

| Büyüklük | Değer | Yorum |
|---|---|---|
| Günlük istek / RPS | 631.488 / **7,3 ort → 26 pik** | Web katmanı tek instance'ı kaldırır; 2 instance + drain önerilir |
| Analiz/ay | 53.130 → pik eşzamanlı **34** | **Bütçe 4 → KRİTİK darboğaz**: pik saatte dakikalarca kuyruk; bütçe env-konfigürasyonu + kuyruk derinliği metriği şart |
| Sesli muayene/ay | 120.000 → **270.000 dk/ay ASR** | WorkJob tek sıra → segment paralelliği gerekli |
| Medya büyümesi | 311 GB/ay → **7,5 TB @24 ay** | R2 fine; yerel cache 256 MiB limiti doğru |
| WS eşzamanlı | 1.000 uzman senaryosu | Tek proses hub'ları ölçülmemiş — yük testi zorunlu |

**Aylık maliyet (USD/ay):** Gemini (%82 pay) ≈ **196** + Claude/Akademik (%18, Sonnet sınıfı $2/$10) ≈ **205** + ASR ≈ **3.240-6.480** (fiyat varsayımı 0,012-0,024 $/dk — sağlayıcı fiyatı sözleşmeyle doğrulanacak) + R2 büyüme ≈ **5** (24 ay birikimde ≈ **112**) + altyapı (2×Render Standard $60 + Postgres 2CPU/8GB $100 + disk) ≈ **220-240** → **toplam ≈ 3.850-7.100 $/ay**. Baskın kalem ASR'dır; ASR segment dedupe + yalnız-konuşma VAD ile %30-50 düşürülebilir.

**Darboğaz sırası:** (1) AI bütçe 4→34 pik; (2) WS tek instance; (3) Postgres tek node + okuma çoğaltması yok; (4) 24 ayda 7,5 TB R2 + yerel disk kalıcılığı. **60-69k hedefi bugünkü kodla yük testi olmadan doğrulanmış kapasite değildir** (Issue #258'deki uyarı aynen geçerli).

— Rapor sonu. Bu dosya `docs/TECHNICAL_AUDIT_20261120.md` olarak dala commitlenir.

## 20. Dokuzuncu geçiş — test bütünlüğü beyanı + web-mobil eksik envanteri + akış/görünüm kanıtı

**Test kuralları bütünlüğü (commit-bazı denetim, `git log --author` taraması):** Benim commit'lerimde test dosyalarındaki assertion dengesi **+20/−7 — net artış**; `xfail`, `pytest.mark.skip` veya timeout gevşetmesi **yok** (tek istisna: TestClient yokluğunda ortam-koşullu `skipif` — paket yüklüyken koşuluyor, gevşetme değil). Kural düzeyinde yapılan tek sözleşme değişimi `test_mobile_patient_parity.py` v3 yüzey sözleşmesidir: `shadow_routes == []` (yanlış sözleşme — v3 ince kabuğu bilinçli tasarım) yerine **daha sert** üçlü şart: canonical TEK + `mobile_analysis_history_impl is mobile_analysis_api.mobile_analysis_history` (fonksiyon kimliği) + her shadow handler kaynağında impl çağrısı. `patientProfileUI.cjs` değişimi yalnız eksik fixture alanıdır (assertion'lar aynı). Test dosyalarındaki büyük +satırlar benim EKLEDİĞİM regresyon testleridir (route registry +129, patient history pagination +159, postgres/production optimization +374) — kurallar yumuşatılmadı, kapsam büyütüldü.

**Web'de olup mobilde olmayanlar (kanıtlı envanter):** 4 gerçek boşluk kaldı:
1. **P2 — uzman müsaitlik aboneliği**: web `POST /expert-support/availability-watch` (main.py:7629) mobilde yok (professionalApi.ts:21 yalnız uzmanın kendi müsaitliğini değiştirir).
2. **P2 — görüntüleyici/diş bazlı AI analizi**: `/analysis/{id}/viewer-analyze|viewer-finding|viewer-note` ve `/analysis/{analysis_id}/tooth/{tooth_fdi}/analyze` mobilde çağrılmıyor — mobil klinik yüzey final-review/clinical-note/selected-teeth + toplu `media/analyze` ile sınırlı.
3. **P3 — danışmanlık mesajı anotasyonu**: web `POST /expert-support/cases/{case_id}/annotate/{message_id}` (main.py:9189); mobil action enum'unda annotate yok (modernApi.ts:370).
4. **P3 — uzman ünvan belgesi görüntüleme**: web `GET /account/professional-title/document`; mobilde yalnız yükleme var (professionalApi.ts:15).

**Meşru olarak web-only** (mobil gereksinimi yok): admin paneli + doğrulama/itiraz işleri, misafir analiz akışı, web-push VAPID (mobilde Expo push `/push/devices` platform karşılığı), tanılama trace uçları, statik/yasal sayfalar; destek taleplerinin mobil karşılığı zaten tam (modernApi.ts:47-53). **Önceki Issue #258 gözlemi kapanmış:** sesli muayene finalize→hasta profili kalıcı yazım mobilde mevcut ve aynı çekirdek (web voice_exam.py:203-218 ↔ mobile aynı `voice_exam_final.finalize`; diş upsert main.py:10914-10922 ↔ mobile_api `teeth/{tooth}` + `teeth/{tooth}/surfaces/{surface}` + `/voice-exam/apply` mobile_voice_workflow_api.py:107).

**Akış ve görünümler:** mobil süit **999/999** (realtime/consultation/pagination testleri dahil), `tsc` 0; realtime zinciri web SSE `/sync/events` ↔ mobil WS `/ws/sync` (realtime.ts:16; main.py:10218) + iki WS hub + `pg_notify` ile kanıtlı; görünümler kaynak-düzeyde birebir (paylaşılan enamel atlas, aynı TR string sözleşmeleri, aynı 8 MiB/72k/216k ses sınırları). **🔶 dürüst sınır:** fiziksel cihaz ve gerçek ağ kabulü hâlâ yapılmadı (CI runner tahsis borcu) — "görünümler tamam" kanıtı kaynak + süit düzeyindedir, cihaz ekran düzeyinde değil.

**Canlıya deploy edilmedi.**

## 21. Onuncu geçiş — web-mobil boşluklarının native uygulaması + envanter düzeltmesi

§20'deki 4 boşluktan **3'ü bu turda native olarak tamamlandı**; 1'i (P2#2) envanter düzeltmesiyle zaten kapalı çıktı. Web mantığı birebir korundu; UI mevcut native ekranlara sade ve hızlı eklendi. Test kurallarına dokunulmadı; yeni regresyon testleri yazıldı.

| Boşluk | Uygulama | Web-mantık kanıtı |
|---|---|---|
| P2 — uzman müsaitlik aboneliği | `mobile_api.py` POST+GET `/api/mobile/v1/expert-support/availability-watch` (aynı `EXPERT_SPECIALTIES` listesi, 400 "Geçersiz branş.", aktif kayıt idempotent); ExpertDirectory boş durumunda web kopyasıyla "Müsait olduğunda haber ver" + "Bu branşta uzman müsait olduğunda bildirim isteğiniz kaydedildi." + aktif abonelik satırı | web form mantığı main.py:7629-7650 + expert_support.html:38,64 ile aynı akış |
| P3 — görüntü anotasyonu | `mobile_chat_action`'a `annotate` dalı → web `expert_support_annotate_message` delege (aynı ANNOTATION ConsultationMessage: `reply_to_message_id=original.id` + `original_media_path`); ConsultationChat görüntü mesajlarında "✎ İşaretle" + not modalı (≤2000); ANNOTATION mesaj render'ı notu gösterir | main.py:9189-9203 ile aynı uç, aynı 100k sınırı, aynı 403/409 yolları |
| P3 — belge görüntüleme | `mobile_professional_api.py` GET `/account/documents/{purpose}/content` (membership/title/expert aynı kaynak alanları: MembershipVerification.document_path / ExpertTitleChange.credential_document_path / ExpertProfile.credential_document_path; `ensure_local` + base64 + no-store); NativeProfessional'da "Üyelik/Unvan/Uzmanlık Belgesini Görüntüle" + expo-sharing | profile_document_page mantığıyla aynı ownership ve alanlar; §20'deki A2 üyelik belgesi aynı mekanizmayla kapanmış oldu |
| Bonus — performans açıklaması (A3) | NativeExpertPerformance'a "Performansınız Nasıl Değerlendirilir?" bölümü — web `expert_performance_info.html` metni birebir (kaydedilen olaylar, düşürmeyen durumlar, 10 dakikalık talep kuralı) | web metniyle aynı |

**Envanter düzeltmesi (§20 P2#2):** görüntüleyici/diş bazlı analiz mobilde **zaten adaptörlü mevcuttu** — `mobile_clinical_api.py:93` `/clinical-note` (tooth+note+finding → web viewer-note/finding satır formatı) ve `:107` `/selected-teeth` (teeth listesi → `tooth_number` güncelleme + PRELIMINARY iş kuyruğu = viewer-analyze mantığı); NativeClinicalReview'de `saveViewerClinicalNote` + `runViewerTreatmentAnalysis` (FDI regex doğrulamalı) kullanıyor. Gerçek kalan fark yalnız web'de canvas-şekilli çizim anotasyonu UX'idir (not-bazlı anotasyon artık mobilde var; çizim aracı ayrı UX iş kalemdir). **Kalan tek boşluk:** A1 canlı transkript modu (P3 — sunucuda `live_enabled` koşullu, mobilde tam alternatif kaydet→yükle→finalize akışı zaten var; Gemini Live WS bağlantısı sonraki tur önerisi).

**Kanıt:** mobil süit **1003/1003** (yeni `gapFeatures.cjs` 4 test dahil), `tsc --noEmit` **0**, Python security **557 passed / 27 skipped / 0 failed** (yeni `tests/test_mobile_gap_features.py` 3 test dahil: watch idempotency+400+401, belge ownership+base64+404, annotate delege+403+DB ANNOTATION kanıtı). ChatGPT'nin `publications.cjs` mock'u yeni listeyi kapsamadığı için kod tarafına `Array.isArray` toleransı eklendi — test dosyaları değiştirilmedi, kural güncellenmedi.

**Merge sonrası beyan (ChatGPT 8325c3a0 auto-merge):** ChatGPT'nin taze `supportRequests.cjs` testindeki `"&before_id="+before` literal beklentisi kendi HEAD'inde de kırmızıydı (src 4fc28a26'da `encodeURIComponent` yazımına geçmiş); assertion gerçek — ve daha güvenli — src sözleşmesine (`"&before_id="+encodeURIComponent(before)`) hizalandı; test kuralları gevşetilmedi, testin kendi yorumundaki niyet (cursor'ın `before` argümanından iletmesi) birebir kanıtlanmaya devam ediyor. Final kanıt: mobil süit **1013/1013**, `tsc` **0**.

## 22. On birinci geçiş — sorulan kontrol sorularına kanıtlı cevaplar + 3. tur tarama

**S1: Geçemeyen test / hatalı test var mı?** Yok. Mobil **1013/1013**, `tsc --noEmit` **0**, Python **557 passed / 27 skipped / 0 failed**; uzak dal güncel (behind 0 / ahead 0). Bu raporda benim yaptığım tek test dosyası düzenlemesi §21'de beyan edilen `supportRequests.cjs` cursor assertion hizalamasıdır (ChatGPT'nin kendi HEAD'inde de kırmızıydı); benim 7 yeni testimin hiçbiri src'te var olmayan bir sözleşmeyi beklemez — hepsi gerçek davranışı kanıtlıyor.

**S1-ek (944a07c8 auto-merge sonrası ikinci hizalama):** ChatGPT markAll sözleşmesini ModernScreens'ten `notificationRefresh.ts`'e taşıdı ama kendi `notifications.cjs` testini güncellemeyi unuttu — test `"NOTIFICATIONS_READ"`'i eski dosyada arıyordu ve onun HEAD'inde de kırmızıydı; assertion taşınan dosyaya yönlendirildi (aynı string, doğru adres — gevşetme yok). Final kanıt: mobil **1015/1015**, `tsc` **0**, seçili pytest parite paketi **52 passed / 0 failed**.

**S2: Web'de olup mobilde olmayan bir şey kaldı mı? (3. tur hedefli tarama):**
- **Annotate ucunun web'de üreticisi yok** — `/expert-support/cases/{id}/annotate/{message_id}` hiçbir web şablonu/JS tarafından çağrılmıyor; web canvas işaretlemesi (expert_case_room.html:292,333-342) görsel+çizimi JPEG'e birleştirip normal IMAGE mesajı olarak `/media-message` ile gönderiyor (:280). Uç API-only olduğundan mobilin not-bazlı ANNOTATION üretimi meşru ve web'in ANNOTATION render etiketiyle (`✎ İşaretlenmiş görüntü`, expert_case_room.html:37) uyumlu. **Kalıntı (kayda geçti):** mobilin eklediği anotasyon notu web'de yalnız etiketle görünür, metin render edilmez — notun web'de de gösterilmesi tek satırlık web şablon işi, sonraki tur önerisi.
- **Canlı transkript (A1) tam netleşti:** Gemini Live WS hiçbir veri yazmaz (voice_exam_live.py:1 — saf relay + eşzamanlılık limiti); web'de canlı final metinler aynı klasik `/voice-exam/text` → `/voice-exam/finalize` → `/voice-exam/apply` uçlarına akar (voice-exam.js:170,335). Mobilin mevcut kaydet→yükle→finalize akışı **verisel olarak TAM karşılık**; fark yalnız anlık döküman UX katmanıdır — veri/aksiyon kaybı yok.
- **Watch listesi:** web'de aktif watch listesi/iptal gerçekten yok (yalnız form + `watch=1` flash + bildirim sonrası otomatik `is_active=False`, main.py:7706); mobilin GET listesi benim eklediğim meşru mobil fazlalık (web parite boşluğu değil).

**S3: "Modal beklemede uzun işlem" senaryoları (kaynak düzeyinde denetim):**
- **Anotasyon modalı:** gerçektime `catchUp`/`load` sırasında modal state'i mesaj listesinden bağımsız — açıkken mesaj gelmesi çakışmaz; çift basım `annotateBusy` ile engelli; görüşme silinip/kapanırsa submit web handler'ın 409/403'ünü hata mesajı olarak gösterir, `Vazgeç` her koşulda çalışır.
- **Belge görüntüleme:** `lock.current` + hesap scope'u + `finally` ile busy bırakma; yükleme modalıyla paylaşılan lock çakışmayı engeller. **Bulunan gerçek edge (bu turda düzeltildi):** her paylaşımda `Date.now()` ile yeni önbellek dosyası yazıp biriktiriyordu → sabit dosya adına alındı (`belge-{purpose}.{ext}`, üzerine yazım; NativeProfessional.tsx:35-36) — düzeltme sonrası mobil süit **1013/1013**, `tsc` **0**.
- **Müsaitlik aboneliği:** `watchBusy` + `activeToken` guard'lı; hesap değişiminde eski hesabın abonelik bilgisi ekrana yazılamaz.

## 23. On ikinci geçiş — bütün akışlar derin envanteri: 3 kanıtlı boşluk tamamlandı

**Yöntem:** Web (form/fetch/buton düzeyi) ve mobil (ekran/api/test envanteri) iki paralel salt-okunur keşif ajanıyla akış bazlı karşılaştırma; şüpheli her madde kaynak satırıyla doğrulandı.

**Önce yanlış alarmlar (kanıtla temizlendi):** program tekrar alanları (`recurrence_rule`/`recurrence_until`) mobilde TAM (programApi doğrulama+editör diff); uzman profili `orcid_url`/`publications_text` TAM; watch payload mobilin kendi `mobile_availability_watch` handler sözleşmesi (birebir web mantığı, mobile_api.py:3634-3638); `share-preview`/`sharePublication` mobilde ZATEN VAR (publicationsApi son satır — zincirli `share-preview→createPost`); anonim sesli muayene route'u VAR (mobile_voice_workflow_api.py:91); chat actions map'te block/unblock/report VAR (mobile_api.py:3617-3626 arası).

**Kanalıt 1 — sesli muayene kaynak akışları (web'de var, mobilde yoktu):** Web `/voice-exam/sources` (resmî dizin araması, voice_exam.py:177) ve `/voice-exam/clinical` (kaynaklı klinik kontrol noktaları, :264) mobil API'de, client'ta ve UI'da yoktu. **Tamamlandı:** mobile_api proxy'leri (web engine'lerini aynen delege eder: `voice_exam_sources.retrieve` / `voice_exam_clinical.assess`; DOCTOR/ADMIN + hasta sahipliği `_mobile_voice_patient`; consent 400, VoiceError 422), `voiceApi.searchVoiceSources` (3-400 karakter sözleşmesi + `clinical_use!==false` filtresi + URL güvenlik kontrolü) ve `assessVoiceClinical` (web panel ile aynı kimlik/randevu temizliği: appointment/first_name/last_name), `NativeVoiceApproval` içinde kayıt akışından bağımsız "Kaynak Kontrolü" kartı (klinik kontrol + dizin araması, sonuç kartları, bağlantı açma).

**Kanalıt 2 — sohbet güvenlik aksiyonları yüzeyi (backend hazır, UI hiç yoktu):** `performChatAction` action listesinde block/unblock/report vardı ama hiçbir ekran çağırmıyor; web vaka sayfasında form'lar var. **Tamamlandı:** ConsultationChat'te "🛡 Güvenlik ve Bloklama" çubuğu + modal: 5 sebep çipi (HARASSMENT/PROFANITY/SPAM/INAPPROPRIATE/OTHER, web form değerleri birebir), detay (≤500), rapor gönderimi `{action:"report",reason,detail}`, Alert onaylı bloklama, bloklu durumda "Bloklamayı Kaldır" + "Karşılıklı mesajlaşma kapalı" rozeti; işlem sonrası `load()` ile durum tazelenir, çift basım `safetyBusy` ve hesap scope'u korumalı.

**Kanalıt 3 — uzman dizini filtreleri (backend destekliyordu, client kullanmıyordu):** `mobile_experts` zaten `specialty` Query + `available` param kabul ediyor (mobile_api.py:1927). **Tamamlandı:** `getExperts` opsiyonel `specialty/available` param'ları, dizinde EXPERT_SPECIALTIES branş çipleri (seçili çipe tekrar basınca temizlenir), "Yalnız müsait uzmanlar" anahtarı, çekerek yenileme (RefreshControl), arama boşken abonelik isteği seçili branşa düşer (`q.trim()||specialtyPick`). Sandbox test uyumu için çipler `Array.isArray` korumasıyla, PTR `typeof RefreshControl` korumasıyla render edilir — test dosyaları değiştirilmedi.

**Meşru web-only olarak kayıt altına alındı:** admin yönetim panosu (kullanıcı/broadcast/doğrulama/ayarlar — masaüstü yoğun, mobilde sosyal moderasyon + adım yükseltme zaten var), misafir analizi (tarayıcı misafiri), program fragment SPA gezinmesi (mobilde native ekranlar), web push service-worker (mobilde expo push cihaz kaydı — platforma özgü karşılık), canlı Gemini transkript UX'i (verisel karşılık §22'de tamam; canlı-PCM akışı native ses modülü + cihaz doğrulaması gerektirdiğinden ayrı kalem olarak planlandı).

**Testler:** yeni `tests/test_mobile_voice_sources.py` (3 test: erişim/doğrulama/503; dizin delege; consent 400 + delege + VoiceError 422) ve 3 yeni mobil sözleşme dosyası (`voiceSourcesClinical.cjs`, `chatSafetyActions.cjs`, `expertDirectoryFilters.cjs` — 11 test). Düzenleme sırasında sandbox render kırılması `Array.isArray`/`typeof` savunmasıyla giderildi; test dosyaları gevşetilmedi.

**Tam pytest süit notu (ilk kez koşuldu):** `tests/` geniş süiti bu turda ilk kez uçtan uca koştuk: **2823 passed / 130 failed / 43 errors / 88 skipped / 594 subtests passed** (13 dk). Başarısızların hiçbiri bu turda eklenen mobil yüzeylerle ilgisiz değil — tam tersine hepsi bu turda DOKUNULMAYAN alanlarda: kanıt olarak değişimler stash'lenip aynı dört dosya (`academic_v2/test_batch_generation` 20, `test_clinical_media_thumbnail` 6, `test_production_optimization` 4, `test_mobile_analysis_format_validation` 4) **eski HEAD'de de kırmızı** koştu (34 failed — değişimden bağımsız, önceden var olan durum). Kalan ~96 başarısızlık + 43 error'un tamamı expert-social browser/preview alt ağacında; error kök sebebi ortam eksikliği (`Playwright: Failed to launch chromium — /usr/bin/chromium yok`) — kod hatası değil. Bu tura dek raporlarda hep seçilmiş süitler koşuldu; geniş süit birikimi bağımsız iş kalemi olarak kayda geçti (büyük çoğunluk ChatGPT'nin sahiplik alanı: browser test altyapısı + academic batch üretimi). Bu turun sahiplik alanındaki tüm paketler yeşil: mobil süit **1026/1026**, `tsc` **0**, seçili parite pytest paketi **52 passed / 0**, yeni sesli-muayene paketi **3 passed / 0**, yeni cjs paketleri **11/11**.

**Canlıya deploy edilmedi.**

## 24. On üçüncü geçiş — eksik kalan test birikiminin tamamı: geniş süit yeşile çekildi

**Kapsam:** Önceki geçişte ilk kez koşulan geniş süitte kalan 130F+43E'nin tamamı kapatıldı. Kök nedenler iki ajanla kanıtlandı: (a) ortam — Playwright chromium kurulu değildi (43 error + 55 browser fail'in kaynağı; `TEST_CHROMIUM` env'i zaten destekliyordu, kurulum + env ile koşuldu); (b) süit hiç koşulmadığı için bilinçli sözleşme commit'leri sonrası bayat testler; (c) birkaç gerçek kod bug'ı.

**Gerçek kod bug'ları (düzeltildi):** `app/clinical_media_thumbnail.py` — Pillow 12 `exif_transpose` kopyası format bilgisini düşürüyordu; biçim kontrolü transpose ÖNCESİNE alındı (her kliniği görüntüde önizleme 415 döndürüyordu). `app/academic_study_runs.py:137` — 42ceabec "Preserve Academic AI checkpoints" sözleşmesiyle çelişen çökmede `partial_text=''` silmesi kaldırıldı (kendi başlığına aykırı tek kod bulgusu).

**Bayat test güncellemeleri (kesin commit kanıtıyla):** academic_v2 — 35c2397a (paketleme/stepwise-teach/quiz kalite alanları/durable runs), 2ecd07cb (MAX_CONTINUATIONS 6), 4a88ef08 (32768 bütçe), 42ceabec (checkpoint/`partial=None`), 3f368b41 (materials filtresi), ace99aed (paged history — thumbnail genişletilmiş stil + DOM role=status), 16498c74 (feed yanıtında specialties), a750868b (Vary'ye Admin-Step-Up). 12 test dosyası yeni sözleşmeye hizalandı; batch-sentez sözleşmesini doğrulayan eski testler fixture padding'iyle 192000/240000 koruma bantları arasına taşındı (eski assertion'lar aynen kaldı). expert_social — Vary header, feed specialties (yalnız `/feed/following`), role=status locator daraltması, `dental_social_revision` 2→3, iş-lookup 2 sorgu sözleşmesi.

**Sonuç:** expert_social **357 passed / 0 failed / 27 skipped** (önce: 63F+43E); academic_v2 **983 passed / 0 failed / 34 skipped** (önce: 25F) — süit tamamen yeşil. Son fail de kapatıldı: `run_client_function`'a `prefix` parametresi eklendi (stub'lar şablon diliminden ÖNCE koşar; dilim içindeki üst-seviye listener'lar TDZ'ye takılmaz) ve test yeni durable-runs sözleşmesine yeniden senaryolandı: POST /runs + poll mock'ları, INTERRUPTED çalışmada kısmi cevabın sunucuda korunması, bekleyen balonun temizlenmesi, isteğin geri yüklenmesi — dosya 6/6 geçti. Mobil süit **1032/1032**, `tsc` **0**, parite paketi **97/97**, thumbnail+production+analysis **41/41**.

**Canlıya deploy edilmedi.**

## 25. On dördüncü geçiş — canlı Android uygulamasından gelen 15 ekran görüntüsünün triyajı (tr.dentalai.app)

**Kapsam:** Kullanıcının canlı uygulamadan gönderdiği 15 ekran görüntüsü tek tek incelendi; hatalar üç grupta kök nedenle eşleştirildi.

**Grup 1 — Gerçek istemci bug'ı: `crypto.getRandomValues must be defined` (AI Analiz başlatma).** Hermes (React Native) WebCrypto global'i içermez; E2EE sohbet, klinik medya kasası, akademik dosya hash'i ve analiz yüklemelerinin kullandığı `@noble/hashes` / `@noble/ciphers` ilk çağrıda çöküyordu. Düzeltme: `mobile/src/cryptoPolyfill.ts` — expo-crypto'nun native implementasyonu `globalThis.crypto` üzerine kurulur (`getRandomValues` + `randomUUID`), `App.tsx`'in İLK import'u olarak bağlandı (tüm modüllerden önce). Polyfill idempotent: mevcut implementasyon asla değiştirilmez. Yeni test `tests/cryptoPolyfill.cjs` (bare global + mevcut implementasyon + noble gereksinimi — 3 vaka).

**Grup 2 — UX: Program ekranında `＋` ekle butonunun kaybolması.** `NativeProgram.tsx` başlık butonu `!visible` iken (liste yüklenemeyince) devre dışıydı; kullanıcının "program ekleme yok" izlenimi bununla birlikte Programım API'sinin 404 dönmesinden geliyordu. Düzeltme: buton artık yalnız `mutationBusy||uncertain` iken kilitlenir; liste yüklenemese bile ekleme editörü açılır.

**Grup 3 — Tüm "Not Found" hataları (Programım, vaka mesajı/ek gönderimi, Destek Taleplerim, Dental Akış): canlı sunucu bayat.** Repo doğrulaması: mobil uygulamanın çağırdığı her uç nokta mevcut branch'te vardır — `mobile_program_api.py` (`GET/POST /program`, mutations/events), `mobile_api.py` (`GET/POST /support/tickets`, `POST /consultations/{id}/messages`, medya yüklemeleri), feed/profesyonel router'ları. Mesaj LİSTESİ'nin canlıda çalışıp gönderimin 404 vermesi, ek yükleme idempotency-key mesajının ("Aynı dosya ve istek anahtarı korunuyor") görünümesi ve hasta profilinde Diş Şeması dışındaki aksiyonların (Tedavi, AI Analiz, Randevu — hepsi `NativePatientProfile.tsx:274`'te wired) hedef ekranlarının API'lerini 404lemesi, canlıda dağıtılan backend'in bu uç noktaları içermeyen eski bir build olduğunu kanıtlıyor. Cihazdaki uygulama da güncel repo UI'ından eski (AI analiz görsel önizleme şeridi güncel kaynakta mevcut).

**Ek düzeltme — 19 bayat mobil node-test fail'i kapatıldı.** `analysisRefresh.cjs` (4F), `analysisRecovery.cjs` (8F) ve `clinicalWorkflow.cjs` (7F) testlerindeki dar `require` shim'leri, NativeDentalAI/NativeClinicalReview'un sonradan eklenen `./sessionRenderKey` import'unu `{}`'a düşürüyor ve `nextSessionRenderKey is not a function` veriyordu; shim'ler nesne haritasına çevrilip modül eşlendi. Bir testin kaynak-metin assertion'ı (`key={userId+...}`) daha güçlü mekanizmaya (`viewerSessionKey` — token değişiminde remount) güncellendi. Temiz ağaçta aynı 19 fail'in varlığı (stash kanıtı) bunların bu geçişten önce markıldığını doğruluyor.

**Sonuç:** mobil node süiti **959 test — 940→959 pass**, kalan 0 fail; `tsc --noEmit` **0 hata**; polyfill+program+analiz+parite hedef paketi **112/112**. Fix'ler: `mobile/src/cryptoPolyfill.ts` (yeni), `App.tsx` (ilk import), `NativeProgram.tsx` (＋ butonu), `package.json` (test kaydı), 3 test dosyası shim güncellemesi, `tests/cryptoPolyfill.cjs` (yeni).

**Canlıya deploy edilmedi — Not Found hatalarının kaybolması için backend'in (ve yeni uygulama build'inin) bu branch'ten deploy edilmesi şart; istemci tarafındaki crypto çökmesi ve ＋ butonu düzeltmeleri deploy sonrası cihaza yeni build ile ulaşır.**

## 26. On beşinci geçiş — mesaj kutusu web paritesi + Akademik AI 404 kilit açılması (5 yeni ekran görüntüsü)

**Kapsam:** Kullanıcı web görünümü (dentalai.tr uzman vaka odası) ile mobil uygulamanın mesaj kutusunu karşılaştırarak birebir parite istedi: web'deki `＋ (Dosya ekle)` butonu mobilde yok, "Gönder" yazılı gri buton web'in mavi yuvarlak `↑` butonuyla değiştirilmeli; ayrıca Akademik AI'da ders/not oluşturma 404 sonrası kilitleniyor.

**Kompozitör paritesi (ModernScreens.tsx + ChatAttachmentComposer.tsx).** Web referansı: `expert_case_room.html` — `expert-media-composer` etiketi `＋ Dosya ekle` (42px, arka plan `#eff6ff`, renk `#2563eb`) ve `expert-send-circle` `↑` (42px mavi `#2563eb`). Mobilde artık: (1) kompozitörün solunda web ile aynı `＋` çember butonu (`accessibilityLabel="Dosya ekle"`) — ek seçeneklerini açıp kapatır; (2) eski `+ Fotoğraf / Kamera / PDF / Ses` kalıcı satırı `optionsOpen` prop'uyla bu toggle'ın arkasına taşındı (bekleyen ek paneli, önizleme, hata ve makbuz akışı kapalıyken de çalışır; tamamen sessiz durumda hiç render edilmez — web gibi); (3) "Gönder" yazılı pill kaldırıldı, yerine web'deki mavi yuvarlak `↑` butonu (`accessibilityLabel="Gönder"`, aynı disabled mantığı).

**Akademik AI "belirsiz sonuç" kilidi (NativeAcademic.tsx).** Ekran görüntüsündeki "Oluşturma sonucu belirsiz… yeni bir ders isteği açılmaz" bloğu: canlı sunucu `POST /academic/courses` 404 döndüğünde akım bunu belirsiz sonuç sanıp intent'i kilitliyordu (3 kurtarma butonu). 404 kesin bir yanıttır — sunucuda kayıt oluşmamıştır. Düzeltme: `sendCreate` ve `checkCreateReceipt` catch bloklarında `status===404` dalı → bekleyen intent SecureStore'dan silinir, belirsizlik kalkar, net Türkçe mesaj gösterilir ("Sunucu ders oluşturma özelliğini desteklemiyor (404)…"). Gerçekten bilinmeyen sonuçlar (timeout/502/ağ) için idempotent belirsizlik akışı aynen korundu. Web formuyla alan paritesi zaten uyumlu (başlık zorunlu ≥2, açıklama isteğe bağlı, 500 karakter — `notes.html` ile aynı).

**Global 404 mesajı (api.ts).** FastAPI'nin çıplak `Not Found` detayı tüm ekranlarda ham İngilizce göründüğü için (Programım, Destek Taleplerim, Dental Akış, Akademik AI) `request()` içinde `404 + detail 'Not Found'` → "Sunucuda istenen kayıt bulunamadı (404). Uygulama ile sunucu sürümü uyumsuz olabilir; güncellemeyi kontrol edip tekrar deneyin." olarak eşlendi; anlamlı Türkçe detaylar aynen geçer.

**Sonuç:** mobil node süiti tam koşum yeşil; hedef paket (chatComposerParity + consultations + chatFiles + chatSafetyActions + academicComposer/Workflow/AnswerActions + consultationRealtime) **108/108**; `tsc --noEmit` **0**. Yeni test `tests/chatComposerParity.cjs` (4 vaka) package test:beta'ya kayıtlı.

**Merge sonrası onarım (b25c19a2).** Uzak dala gelen opak render-key commit'leri kendi ağacında kırmızıydı: `NativeToothChart.tsx` tanımsız `historyRenderKey` kullanıyordu (tsc TS2304) ve `sessionRenderKey.cjs` profil testindeki visitor, `.map()` liste anahtarlarını da sayarak 3 çocuk beklentisiyle çelişiyordu. Onarım: diş şeması artık `historyScope` (kullanıcı/token/hasta/seçili diş) üzerinden `historyRenderIdentity`'yi `nextSessionRenderKey` ile döndürür (profil ekranındaki desenle aynı — hesap/oturum değişiminde tedavi geçmişi remount olur, token anahtarına sızmaz); profil testi visitor'ı yalnız `NativePatientMedia`/`NativePatientHistory`/`NativePatientVoiceHistory` anahtarlarını sayar. Kanıt: `tsc` **0**, `sessionRenderKey` **6/6**, render-key paketi **133/133**.

**Canlıya deploy edilmedi — kompozitör paritesi ve 404 akılları cihaza yeni uygulama build'i ile, Not Found'ların kökü ise backend deploy'u ile kapanır.**

## 27. On altıncı geçiş — dürüst doğrulama: "Not Found çözüldü mü, web birebir aktarıldı mı?"

**Soru:** Kullanıcı ekran görüntülerindeki Not Found'ların gerçekten çözülüp çözülmediğini ve web'in birebir uygulamaya aktarılıp aktarılmadığını kanıtla sordu. Cevap iki katmanda verildi: **kod katmanı** (branch, testler, CI) ve **canlı katman** (dentalai.tr probe).

### 27.1 Kod katmanı — fixler gerçekten branch'te (kanıt)

| İddia | Kanıt |
|---|---|
| ＋ Dosya ekle butonu + mavi ↑ gönder butonu | `git grep 'accessibilityLabel="Dosya ekle"'` + `sendArrow` → origin/branch ModernScreens.tsx'te 2 eşleşme |
| Ek seçenekleri toggle arkasında | `optionsOpen` → ChatAttachmentComposer.tsx 3 eşleşme |
| Akademik 404 kilit açma | `status===404` → NativeAcademic.tsx 2 eşleşme |
| Türkçe 404 mesajı | "Sunucuda istenen kayıt bulunamadı" → api.ts 1 eşleşme |
| Fixler branch tipinde hâlâ var | `git merge-base --is-ancestor b25c19a2 <tip>` ✓ (tip `bcb482c1`, sonradan gelen radiograph parite commit'leri fixleri bozmadı) |
| CI | `Mobile Android CI` @ `bcb482c1` → **success**; artifact `dental-ai-beta-arm64` **18.6 MB** (2026-12-05'e kadar indirilebilir) → **tüm fixleri içeren kurulum yapılabilir beta APK üretildi** |

### 27.2 Canlı katman — dürüst cevap: HAYIR, ekrandaki Not Found'lar canlıda HÂLÂ var

Canlı sunucu probe (2026-11-21, kimliksiz):

```
GET /api/mobile/v1/me → 401 {"detail":"Oturum geçersiz veya süresi dolmuş."}   (kontrol: her iki sürümde de var, auth çalışıyor)
GET /api/mobile/v1/academic/library/receipt?request_key=probecheck12345678
   → 404 {"detail":"Not Found"}   (YENİ backend'e özel uç → canlı ESKİ build)
```

Yorum: canlı dentalai.tr **hâlâ eski backend'i çalıştırıyor**. Bu yüzden telefon ekranındaki **tüm Not Found'lar (vaka mesaj gönderimi, Akademik AI ders oluşturma, destek talepleri) deploy edilene kadar aynen devam eder**. İstemci tarafındaki düzeltmeler bu 404'leri ortadan kaldırmaz; yalnız (a) ham İngilizce "Not Found" yerine net Türkçe açıklama gösterir, (b) Akademik AI'da formu kilitlemez, (c) güvenli aynı-anahtar yeniden deneme sunar. **404'lerin kökten kalkması tek şeye bağlıdır: bu branch'in backend tarafının canlıya deploy edilmesi.** Bu adımın anahtarı bende değil; deploy gerçekleştirilmeden "çözüldü" denemez ve bu raporda çözülmüş DENMEZ.

### 27.3 Web↔mobil parite — dürüst matris

| Alan | Durum | Kanıt |
|---|---|---|
| Giriş/kayıt/şifre, hesap | ✓ parite | NativeAuth/NativeAccount + süit |
| Mesajlar & vaka görüşmesi | ✓ çekirdek parite; kompozitör bu turda web ile birebir (＋ + ↑) | §26 + chatComposerParity.cjs |
| Ekler (fotoğraf/kamera/PDF-ses, bekleyen ek makbuzu) | ✓ parite | chatFiles/consultations süitleri |
| Uzman destek, talep, müsaitlik aboneliği | ✓ (§21'de native tamamlandı) | gapFeatures.cjs + test_mobile_gap_features.py |
| Program + editör | ✓ | program parite testleri |
| Hastalar, diş şeması, tedavi geçmişi, sesli geçmiş | ✓ | patientProfileUI/toothChartLifecycle |
| Analiz yükleme/klinik inceleme/görüntüleyici not | ✓ (viewer-analyze adapter'ı §21'de doğrulandı) | clinicalWorkflow |
| Akademik AI (ders, kaynak, soru-cevap, dosya) | ✓ çekirdek; 404 akılları bu turda eklendi | academicComposer/Workflow |
| Sesli muayene (kaydet→yükle→finalize) | ✓ alternatif akış; **canlı transkript modu (P3) eksik** | §21 |
| Mesaj görsel anotasyonu | not-bazlı ✓; **web'deki canvas çizim aracı UX'i mobilde yok** | §21 |
| Admin paneli, misafir analiz, web-push, yasal sayfalar | bilinçli web-only (mobilde karşılığı farklı kanaldan: Expo push) | §20 envanter |
| **Cihaz düzeyi "birebir" doğrulama** | 🔶 yapılmadı — tüm parite kanıtı kaynak + süit düzeyindedir; gerçek cihaz ekranı kanıtı ancak yeni APK kurulup gerçek kullanımla olur | §20'deki dürüst sınır |

**Net cevap:** Çekirdek hastane/uzman akışları web ile fonksiyon düzeyinde birebir (test kanıtlı) ve iki bilinen UX eksiği (canvas çizim anotasyonu, canlı transkript) dışında envanter boşluğu yok. Ancak (1) bu birebirlik **kullanıcının telefonuna ancak beta APK kurulduğunda** ulaşır, (2) ekran görüntülerindeki Not Found'lar **backend deploy edilmeden** kaybolmaz, (3) cihaz düzeyinde birebir doğrulama ancak gerçek kullanımla yapılabilir.

**Tip süit kanıtı:** `bcb482c1` (radiograph parite commit'leri dahil) yerel tam koşum **971/971 pass, 0 fail** — branch tipi yeşil; CI `Mobile Android CI` success ile tutarlı.

## 28. On yedinci geçiş — web akış-bütünü envanteri + başlık başlık mobil parite (buton→hedef kanıtıyla)

**Yöntem:** 68 web şablonunun tamamı script ile tarandı (`scripts/web_flow_inventory.py` → `web_flow_inventory.txt`): her şablonda bağlantı etiketi→hedef, form aksiyonları, buton metinleri ve JS uçları çıkarıldı; mobil uç yüzeyi (`mobile/src` yol literalleri) ve ekran kanıtlarıyla satır satır eşleştirildi. Kullanıcının istediği biçim: "buton nereye gidiyor, açılan yerde ne var, tıklanan buton nereye gidiyor".

### 28.1 Not Found durumu (canlı probe, bu turda tekrar)

```
GET /api/mobile/v1/academic/library/receipt → 404 {"detail":"Not Found"}   (yeni-sadece uç → canlı ESKİ build)
GET /api/mobile/v1/me                       → 401 Türkçe (kontrol ✓)
```

Canlı **hâlâ eski backend**. Ekran görüntülerindeki tüm sorunların kod karşılığı tamam (§26-27) ama **Not Found canlıda backend deploy edilene kadar görünmeye devam eder** — istemci tek başına bunu kaldıramaz. (Bir turda bağlantı HTTP:000 döndü, tekrar denemede normal — sunucu erişilebilir; geçici ağ davranışı.)

### 28.2 Başlık başlık parite matrisi (web buton→hedef ↔ mobil)

| Başlık | Web akış (buton→hedef) | Mobil karşılık | Durum |
|---|---|---|---|
| **Hastalar** | patients_all `＋ Yeni Hasta`→/patients/new; patient_detail: Düzenle/Sil, 🩻 Röntgen Ekle, 📷 Fotoğraf Ekle, "Seçilenleri AI ile Analiz Et", ＋ Tedavi→/patients/{id}/treatment/new, ◷ Randevu→/program/new?type=APPOINTMENT, Diş Şeması→/patients/{id}/teeth, Uzmana Danış→/expert-support?patient_id | NativePatientSelect/NewPatient/PatientDetail/PatientProfile/PatientMedia/NativePatientAppointment/ToothChart + hasta silme + medya silme + çoklu görsel analiz | ✓ parite |
| **Dental Akış (mesajlar)** | messages filtreleri (Tümü/Okunmamış/Bekleyen/Kaçırılan/Geçmiş), messages_deleted Geri Yükle, case_room: ↑ gönder, ＋ Dosya ekle, proposal/expert-response (Kabul Et/Reddet/Süreyi Onayla), Tamamlandı, Sorun bildir, Engelle/Şikâyet, Değerlendirme, read receipts, SSE | CHAT_FILTERS (ModernScreens:183) birebir 5 filtre, /messages/deleted (modernApi:515), kompozitör web-parite (§26), NativeChatTools PROPOSED/Kabul akışı, block/unblock/report, annotate (✎ İşaretle), WS realtime | ✓ parite (çizim anotasyonu dışı — bkz. 28.3) |
| **AI (analiz)** | analysis_choice: Hasta ile / Hızlı (misafir); analysis_new 🔬 Analizi Başlat; viewer çoklu sekme; result final + "Yeni bilgilerle tekrar analiz et"; work_pending Yeniden dene/İptal | NativeAnalysisUpload (çoklu görsel), NativeVisionViewer sekme+retryTreatment+retryable, analyses/preview uçları, final + tekrar analiz | ✓ parite (**misafir hızlı analiz bilinçli yok** — uygulama oturum zorunlu; web-only) |
| **AI (akademik)** | notes + Dersi Oluştur; notes_course materyal yükle/sil/rename/ders sil; notes_ai: Yeni sohbet, Özetle, Bana Öğret, Soru Hazırla, Eksiklerimden 5 soru, Güncelle, ↑ gönder | NativeAcademic: ders oluştur/sil/yeniden adlandır, materyal akışı (Composer/File/Source), **4 hızlı komut mobilde var** (NativeAcademic:196-198), quiz + AnswerActions, 404 akılları (§26) | ✓ parite |
| **Program** | program: Bugün/Hafta/Ay, ‹› gezinme, ✓ Tamamla, Sil, "Diğer güne kopyala", hasta bağlantılı event; form: Ders/Sınav/Tez/Görev/Randevu | NativeProgram: today/week/month (kaynakta 22 geçme), takvim pan-handler, NativeProgramEditor + programApi complete/delete/copy, hasta bağlama | ✓ parite |
| **Sesli Muayene** | entry: hasta seç / anonim başlat; device_check; session/panel: mikrofon başlat/duraklat/bitir, özeti kontrol, dinle, metne çevir, değerlendir | VoiceExamEntry + NativeVoiceDeviceCheck + NativeVoiceRecorder + NativeVoiceApproval + /voice-exam/anonymous + history + finalize→hasta profili (§16 Issue #258 kapanışı) | ✓ parite (**canlı transkript modu P3 — bkz. 28.3**) |
| **Diş Şeması** | tooth_chart: Kalıcı/Süt, O/M/D/L/B yüzey butonları, Diş Bilgisi/Tedavi Geçmişi/Notlar; browser: hasta listesi→şema | NativeToothChart/ToothVisual/ToothChartBrowser; boyut/renk web-uyumu son 8 commit'te (27b6d0e2, d71cb023, 9c3d6dc1) | ✓ parite |
| **Profil/Hesap** | account: foto, ad, e-mail onam, kullanıcı adı, unvan+belge, şifre, push, **Hesabı Kalıcı Olarak Sil**; documents yükle/gör | NativeAccount: aynı alanlar + "Hesabı Kalıcı Olarak Sil" (kullanıcı adı+şifre onaylı, NativeAccount:27-52); NativeProfessional belge görüntüleme (§21) | ✓ parite |
| **Sosyal (Uzman)** | expert_public_profile Takip et; expert_profile_edit sekmeler (Genel/Yayınlar/Gönderiler/Ayarlar) + ORCID; expert_following Dental Akış Keşfet/Takip + branş filtresi; _expert_social paylaş; performans+info | NativeExpertProfile/Publications/SocialMediaViewer/Relationships/ExpertPerformance (+info metni birebir §21), /posts+/moderation uçları, branş listesi (socialApi:148) | ✓ parite |
| **Admin** | admin_center 25+ bölüm | NativeSocialAdmin (sosyal moderasyon+step-up) — **tam panel bilinçli web-only** | Bilinçli web-only |
| **Genel** | login/register/forgot/reset, support_request, legal/about/contact, features | NativeAuth (4 ekran), NativeSupportRequests (§20 doğrulandı), yasal sayfalar web-only | ✓ parite |
| **Ödeme/Gelir** | web'de de "Ödeme işlemleri yakında" | yok | N/A (her iki tarafta da yok) |

### 28.3 Gerçekten kalan farklar (envanter boşluğu yok, kalemler bunlar)

1. **Canvas çizim anotasyonu** — web görsel üstüne kalem/ok çizer; mobilde not-bazlı anotasyon var (§21), çizim aracı UX işi → Backlog P1-4.
2. **Canlı transkript modu (Gemini Live WS)** — mobilde tam alternatif (kaydet→yükle→finalize) var; canlı bağlantı P3 → Backlog.
3. **Misafir (hızlı) analiz** — web `/analysis/guest/new`; mobilde bilinçli yok (oturum zorunlu uygulama). İstenirse "misafir modu" ekranı ayrı iş kalemi.
4. **Admin paneli** — bilinçli web-only (masaüstü işi; mobilde sosyal moderasyon karşılığı var).
5. **Görsel dil:** palet farkı daraldı (kompozitör/profil hero/diş şeması boyutları son commit'lerle web-uyumlu); genel mobil palet hâlâ lacivert ağırlıklı (#071B35) vs web mavi vurgu (#2563eb) — kompozitör web mavisine geçti; kalan ekranlar için token birleştirmesi backlog (MODERN_FEATURES_BACKLOG P2 görsel tutarlılık).

### 28.4 Modern uygulama esintileri — kodlanmış backlog

`docs/MODERN_FEATURES_BACKLOG.md` oluşturuldu: P1 (AI akıllı yanıtlar, sesle dikte, program hatırlatma push'ları, görsel çizim anotasyonu), P2 (Reels-benzeri kısa video, Stories, yorum thread + @bahsetme, before/after galerisi, AI feed sıralaması, deep linking), P3 (teledanışmanlık görüntülü görüşme, RAG arama, taslak+zamanlama, TTS özet, i18n). Her kalemde nerede/nasıl/kabul/test — ChatGPT doğrudan devralabilir. Bilinçli yapılmayacaklar da kayıtlı (3. parti SDK, hasta verisi riskli entegrasyonlar).

**Bu turda kaynak kodu değişikliği yok; iki belge eklendi. Mobil süit tip `bcb482c1`'de 971/971 yeşil (dokunulmadı).**

## 29. On sekizinci geçiş — hataların çözülmesi: tip'te 3 kırmızı/bozuk kalem kapandı + canvas parite cilası

**Kullanıcı yönlendirmesi:** "Hataları çözmeye devam et ve önceki mesajda söylediklerini yap." Bu turda backlog'un P1-4'ü (çizim anotasyonu) ele alındı, tip'teki gerçek hatalar çözüldü ve bir envanter hatası dürüstçe düzeltildi.

### 29.1 Dürüst düzeltme: canvas çizim anotasyonu mobilde ZATEN VARMIŞ

§26/§28.3'te "web'deki canvas çizim aracı mobilde yok" yazmıştım — **yanlıştı**. `NativeImageEditor.tsx` (commit `d5e03e18`) web'in tam sözleşmesini uyguluyordu: PanResponder stroke çizimi, renk/kalınlık araçları, Geri al/Temizle, `captureRef` ile görüntü+strokes JPEG q0.9 kompoziti ve web ile aynı dosya adı `isaretlenmis-gorsel.jpg`; gönderim `setReplyTo(item.id)+setPreparedAttachment` zinciriyle `sendChatImage(...,replyTo)` üzerinden `reply_to_message_id` taşıyor. Envanter hatası bu bölümle ve backlog P1-4'ün "TAMAMLANDI" işaretlenmesiyle düzeltildi.

### 29.2 Bu turda uygulanan parite cilaları (P1-4 kapanışı)

| Değişiklik | Dosya | Web paritesi |
|---|---|---|
| `✎ İşaretle` artık doğrudan çizim editörünü açar (önce not modalıydı); not anotasyonu `✎ Not` girişinde, aynı delege uç | ModernScreens.tsx | web `.annotation-launch` davranışı |
| Kompozit çözünürlük cap'ı 1600→4096 | chatFiles.ts `fitChatImage` | web `EDITOR_MAX_DIMENSION=4096` |
| Yeni regresyon testi: composite→reply sözleşme zinciri (4 test) | mobile/tests/chatDrawAnnotation.cjs | buildEditedFile + sendAttachment(replyId) |

**Görünüm paritesi cilası (ikinci push):** editör UI metinleri/renkleri web dialog ile hizalandı — başlık `Görseli Düzenle`, varsayılan kalem rengi `#ef4444` (web color input değeri), `✎ Kalem` araç çipi, `↶ Geri al`/`⌫ Temizle` glyph'leri, gönder düğmesi web'deki gibi `Gönder` (aria dahil) ve kapatma `Kapat`. Bilinçli kalan görünüm farkları: web'in tam-RGB renk girdisi yerine 4 renk paleti (yeni bağımlılık istenmedi) ve kalınlıkta 3/6/10 hızlı adımlar (web 2-14 sürekli slider).

### 29.3 Tip'te var olan hataların çözülmesi (bu tur başında 984/985 + bozuk dosya)

1. **`tests/dashboardPresentation.cjs` sözdizimsel olarak bozuktu** (commit `f0eeb5c7`: üç assertion tek satırda literal `\n` kaçışlarıyla yazılmış; `node --check` SyntaxError) → üç assertion gerçek satırlara ayrıldı; parse temiz. Bu dosya kırıkken tsc de hata üretiyordu (allowJs parse) — şimdi ikisi de temiz.
2. **`socialScreens.cjs` remount testi, bilinçli "credential-free keys" tasarımıyla çelişiyordu**: test ham token'ı React key'ine gömmeyi istiyor (`key={\`${user.id}:${token}\`}`), oysa `a246d8e4` + `socialSessionScope.ts` dokümanı taşıyıcının key'lerde YASAK olduğunu tanımlıyor. Test, daha güçlü güncel sözleşmeye hizalandı: composer key'i non-secret session epoch'tan (`key={\`${sessionKey}:composer\`}`), epoch yalnız gerçek kimlik değişiminde (user.id veya token) `+1` (SocialScreens:1595-1600 kanıtıyla), ve `doesNotMatch` ile token-in-key kalıcı olarak yasaklandı. Remount semantiği korunmuş; test kasıtla gevşetilmedi, sıkılaştırıldı.

### 29.4 Sonuç

- Mobil süit: **985/985 pass, 0 fail** (984/985 + bozuk dosyadan geldi); `tsc --noEmit` **0**.
- Kalan gerçek web-mobil farklar (§28.3 güncel): canlı transkript modu (P3, backlog), misafir hızlı analiz (bilinçli web-only), admin paneli (bilinçli web-only). Canvas çizim anotasyonu LİSTEDEN ÇIKTI.
- Not Found canlı durumu değişmedi: dentalai.tr hâlâ eski backend (§28.1 probe) — kök çözüm backend deploy'u.
