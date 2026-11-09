# Yorum sistemi — kurtarılan çalışma ve PR teslimi

9 Kasım 2026 tarihinde önceki çalışma ortamındaki kaydedilmemiş kod ve testler kurtarıldı. GitHub main `bd17de046a58ddf924afb343aaca3dc103ad536e`, son canlı uygulama PR #253 ile karşılaştırıldı. Bu yorum geliştirmesi o sürümde bulunmuyordu.

## Tamamlanan davranışlar

- Küçük avatar ve metinlerle mobil alt panel; masaüstünde aynı yorum bileşeni. Tek satırlık, gerektiğinde büyüyen yazma alanı, emoji seçimi ve gönderme simgesi.
- Yanıtlar başlangıçta kapalıdır. Açılınca en fazla 10 yanıtlık sayfalar getirilir; kapatıp açmak gereksiz istek üretmez. Ana yorumlar da sayfalanır.
- Yorum/yanıt beğenileri sunucuda saklanır. Tekrarlanan istekler aynı ilişkiyi çoğaltmaz. Başarısız istek mevcut beğeniyi değiştirmez.
- Düzenle, sil ve bildir işlemleri üç nokta menüsündedir. Uzman profil bağlantıları, ana yorum silinince yanıtların kaldırılması, moderasyon ve yetki kontrolleri korunur.
- Kapatma/geri tuşu taslağı korur. Önceki pencerenin gecikmiş gönderim sonucu yeni taslağı silemez.
- Gönderim tekrarlarında sunucunun yorum ve ana yoruma ait yanıt sayısı kullanılır. Eski GET yanıtları daha yeni işlemleri geri alamaz; en fazla bir düzeltici istek yapılır.
- Yeni beğeni tablosu, birleşik benzersiz anahtar, yabancı anahtarlar ve yanıt sorgusu indeksleri eklendi. Hesap anonimleştirilirken beğeniler ayrıca temizlenir.

## Veritabanı ve dağıtım koşulu

Değişiklikler eklemelidir; mevcut baseline 12/social 2 uyumluluğu korunur. Dağıtımdan önce `python -m app.migrate` çalıştırılmalıdır. Şema hazır değilse uygulama başlangıç denetimi eksik tabloyla trafik kabul etmez. Başarılı geçiş sabit ve içerik içermeyen `social.schema ready version=2 comment_likes=true` kaydını üretir. Yeni bağımlılık veya ücretli servis eklenmedi.

Bu çalışmada main birleştirmesi ve Render dağıtımı yapılmadı. Canlı hesap üzerinde yeni yorum özelliği testi yapılmadı; uygulama yerel test hesaplarıyla doğrulanır.

## Test kapsamı

API yetkileri, CSRF, gizli/engellenmiş yorumların görünürlüğü, sayfalama, beğeni tekrarları, gerçek PostgreSQL yarışları ve silme davranışı, şema geçişi, emoji, 360/430/1280 px arayüz, yavaş yanıt/taslak ve tekrar gönderim senaryoları kapsanır. Nihai çalıştırma sonuçları PR açıklamasında belirtilir.

Önceki çalışmadan kalan akademik/genel CI başarısızlıkları bu değişikliğin tamamlandığı iddiasına dahil değildir; ilgili iş akışları PR üzerinde ayrıca izlenmelidir.

## Kesilen sohbetten ikinci kurtarma — 9 Kasım 2026

- Değiştirilen 14 mevcut dosyanın başlangıç blob SHA değerleri GitHub main `bd17de046a58ddf924afb343aaca3dc103ad536e` ile tek tek eşleşti. Önceki çalışma yeniden yazılmadan kurtarıldı.
- Önceki oturumun son sosyal regresyon kaydı **302 geçti, 5 atlandı** sonucunu içeriyordu; bu kayıt güncel oturumda yeniden çalıştırılmış tarayıcı testi olarak sunulmaz.
- Yeni bağımsız inceleme, gönderim beklerken seçilen başka yanıt/düzenleme hedefinin eski POST sonucu tarafından sıfırlanabildiğini buldu. Başarılı sonuç artık yalnızca metin ve hedef hâlâ gönderilen taslakla eşleşiyorsa yazma alanını temizler.
- Aynı üretim JavaScript dosyasını çalıştıran JSDOM denemesi düzeltmeden önce hedef kaybıyla başarısız oldu; düzeltmeden sonra **yanıt ve düzenleme için 2 senaryo geçti**. Kalıcı Chromium testleri sonraki isteğin doğru `parent_id` veya düzenlenen yorum kimliğiyle gönderildiğini de kontrol eder.
- Güncel yerel API/veritabanı/güvenlik/danışmanlık/sesli muayene paketi: **404 geçti**. Ek ilişki/yorum sözleşmesi: **25 geçti**; kalan güvenlik/şema/kapasite kontrolleri: **43 geçti, 4 isteğe bağlı dış servis testi atlandı**. Böylece birbirinden ayrı yerel Python koşularında toplam **472 geçti, 4 atlandı**. Gerçek, geçici PostgreSQL kümesinde eşzamanlı beğenme, şema geçişi ve yabancı anahtar/silme kontrolleri dahil.
- Güncel oturumda tam tarayıcı koşusu başlatıldı, fakat Chromium uygulama açılmadan `socket() failed: Operation not permitted` hatasıyla durdu. Bu ortam hatası başarılı tarayıcı testi olarak sayılmaz; PR'ın mevcut GitHub Expert Social iş akışı tarayıcıları yeniden çalıştırır.
- JavaScript sözdizimi ve diff boşluk denetimi geçti. Akademik/genel uygulama paketinin tamamı bu oturumda tekrar çalıştırılmadı.

`docs/social-completion/compact-comments-{360,430,1280}.png` dosyaları önceki başarılı yerel tarayıcı koşusundan kalan sentetik ekranlardır; canlı ekran oldukları iddia edilmez.
