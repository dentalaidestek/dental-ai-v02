# Dental Akış

Kullanıcı 9 Kasım 2026'da önerilen Dental Akış adını, Keşfet/Takip Ettiklerim sekmelerini ve uzman paylaşımlarını ortak alanda görme fikrini onayladı.

- Yeni üye sayfası `/dental-akis`; Keşfet tüm yayınlanmış ve halen doğrulanmış/aktif uzmanlara ait gönderileri, Takip Ettiklerim mevcut takip ilişkilerinin gönderilerini gösterir. Eski takip adresi çalışmaya devam eder.
- Branş filtreleri iki sekmede de korunur. Ana sayfa ve menüden erişilir; ana sayfa sosyal akışı arka planda yüklemez.
- Mevcut gönderi/medya görüntüleyici, yorum, yanıt, beğeni ve admin onayı kullanılır. Bekleyen/reddedilen içerik sahibi tarafından bile genel akışta gösterilmez; çift yönlü engelleme korunur.
- Son gönderiler kimlik sırasıyla, varsayılan 15/en fazla 30 kayıtta sayfalanır. Keşfet sıralaması için yeni AI veya popülerlik servisi yoktur. Yalnızca branş filtresi; makale arama/anket/kredi sistemi bu talepten türetilmez.
- Kartlar uzman profiline, takip eylemine ve uygun olduğunda mevcut destek talebine bağlanır. Kendi gönderisini akışta gören uzman mevcut profil yönetimine gider; eksik editör açılmaz.
- API sorguları gönderi başına büyümez. Takip/uygunluk bilgisi aynı sayfanın uzmanları için topluca alınır. Yeni tablo/sağlayıcı/ücretli servis gerekmez.
- Mobil 360/390/430 ve masaüstü 1280 px, boş/yükleniyor/hata durumları, geri gezinme ve mevcut yorum taslakları kontrol edilir.

Seçilen yaklaşım mevcut takip beslemesi ve sosyal kartı genişletmektir. Ayrı paylaşım sistemi veri ve denetim kopyalayacağı için; iframe/harici ağ ise hesap ve veri bütünlüğünü bozacağı için uygun değildir. İlk teslim ayrı PR'dır; yeni dağıtım bu kodun doğrulamasından sonra ele alınır.
