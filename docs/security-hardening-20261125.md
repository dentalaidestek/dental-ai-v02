# Güvenlik sertleştirme turu — 2026-11-25

Statik güvenlik denetimi (backend + web şablonları + mobil istemci) sonrasında
uygulanan düzeltmeler. Denetimde CRITICAL seviye bulgu yok; mevcut taban
(Argon2id parola hashing, SHA-256 hash'li oturum token'ları, HttpOnly+Secure+SameSite
çerez, admin Gmail OTP + gizli yol, DB-aracılı upload servisi, IDOR kapalı uçlar,
Pillow pixel/EXIF doğrulama, Origin allowlist'li WebSocket, env'de anahtarlar)
"iyi korunmuş" olarak doğrulandı.

## Kapatılan bulgular

| ID | Bulgu | Düzeltme |
| --- | --- | --- |
| H1 | Render'da TLS edge proxy'de sonlandığı için uvicorn isteği http görüyor, HSTS koşulu asla sağlanmıyordu | `render.yaml` startCommand'a `--proxy-headers --forwarded-allow-ips="*"`; HSTS başlığı `app/main.py` security_headers middleware'inde koşulsuz basılıyor |
| H2 | Foto Fikir metin AI uçları (ideas/slides/ig/reels + generate taslak çağrısı) kota ve hız sınırı olmadan Claude çağırıyordu → sınırsız token maliyeti | `app/foto_fikir_api.py`: `_ff_throttle` (auth_rate.admit ile kullanıcı başına ideas 10, slides 10, mevzuat 30, ig 5, reels 5, generate 3, brand 6/3 per 60sn) + `_ff_ai_budget` (provider_budget.reservation: kullanıcı başına inflight cap + istek bütçeleri; ProviderBusy → 429 Türkçe) |
| M2 | Çerezli mutasyonlarda CSRF yalnızca SameSite=Lax'a dayanıyor | `app/main.py` yeni `cookie_csrf_guard` middleware: çerezli POST/PUT/PATCH/DELETE'te `sec-fetch-site` cross-site → 403; header yoksa Origin↔host karşılaştırması; Bearer (mobil) ve Bearer'sız eski tarayıcı muaf |
| M3 | HTML sayfalarında CSP yok | security_headers middleware'ine `Content-Security-Policy`: `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'` (inline JS kullanan şablonlar bozulmadan external script enjeksiyonu kapanır) |
| M4 | Unvan/belge upload'ında yalnız uzantı+boyut kontrolü vardı; etiketi yanlış/polyglot dosya admin'e inline ulaşıyordu | `professional_title_document_upload`: magic-byte imza kontrolü (%PDF-, JPEG FFD8FF, PNG 89504E47); uymayan 400 |
| L1 | IP başına giriş deneme sınırı 100/10dk dağıtık password spray'e cömert | default 100→40 (`AUTH_IP_RATE_MAX_ATTEMPTS`) + render.yaml envVarGroups'e açık env |

## Bilinen ve ertelenen

- **M1 (MEDIUM, kısmen hafifletildi):** görsel üretim kotasında TOCTOU yarışı —
  kota kontrolü üretimden önce, iş kaydı sonrasında yapılıyor; paralel istek
  burst'i 30/ay sınırını aşabilir. Tam çözüm (rezervasyon + iade) iş kayıt
  modelinin yeniden kurgusunu gerektirdiğinden bu turda yapılmadı; generate
  ucuna 3/60sn kullanıcı sınırı eklendi (aşım üst sınırı ~3 görsel/burst).

## Doğrulama

- `pytest tests/test_security_hardening.py tests/test_mobile_chat_route_security.py` → 47/47
- Duman testi (`scripts/sec_smoke.py`): cross-site çerezli POST → 403; same-origin
  POST → geçer; Bearer muaf; header'sız POST geçer; CSP + HSTS başlıkları yanıtla çıkıyor.
- Foto Fikir sözleşme/parite testleri (mobile/tests/fotoFikir*.cjs) → 27/27.

## Operasyonel not

`render.yaml` değişikliği (proxy-headers + AUTH_IP_RATE env) bir sonraki
deploy'da etkin olur; kod tarafındaki başlık/middleware değişiklikleri deploy
ile birlikte yayına girer. Mobil APK bu turdan etkilenmez (sunucu tarafı
sertleştirme); APK içeriği bu daldaki mobil parite + metin temizliği + güvenlik
turunun tamamını taşır.
