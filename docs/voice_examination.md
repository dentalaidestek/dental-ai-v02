# Sesli muayene — ilk inceleme sürümü

Bu dal mevcut hasta ekranına bir sesli muayene bölümü, yeni hasta ekranına
anonim başlangıç ekler. Ayrı bir muayene raporu sayfası oluşturmaz.

Akış: mikrofon / metin → tek Gemini çözümleme çağrısı → konuşmadaki birebir
dayanağıyla alan önerileri → hekimin düzenleyip seçmesi → tek işlemde kayıt.
Ad, soyad ve yaş başlangıçta seçili değildir. Boş / seçilmeyen alanlar korunur.
Klinik notlar mevcut Analysis DRAFT kaydına gider; tanı veya analiz çağrısı
otomatik çalışmaz. Diş şeması ve randevu ayrı onay ister. Randevu tarihi model
tarafından hesaplanmaz; hekim Türkiye saatiyle seçer ve mevcut program
doğrulayıcısı / bildirim akışı kullanılır. Yinelenen onay aynı request_key için
yeni klinik kayıt, randevu veya şema değişikliği oluşturmaz.

## Etkinleştirme

- `VOICE_EXAM_ENABLED=1` (varsayılan `0`).
- Mevcut `GEMINI_API_KEY` kullanılır.
- `VOICE_EXAM_GEMINI_MODEL` isteğe bağlıdır; yoksa mevcut
  `DENTAL_CLINICAL_AI_MODEL`, o da yoksa projenin klinik varsayılanı kullanılır.
- Yeni tablo / migration yok. Onay işlemi mevcut WorkJob tablosuna yalnız
  sahiplik, kaynak kimliği ve idempotency kaydı yazar; ses / transkript yazmaz.
- Bu dal production'a otomatik dağıtılmak üzere hazırlanmadı. Hasta verisi
  kullanmadan sentetik Türkçe ses ve gerçek cihazlarla doğrulanmalıdır.

## Veri ve kapsam

Ses yalnız bellekte işlenir; uygulama diske/R2'ye ses kaydı yazmaz. Aktarımda
ses görüşmedeki kişisel verileri içerebilir; tam anonimleştirme iddiası yoktur.
Arayüz, dış Gemini aktarımını açıklayan onay ister. Kayıtlı hasta kimliği veya
geçmişi sağlayıcı isteğine eklenmez. Metin girişinde mevcut doğrudan kimlik
maskeleme yardımcısı kullanılır. Sağlayıcı hataları ham yanıta / anahtara / URL'ye
yer vermez; otomatik ücretli yeniden deneme ve Claude/OpenAI fallback yoktur.

İlk sürüm ses bölümünü kullanıcı duraklatınca veya 90 saniye dolunca işler;
canlı STT / gerçek zamanlı acil uyarı sistemi değildir. Alerji, ilaç, hastalık,
negasyon ve belirsizlik hasta beyanı olarak incelemeye taşınır. İlaç etkileşimi,
olası tanı ve aciliyet çıkarımı üretmez. Hekim bir ders ve konu seçerek mevcut
Academic AI kaynak aramasından dosya/sayfa bilgili alıntıları açabilir. Bu arama
mevcut yayımlanmış parça arayıcısını kullanır; ek LLM çağrısı yapmaz. Ders notu
alıntıları klinik güvenlik veya ilaç etkileşimi doğrulaması sayılmaz.
Doğrulanmış kritik klinik kurallar ve native mobil kayıt henüz bağlı değildir.
Arka planda kalıcı ses oturumu yok; sayfadan ayrılma uyarısı gösterilir
ve mikrofon kapatılır. Kaydedilmemiş taslak tarayıcı belleğindedir.

## Doğrulama

`pytest tests/test_voice_exam.py tests/test_voice_exam_panel.py -q`

`node --check app/static/voice-exam.js`

Gerçek sağlayıcıyla henüz denenmedi. Canlı hasta sesleri geliştirme testinde
kullanılmamalıdır. Sentetik ses testi; Chrome Android / Safari iOS mikrofon
izni, duraklatma, hata sonrası aynı Blob'u tekrar işleme, olumsuz ifadeler,
birbirine karışan konuşmacılar, şema ve randevu onayı ayrı ayrı denenmelidir.
