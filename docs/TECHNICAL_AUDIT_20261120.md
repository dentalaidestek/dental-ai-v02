# Dental AI — Teknik Denetim Raporu (2026-11-20)

Dal: `fix/main-five-mobile-routes-20261122` · Kaynak: `origin/live-main` (7550add6)
Not: Bu dosya canlı main'de bulunmadığı için bu dalda oluşturulmuştur. Numaralı
tam denetim kaydı (bölüm 1-37, Foto Fikir ve sağlamlaştırma dalgaları dahil)
yalnızca `feature/mobile-web-parity-20261110` dalındaki kopyada yaşar; tam
parite birleşmesinde iki kayıt tek belgede birleştirilmelidir.

## 38. Beş mobil parite rotasının canlı main'e damıtılması (2026-11-22)

### 38.1 Kapsam: doğrulanmış gerçek fark (ChatGPT listesi ve önceki özetler dış kaynak olarak kullanılmadı)

Kapsam `git diff origin/live-main...feature/mobile-web-parity-20261110` üzerinden
sıfırdan çıkarıldı; iki aday listenin uzlaştırması aşağıdadır. Canlı main'de
zaten var olan rotalar yeniden taşınmadı. Bu dalın taşıdığı altı rota:

| Rota | Parite dalındaki yeri | main'de durumu |
| --- | --- | --- |
| POST `/api/mobile/v1/consultations/{case_id}/attachments` | `app/mobile_api.py` mobile_chat_upload (PR 3884-3936) | YOK — eklendi |
| GET `/api/mobile/v1/consultations/{case_id}/attachments/{message_id}` | `app/mobile_api.py` mobile_chat_attachment (PR 3847-3864) | YOK — eklendi |
| GET `/api/mobile/v1/messages/unread-count` | `app/mobile_modern_api_v3.py` (PR 329-334) | YOK — eklendi |
| GET `/api/mobile/v1/notifications/unread-count` | `app/mobile_api.py` (PR 1845-1858) | YOK — eklendi |
| GET `/api/mobile/v1/experts/performance-info` | `app/mobile_professional_api.py` (PR 107-131) | YOK — eklendi |
| GET `/api/mobile/v1/consultations/{case_id}/message-receipt` | `app/mobile_api.py` (PR 2762-2801) | YOK — eklendi |

Semptom rota uzlaştırması: ChatGPT'nin beş maddesinden "analiz yükleme
makbuzu + kurtarma" ayrı bir uç DEĞİLDİR (makbuz mantığı PR'da
`mobile_analysis_api.py` içindeki yükleme uçlarının gövdesinde yaşar);
"hasta klinik medya yükleme makbuzu" için PR'da tek bir kurtarma ucu vardır
(`GET /patients/{id}/media/uploads/{request_key}`, PR 2660) ancak kapanışı
aşağıda belgelenen nedenle ağır; "uzman görüşmesi mesaj makbuzu" gerçek bir
rotadır ve bu dala alındı. PR #257'nin kendi regresyon matrisi
(`tests/test_parity_five_routes_regressions.py`) beş rotayı ekler
{konsultasyon ekleri POST/GET, messages/unread-count, notifications/unread-count,
experts/performance-info} olarak tanımlar; bu dal o tanımı temel alır ve
makbuz kurtarma ucunu matrisin dayattığı kapanış olarak ekler.

### 38.2 Önküsur dal durumu (dürüst kayıt)

