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

İlk PR tesliminde main birleştirmesi ve Render dağıtımı yapılmadı. Daha sonraki kullanıcı onaylı yayın aşağıdaki sürüm kaydındadır. Canlı hesap üzerinde yeni yorum özelliği testi yapılmadı; uygulama sentetik hesaplarla doğrulanır.

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

`docs/social-completion/compact-comments-{360,430,1280}.png` dosyaları son GitHub Chromium koşusunun sentetik ekranlarıyla güncellendi; canlı ekran oldukları iddia edilmez.

## Gönder düğmesi, admin inceleme bildirimi ve hız

Kullanıcının devam talebiyle aynı PR genişletildi. Gönder düğmesi yazma alanının içine taşındı: 34×34 px koyu yuvarlak, yalnızca yukarı ok; erişilebilir adı “Gönder”. Yanıt/düzenleme taslak korumaları devam eder.

Admin panelinde mevcut “Gönderi ve Yorum Denetimi” bölümü bulundu; yeni içerik için admin bildirimi eksikti. Yeni/düzenlenen ve inceleme gerektiren gönderi, yorum ve yayın artık aktif, e-postası doğrulanmış sabit admin hesabına tekilleştirilmiş bildirim oluşturur. Metin/görsel/kişisel veri bildirime kopyalanmaz. Bildirim doğru içerik türü ve kimliğiyle denetim ekranını açar; menüde bekleyen içerik sayısı görünür. İnsan kararı, otomatik kontrolün düzelmesi ve yorum/gönderi/hesap silme zincirleri eski bildirimleri kapatır.

Bildirim ve içerik aynı DB işlemindedir; rollback ikisini de geri alır. Ağ yayını yalnızca dış işlem commit olup oturum kapandıktan ve HTTP gövdesi gönderildikten sonra yapılır. Anlık teslim başarısız olursa kalıcı bildirim ve olay kaydı korunur. Yeni tablo/servis/sağlayıcı yoktur.

| Ölçülen yük / neden | Değişiklik / sınır |
| --- | --- |
| Son canlı yeniden açılış: 13:32:16–13:33:14 UTC, yaklaşık 58 saniye; yaklaşık 28 sn import ve 30 sn startup. Free servis. | Kurulu şema hazırken tekrar migration/backfill çalıştırılmaz; eksikse mevcut migration ve ardından readiness denetimi çalışır. Uygulama eksik şemayla başlamaz. İlk import süresi ve platformun uyuması tamamen giderildi iddiası yoktur. |
| 32 uzman için eski dizin sorgusu 195 SQL çalıştırdı. | Kullanıcı, politika, kapasite ve performans istatistikleri toplulaştırıldı; aynı sentetik senaryoda 8 SQL. Mevcut SQLite/PostgreSQL ortalama/yuvarlama testleri korundu. |
| Ana stil 257.992 bayt; sosyal stil 54.205 bayt. | Yalnızca herkese açık `/static` dosyaları gzip ile sıkıştırılır. Yerel gzip karşılıkları sırasıyla 44.850 ve 10.857 bayt. Sürüm parametreli dosyalarda bir günlük önbellek; özel HTML/klinik veri önbellek kuralları korunur. |
| Render HTTP gecikme metriği boştu; son CPU/bellek örneklerinde kaynak baskısı görülmedi. | Tüm sayfa gecikmelerinin tek nedeni bulundu veya canlı gecikme artık belli bir süreye indi denmez. |

Bu değişikliklerin ilk doğrulaması: **95 geçti** (admin inbox, rollback/teslim, silme zincirleri, startup, schema, eski moderasyon/temizlik ve gerçek PostgreSQL danışmanlık performansı dahil). GitHub'da önceki `e410e23` sürümünün Expert Social koşusu **560 geçti, 5 atlandı**; bu yeni değişikliklerin tarayıcı sonucu değildir. Güncel tam regresyon ve tarayıcı sonucu PR üzerinden ayrıca kaydedilir.


## Son doğrulama

- Uygulama commit: `959a265ac75f5179d95dc025eab6f1de581752c4`.
- Ayrı yerel koşuların örtüşmeyen toplamı: **487 geçti, 4 dış servis testi atlandı**.
- GitHub Expert Social: **575 geçti, 5 atlandı**; gerçek Chromium, yeni düğmenin 34×34 boyutu/simgesi, admin menüsündeki sayaç, bildirimden doğru içerik ekranına geçiş ve kuyruktan insan onayı dahil. Koşu: https://github.com/dentalaidestek/dental-ai-v02/actions/runs/42630984117
- Admin security, Security recovery ve Mobile Android CI geçti.
- Academic V2: 40 başarısız sonuç; listelenen 30 test kimliği önceki e410e23 ile aynı, yeni kimlik yok. Semantic PostgreSQL başarısız iki test kimliği de öncekiyle aynı (`test_every_allowed_planner_search_reaches_real_postgres[8]`, `[16]`). Genel uygulama paketi ayrı izlenir; tüm depo yeşil olarak sunulmaz.
- Son bağımsız incelemede açık önemli bulgu kalmadı. Zincirleme silmede bildirim kapanması API ile yeniden doğrulandı.
- Güncel sentetik görseller `docs/social-completion/compact-comments-{360,430,1280}.png` ve `moderation-human-queue-1280.png`. 360 px yorum ve 1280 px denetim ekranı ayrıca görsel olarak incelendi.
- İlk teslimde main birleştirmesi/Render dağıtımı yapılmadı. Sonraki onaylı yayın aşağıda kayıtlıdır; ücretli altyapı değişikliği yapılmadı.


## Kullanıcı onaylı canlı yayın — 9 Kasım 2026

- Kullanıcı “Canlıya alalım artık” talimatıyla PR #254 dağıtımını onayladı.
- PR #254 squash ile main’e alındı: `2a8073d21311500ef49e85db4f0e471d18773ff6`.
- Render servisi `dental-ai-v02`; dağıtım `dep-dbp0fep42hec73db3vm0` otomatik tetiklendi. İkinci bir deploy başlatılmadı.
- Durum **LIVE**: 9 Kasım 2026 **17:51:51 UTC / 20:51:51 Türkiye saati**.
- Geçiş kaydı: `social.schema ready version=2 comment_likes=true` (17:51:41 UTC); uygulama başlangıcı tamamlandı.
- Canlı tarayıcıda `/healthz` ve `/readyz` yanıtları `{"ok":true}` olarak doğrulandı. Oturumsuz takip sayfası üye girişini zorunlu tuttu; ana sayfa giriş ekranına yönlendi. Bu tarayıcıda açık üye/admin oturumu olmadığı için gerçek hesapla yorum gönderme veya yönetici onayı yapılmadı.
- Yayın öncesi genel paket karşılaştırması: 45 başarısız sonuç/35 kimlik; önceki 44/34’e ek yalnızca `tests/expert_social/test_mobile_social_polish.py::test_upload_previews_scroll_sideways_and_keep_reorder_controls[390]` vardı. Dört görsel önizlemesinin 20 saniyelik test sınırında üçü tamamlanmıştı; aynı test tam Expert Social Chromium koşusunda geçti. Testi yeşile çevirmek için üretim davranışı veya test süresi değiştirilmedi. Akademik/semantik başarısızlık kimlikleri öncekiyle aynı.
- Kullanıcının LiteraDent görsellerinden hareketle istediği genel uzman keşfet alanı bu yayına eklenmedi; ayrı ürün önerisidir. Mevcut takip akışı ve uzman paylaşımları altyapısı yeniden kullanılabilir.
