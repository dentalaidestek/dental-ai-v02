# Tehdit modeli — 2026-11-25 (düşman perspektifinden savunma değerlendirmesi)

Amaç: Hasta verileri, uzman bilgileri ve ödeme bilgilerini ele geçirmek isteyen
bir aktörün gerçekçi yollarını sıralamak ve her yolun bugünkü durumunu
kapatık/açık olarak göstermek. Bu belge exploit tarifi içermez; mimari
seviyede saldırı yolu + mevcut savunma + kalan boşluk listeler.

## Değerli varlıklar (crown jewels)

1. **Hasta verileri** — kimlik + klinik notlar + analiz görselleri (KVKK hassas).
2. **Uzman bilgileri** — kimlik, unvan belgesi upload'ları (`expert_title_changes`),
   hasta ilişkileri.
3. **AI sağlayıcı anahtarları** — env'de (ANTHROPIC/GEMINI); doğrudan hasta verisi
   değil ama maliyet silahı ve hesap ele geçirme aracı.
4. **Ödeme yöntemleri — ŞU AN YOK.** Kod tabanında ödeme işleme/kart saklama
   yok (denetimde ödeme ucu bulunamadı; kota sunucu tarafı sayaç). Ele geçirilecek
   kart verisi bugün mevcut değil. Ödeme ekleneceğinde: işlemci (iyzico/Stripe)
   tarafında tut, PAN/CVV asla saklama, tokenizasyon sunucuda.

## Gerçekçi saldırı yolları (olasılık sırasıyla)

| # | Yol | Nasıl çalışır (mimari) | Bugünkü durum | Kalan boşluk |
| --- | --- | --- | --- | --- |
| 1 | **Uzman hesabının ele geçirilmesi (oltalama)** | En olası yol: sahte "hesabınız" maili → şifre/oturum → saldırgan o uzmanın hastalarını *meşru* yetkiyle okur. Argon2id'yi kırmaya gerek yok. | Şifre hashing, hız sınırları, hash'li token, SameSite ✓ | Uzmanlar için 2FA yok, yeni cihaz uyarısı yok, oturum listesi/uzaktan kapatma zayıf, anomalı giriş tespiti yok. Hassas okumalarda step-up yok (admin'de var olan desen uzmanlara taşınmalı) |
| 2 | **Uzman cihazının enfeksiyonu (infostealer)** | Uzmanın kendi bilgisayarı/telefonu ele geçer; çerez/token çalınır — siteye saldırı gerekmez. | Sunucu tarafı: token 7 gün, DB'de hash'li ✓ | Cihaz tarafı tamamen kullanıcının sorumluluğu; anormal eşzamanlı oturum uyarısı eklenmeli, hassas işlemde yeniden kimlik doğrulama |
| 3 | **Admin merkezi hedefleme** | Gerçek zamanlı OTP aktarım oltası (sahte admin girişi + anında kod isteme) | Parola + Gmail OTP + gizli yol + hız sınırı + sec-fetch-site ✓ | WebAuthn/passkey, admin girişi e-posta uyarısı, mümkünse admin yolu IP kısıtı |
| 4 | **Sahte/trojan APK dağıtımı** | Ürün APK linkiyle dağıtılıyor; saldırgan uzmanlara "yeni sürüm" diye mutasyonlu APK yollar → kimlik/oturum çalar. Sunucuya hiç dokunmaz. | Debug imzalı beta; imza uyuşmazlığı üstüne kurulum yapmayı engeller ✓ | Prod için gerçek release keystore zorunlu; SHA-256 resmi kanalda yayınlama; tek resmi dağıtım kanalı; ileride Play Store + bütünlük kontrolü |
| 5 | **Sunucu sırlarının sızması** | Render env'lerindeki Postgres/R2/AI anahtarları sızarsa (yanlış yapılandırma, log, personel) DB'nin tamamı okunur | Anahtarlar kodda değil, loglara sızmıyor (denetim ✓) | En az yetkili DB kullanıcısı + R2 token kapsamı, sırların periyodik rotasyonu, at-rest şifrelemenin Render tarafında doğrulanması |
| 6 | **Tedarik zinciri** | Kötü niyetli npm/pip bağımlılık güncellemesi → sunucu RCE veya istemci zararlısı | requirements-web.lock + package-lock pinleme ✓ | Bağımlılık güncelleme disiplini + audit taraması; colocated worker zaten sabit-argümanlı |
| 7 | **Uygulama katmanı açığı** | XSS/CSRF/IDOR/websocket yolları | Denetimde CRITICAL yok; CSRF middleware + CSP eklendi; IDOR kapalı ✓ | CSP'de inline script serbest (şablon borcu); WAF yok — Render starter önüne Cloudflare önerilir |
| 8 | **Hukuki yolla veri talebi** | "Devlet istese" senaryosu: hack değil, barındırıcıya tebliğ. Sunucu tarafındaki her veri bu yola açıktır. | Veri toplanıyor (sağlık verisi) | Sunucuda anahtarı olmayan **uçtan uca şifreleme** olmadan bu yola teknik çözüm yok; gerçekçi adım veri minimizasyonu + saklama politikası + bilinçli ürün kararı |
| 9 | **İçeriden/ekip** | Kendi ekibimizden biri veya Render personeli | Erişim izleri ✓ | En az yetki, break-glass kaydı |
| 10 | **Geliştirme akışının sızması** | Bu oturumda PAT düz metinle komut satırına yazıldı; log/screenshot sızarsa repo erişimi gider. Debug keystore + build ortamı da aynı kategori. | — | **PAT derhal rotate edilmeli**; token env/secrets'ta tutulmalı; beta keystore'u prod'dan ayrı |

## Öncelikli eylem listesi

1. **GitHub PAT'ini hemen yenile** (bu oturumda düz metin kullanıldı) ve bir daha
   komut satırına yazma; CI için ayrı, salt-okunur token kullan.
2. **Uzman hesaplarına 2FA (TOTP) + yeni cihaz e-posta uyarısı + oturum yönetimi** —
   gerçekçi saldırının %80'i bu yoldan gelir; admin'deki OTP desenini uzmana taşı.
3. **Hassas okumalarda step-up** (hasta listesi dışa aktarma, toplu görüntüleme):
   `socialAdminStepUp` deseni uzman tarafına genelleştir.
4. **Release keystore + APK SHA-256 yayınlama + tek dağıtım kanalı** — sahte APK
   vektörünü kapat.
5. **Admin için passkey/WebAuthn + giriş uyarısı.**
6. **Sırların rotasyon takvimi** (DB, R2, AI anahtarları) + en az yetki.
7. **Önüne Cloudflare/WAF** (bot filtre, rate limit, DDoS) — Render starter tek başına yeterli değil.
8. **Veri minimizasyonu + saklama politikası**; uçtan uca şifreleme isteğini bilinçli
   ürün kararı olarak ele al (KVKK + "devlet istese" barının tek gerçek cevabı).

## Dürüst özet

- Sunucuyu "hackleyerek" hasta verisi çalmak bugünkü tabanda zor: Argon2id,
  rate limit, IDOR kapalı uçlar, DB-aracılı dosya servisi, imzalı oturumlar.
- Gerçek risk **kimlik ve anahtar ele geçirme** (oltalama, infostealer, sızan
  sırlar, sahte APK) ve **hukuki yoldur** — ikisine karşı da yukarıdaki 1-8
  uygulanır; 8 için tek gerçek teknik cevap uçtan uca şifrelemedir.
- Ödeme verisi bugün yok; eklenecekse işlemci tarafında tutulmalı.