Görev başladığında yerel dal beklenmedik biçimde 4 komitle mevcuttu
(eski uç 2f83a88b, reflog'da durur): sohbet rotaları D/E/F/G ve aksiyonlar,
destek makbuzları, okunmamış sayaçlar ve performans bilgisi. Bu komitler
kapsam dışı genişlikteydi ve revizyon-14 merdivenini
`MobileSupportMutationReceipt` tablosu olmadan ilerletiyordu (tam parite
birleşmesinde o adım revizyonu görünce tabloyu atlayacaktı — üretim riski).
Dal `origin/live-main` üzerine sıfırdan yeniden kuruldu; eski komitler
silinmedi, reflog'dan erişilebilir.

### 38.3 Bağımlılık sırası ve komitler

Her aşama tek başına yeşildir (py_compile + komşu paketler); hiçbir aşama
kapsam dışı içerik taşımaz:

1. `a7e1d14b` makbuz modeli + dört yardımcı (`ConsultationMessageReceipt`,
   `_normalize_consultation_client_message_id`,
   `_consultation_message_payload_hash`, `_consultation_message_payload`,
   `_consultation_message_receipt_replay` — parite dalından 1:1, PR main.py
   786-853) + migrate.py revizyon merdiveni 12 -> 13.
2. `25ddc5bc` mobil yardımcı katman: `_PRIVATE_MOBILE_RESPONSE_HEADERS`,
   `_mobile_private_no_store`, `_ChatFileResponse`/`_chat_offload`/
   `_chat_inspect` takma adları, `_mobile_chat_dispatch` (PR 1684-1688,
   1990-2000, 3689-3735) 1:1.
3. `adba616c` web handler deltaları: `expert_support_message` ve
   `expert_support_media_message` parite dalından byte-özdes (makbuz
   kaydı/replay + 403/404/409/423 ayrıştırması + safe_filename). İkinci
   handler main'de zaten var olan mobil metin mesaji rotasını da
   idempotency ile güçlendirir.
4. `8cfd6845` altı rota + yetki yapıştırıcısı + yeni
   `app/mobile_performance_info_api.py` (56 satır; handler PR'dan 1:1,
   `_account_user` ve `PlainLegal` PR mobile_account_api 104-108/16-21'den
   1:1 yerel kopya — PR'nin 221 satırlık 9 uçlu profesyonel modülü ve 217
   satırlık hesap modülü PR-only bağımlılık taşıdığı için port edilmedi).
5. Regresyon paketi: parite matrisinin bu tabana uyarlanmış hali (12 test).
6. `37597412` mini CI: vision48 bootstrap deseni, python-only.
7. Bu belge bölümü.
8. `451e54ff` web sözleşme pinleri: `test_security_hardening` revizyon
   pinleri yeni merdivene alındı (CONSULTATION_RECEIPT_REVISION = 13);
   arındırılmış görüşmede mesaj 410 (parite web handler sözleşmesi) ve
   salt kapalı vakada 409 kilidi. Not: 410 sözleşmesi parite dalının
   ucunda da kırıktır (146f7fce'de aynı test başarısız); bu dalda sözleşme
   güncellemesiyle yeşile alındı.

Dalların toplam farkı: 10 dosya, +1.123/-34 (test dosyası ve sözleşme
pinleri dahil). Üretim kodu +510 satır civarındadır; port edilen her
handler PR kaynağıyla satır satır karşılaştırıldı.

### 38.4 Ertelenmeler (satır bantlarıyla)

- Analiz yükleme makbuzu kapanışı (~700+ satır): `mobile_analysis_api.py`
  PR farkı +569, `analysis_upload_receipts.py` 137 yeni satır, v3 yüzey
  deltaları. Ayrı birim olarak parite dalında kalmalı.
- Hasta klinik medya makbuzu kapanışı (~500+ satır):
  `patient_media_receipts.py` 118 yeni satır, kurtarma ucu 26 satır, medya
  rota deltaları (PR mobile_api 2322-3118 bandı, ~700 satır fark bandı
  içinden makbuz parçaları), web deltaları upload/delete/delete-all
  (+12/-4, +12/-2, +27/-10) ve zorunlu `PATIENT_MEDIA_RECEIPT_KEY` ortam
  anahtarı (64 hex; yoksa kurtarma ucu 503). Bu dalın ölçütü ~400 satır;
  aşıldığı için ertelendi.
- Sohbet kümesi rotaları: `messages-live`, `read`, `actions`,
  `shared-media`, `deleted` (PR'nin D/E/F/G bandı) — beş rota matrisinin
  kapanışında değil; rozet temizleme akışları bu kümede. Regresyonlarda bu
  semantikler `_consultation_unread_total`'ın tükettiği
  `ConsultationInboxState` satırları doğrudan yazılarak kilitlenir.
- `MobileSupportMutationReceipt` ve destek makbuzları: ayrı birim; revizyon
  14 parite dalına bırakıldı (bu dalın 13 merdiveni 12/13 kaynaklı 14 adımını
  bozmadan birleşir).
- `.cjs` istemci kontrat testleri: main'in `mobile/src` ağacında
  professionalApi/chatFiles/notificationsApi karşılık çağrıları YOK (11
  dosyalık eski istemci); istemci paritesi parite dalının kapsamıdır.

### 38.5 Migration ve canlıya alma gereksinimi

- Şema: `consultationmessagereceipt` tablosu. SQLite/test yolu
  `create_all` ile karşılanır; üretimde (Render) `init_db` DDL'i
  çalışmadığından tablo yalnız `python -m app.migrate` revizyon-13 adımıyla
  açılır (postgres, transaction-lock, checkfirst).
- `require_schema` artık revizyon 13 bekler: revizyon-12 veritabanı ile
  servis bilinçli olarak başlamaz. Sıra: (1) `python -m app.migrate`,
  (2) servis derle. Geri alma: tablo additive'dir; revizyon numarası 12'ye
  alınabilir, tablo bırakılabilir.
- Ortam değişkeni gerektirmez (ertelenen makbuz kapanışlarının anahtarları
  bu dala girmedi).
- Tam parite birleşmesi: parite dalının revizyon-14 adımı 12/13 kaynakları
  kabul eder; bu dalın merdiveniyle çakışmaz.

### 38.6 Test, CI ve doğrulama

- `tests/test_parity_five_routes_regressions.py`: 12 test, rota başına
  sahiplik / yetki / idempotency / aynı-istek-anahtarı kurtarma / yanlış
  hesap boyutları; 3 arka arkaya koşuda 12/12 sabit.
- main tabanına uygun komşu paketler: `test_chat_read_http.py` +
  `test_chat_read_cursor_isolated.py` 8/8 (main'de olduğu gibi).
- openapi.json doğrulaması: 6/6 rota kayıtlı; anonim istek 6/6 401
  (revalidation sözleşmesi).
- Taban karşılaştırması: 16 komşu paket (sohbet okuma, danışmanlık akışı,
  destek, güvenlik sertleştirme, gerçek zamanlı mesajlaşma, sorgu verimliliği
  ve bu daldaki regresyon dosyası) bu dalda 187 test; başarısız küme main
  tabanındaki 7550add6 klonuyla satır satır diff'lendi. main'de önceden
  kırık tek test (test_support_ticket_flow tam yaşam döngüsü) bu daldan da
  aynı biçimde kırıktır; salt bu dalda yeni kırılan iki sözleşme pini
  (revizyon 12 pini, arındırma 409 pini) `451e54ff` ile güncellendi — net
  yeni başarısızlık sıfır.
- Mini CI: `.github/workflows/five-routes-mini-ci.yml` — yalnız bu dala
  push + workflow_dispatch; py_compile (5 dosya), 12 testlik paket, komşu
  paketler ve revizyon-13 geçiş şeması.

### 38.7 Sinirlar ve net beyan

- Rozet temizleme (okundu/arsiv) bu daldaki mobil yuzeyde ayrı rotalarla
  değil, web semantiğiyle sayaç üzerinden doğrulanır; temizleme rotaları
  parite dalının sohbet kümesiyle gelecek.
- Analiz ve hasta medya makbuz kurtarma bu daldaki yüzeylerde yok; bu
  bilinçli bir ertelemedir ve 38.4'te sınırları çizilmiştir.
- Canlıya alınmadı: bu dal main'e merge edilmedi, uzak depoya push
  edilmedi, herhangi bir ortama deploy edilmedi. `feature/mobile-web-parity-20261110`
  ve `fix/mobile-web-parity` dallarına dokunulmadı. Canlıya alma yalnız
  38.5'teki sırayla, ayrı bir kararla yapılmalıdır.
