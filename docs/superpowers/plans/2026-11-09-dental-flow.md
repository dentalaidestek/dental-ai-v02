# Dental Akış Implementation Plan

**Goal:** Onaylanmış uzman paylaşımlarını Keşfet/Takip Ettiklerim ve branş filtreleriyle ortak üye alanına taşımak.

**Architecture:** Mevcut ilişkiler API'si, sosyal kart ve yorum bileşeni genişletilir. Tek üye sayfası aynı API'yi keşfet veya takip kipinde çağırır; SQL görünürlük ve sorgu sınırları korunur.

**Tech Stack:** FastAPI, SQLModel/PostgreSQL, Jinja, mevcut Vanilla JS/CSS, pytest/Chromium.

**Spec:** docs/superpowers/specs/2026-11-09-dental-flow-design.md

## Constraints

Yeni tablo, AI çağrısı, servis ve ana sayfada besleme isteği yok. Bekleyen içerik genel akışa sızmaz. Kendi gönderisini yönetmek mevcut profile gider. Eski takip bağlantıları çalışır.

## Review focus

Yetki/aktif uzman durumunun değişmesi; iki yönlü engeller; sayfa sınırı silinince cursor; filtre/sekme korunması; aynı uzmanın birden çok kartında takip durumunun tutarlılığı.

- [x] API başarısız testleri: keşfet/takip, branş doğrulama, gizli içerik, aktiflik/engeller, cursor ve sorgu sınırı.
- [x] Paylaşılan feed sorgusu, toplu takip/uygunluk metadatası ve tek Dental Akış sayfası.
- [x] Mobil/masaüstü görünüm, mevcut kart eylemleri, ana sayfa/menü girişleri; kendi gönderi menüsünün yönlendirmesi.
- [x] API/PostgreSQL ve mevcut akış regresyonları; üç yeni DOM etkileşim kontrolü.
- [x] Gerçek Chromium etkileşim/taşma/ekran görüntüleri: ilk ortam engelinden sonra GitHub koşusu42682469412 ile616geçti/5atlandı; görseller incelendi.
- [x] Bağımsız inceleme; taslak PR #255 ve doğrulama sınırlarıyla teslim raporu.

## Kullanıcının eşzamanlılık devam isteği

- [x] Avatar bağlantısı, beş gerçek PostgreSQL yazarı ve sahiplik/idempotency testleri.
- [x] 60.000 kayıt +1.000uzmanla Keşfet/takip/profil okuma ölçümü; üretim sınırlarını raporla.
- [x] Tek yükleme yuvasını koruyup Retry-After beklemesi ve logout iptali ekle.
- [x] Cache kapasite hatasını503olarak işle; görsel GET tekrarı sınırla; aktif filtre kontrastını düzelt.
- [x] Son kaynak için616testlik tarayıcı/API/DB regresyonu, kullanıcı onaylı canlı yayın ve HTTPS sağlık/statik dosya doğrulaması.
