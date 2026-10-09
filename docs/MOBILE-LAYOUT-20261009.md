# Mobil yerleşim — deploy edilmedi

Kapsam mobil web/PWA ekranlarıdır. Native APK bu oturumda değiştirilmedi.

## Düzeltmeler

- Ortak mobil main üst boşluğu, Program / Destek / Mesajlar için biriken padding ve margin düzeltildi.
- Program formunun global `padding:0!important` ve iki sütun kuralı kontrollü biçimde geçersiz kılındı. Başlık ve kapatma aynı satırda; alanlar mobilde tek sütun. Gönder düğmesi alt menünün üzerinde kalır.
- Destek kartlarının iç padding'i geri verildi. Filtreler kart içinde yatay kayabilir; sayfa yatay taşmaz.
- Mesaj listesinde grid/flex öğeleri daralabilir; uzun ad ve durum etiketi kısalır. Kesintisiz sohbet metni, dosya adı ve medya kutusu sınırında kalır.
- iOS form odağındaki otomatik zoom için ilgili alanlar 16px. Header kenarlarında safe-area boşluğu vardır.
- CSS bottom `!important` kuralının visualViewport hesabını ezmesi giderildi. Mobil sohbet main yüksekliği de görünen alana uyarlanır; klavye kapanınca/masaüstüne geçince hesaplanan override temizlenir.
- Yeni network çağrısı, polling, backend kaynağı veya üretimde AI maliyeti eklenmedi.

## Doğrulama

Gerçek yerel Chromium 133 ile Jinja şablonlarından oluşturulan sentetik hesap/hasta verileri kullanıldı. Backend ve oturum açma bu fixture kontrolünün kapsamında değildir.

Boyutlar: 320×568, 360×800, 375×667, 390×844, 414×896, 430×932, 768×1024, 844×390.

Ekranlar: Mesaj listesi, Program formu, Destek talebi, uzman sohbeti, Profil (bölümler açık), Diş şeması. **48 yerleşim senaryosu geçti:** document yatay taşması yok. Program eylemi görünür olduğunda alt menü arkasında değil. Sohbet fixture'ında uzun kesintisiz metin, uzun dosya adı ve ses kontrolü bulunur.

Üç visualViewport senaryosu geçti: klavye açık, viewport yukarı kaymış, klavye kapalı. Hem composer hem sohbet alanı görünen alt sınır içinde. Bu, fiziksel klavye/cihaz testi değil, tarayıcıda kontrollü viewport simülasyonudur.

Diş şeması gerçek tarayıcı etkileşim kontrolü de geçti: son diş, süt dişi, analizsiz başlangıç, başlık-numara mesafesi, yüzey, durum toggle, lazy geçmiş ve kaçışlı içerik. Screenshot'lar görsel olarak incelendi. CSS/Python sözdizimi ve diff whitespace kontrolleri geçti.

## Sınır

Fiziksel iPhone/Safari veya Android cihazda son doğrulama yapılmadı. Bütün telefonlarda veya bütün ekranlarda kusursuzluk iddiası yoktur. Instagram tasarımının birebir kopyası hedeflenmedi; hedef ölçülen ekranlarda doğal, taşmayan ve erişilebilir yerleşimdir. Bu değişiklikler hâlâ hazırlık branch'indedir.
