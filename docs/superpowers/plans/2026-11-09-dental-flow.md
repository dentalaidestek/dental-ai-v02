# Dental Akış Implementation Plan

**Goal:** Onaylanmış uzman paylaşımlarını Keşfet/Takip Ettiklerim ve branş filtreleriyle ortak üye alanına taşımak.

**Architecture:** Mevcut ilişkiler API'si, sosyal kart ve yorum bileşeni genişletilir. Tek üye sayfası aynı API'yi keşfet veya takip kipinde çağırır; SQL görünürlük ve sorgu sınırları korunur.

**Tech Stack:** FastAPI, SQLModel/PostgreSQL, Jinja, mevcut Vanilla JS/CSS, pytest/Chromium.

**Spec:** docs/superpowers/specs/2026-11-09-dental-flow-design.md

## Constraints

Yeni tablo, AI çağrısı, servis ve ana sayfada besleme isteği yok. Bekleyen içerik genel akışa sızmaz. Kendi gönderisini yönetmek mevcut profile gider. Eski takip bağlantıları çalışır.

## Review focus

Yetki/aktif uzman durumunun değişmesi; iki yönlü engeller; sayfa sınırı silinince cursor; filtre/sekme korunması; aynı uzmanın birden çok kartında takip durumunun tutarlılığı.

- [ ] API başarısız testleri: keşfet/takip, branş doğrulama, gizli içerik, aktiflik/engeller, cursor ve sorgu sınırı.
- [ ] Paylaşılan feed sorgusu, toplu takip/uygunluk metadatası ve tek Dental Akış sayfası.
- [ ] Mobil/masaüstü görünüm, mevcut kart eylemleri, ana sayfa/menü girişleri; kendi gönderi menüsünün yönlendirmesi.
- [ ] API/PostgreSQL ve mevcut akış regresyonları, gerçek Chromium etkileşim/taşma/ekran görüntüleri.
- [ ] Bağımsız inceleme; ayrı PR ve doğrulanmış teslim raporu.
