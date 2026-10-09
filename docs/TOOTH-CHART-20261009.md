# Diş şeması — hazırlık değişikliği, deploy edilmedi

- Alt çene etiketi normal akışta numaraların altında; üstüne binmez.
- Sabit 16 seçimi kaldırıldı. Yetkili hastanın en son AI_ANALYZED / AI_FINAL / VISION_READY analizindeki geçerli FDI numarası seçilir. Süt dişi için süt şeması açılır. Böyle bir analiz yoksa panel kapalı başlar.
- İlk açılışta tüm analiz ve tedavi nesnelerinin çekilmesi kaldırıldı. Tek skaler son-diş sorgusu kullanılır. Geçmiş yalnız sekmesi açılınca alınır.
- Ortak diş atlası ve seçilen diş tipi panelde de kullanılır. Alt çene ters yöndedir. Çürük/dolgu, kron, kanal, çekilmiş diş ve implant farklı şekillerle gösterilir. Seçilen yüzey önizleme işaretinin konumunu değiştirir.
- Not görünür alana taşındı; kayıtlı genel not diş seçiminde doldurulur. Başka dişe geçince önceki dişin notu taşınmaz. Kaydetme endpointi değiştirilmedi.
- Geçmiş metinleri HTML olarak yorumlanmaz; eski dişin geciken cevabı yeni paneli doldurmaz.

## Kontrol

Render edilmiş Jinja sayfasında gerçek JavaScript, yerel DOM ortamında kontrol edildi: son diş, süt dişi, analizsiz başlangıç, not korunması, yüzey, durum toggle, diş tipi, lazy geçmiş, HTML kaçışları, POST adresi ve çift gönderim. JavaScript hatası yok. Python derleme ve diff whitespace kontrolü geçti.

Sonraki mobil yerleşim oturumunda Chromium alternatifi açıldı: gerçek tarayıcı screenshot/ölçüm ve diş etkileşimi kontrolleri tamamlandı. Mobil yerleşim raporu: `MOBILE-LAYOUT-20261009.md`. Backend route bu oturumda tam uygulama ortamında çalıştırılmadı. Referansa piksel piksel eşitlik doğrulanmış değildir. Yeni görsel atlas referanstan üretildi; kaynak resmin birebir kopyası değildir. Süt dişleri aynı temel şekilleri kullanır.

## Görsel

Dosya: `app/static/tooth-chart/enamel-atlas-v2.webp` (~167 KB), ortak ve önbelleklenebilir. Built-in imagegen ile yalnız geliştirme sırasında üretildi; uygulamada görsel üretimi veya yeni AI çağrısı yoktur.

Prompt: Reference is style only. Transparent four-cell horizontal atlas; left to right healthy molar, premolar, canine, incisor; crowns at top, roots downward; same height and centered cells; detailed realistic ivory translucent enamel matching reference; no colored conditions, text, numbers or UI. Statik durum/yüzey işaretleri kodla uygulanır.
