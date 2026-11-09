# Dental Akış — Keşfet ve Takip Ettiklerim

Uzmanların mevcut onaylı paylaşımları `/dental-akis` sayfasında toplanır. Keşfet tüm uygun uzmanların, Takip Ettiklerim yalnızca üyenin izlediği uzmanların gönderilerini gösterir. Sekmeler ve sekmeler arasında korunan branş filtreleri ana sayfa, menü ve Tüm Özellikler bağlantılarından açılır.

Yeni paylaşım sistemi kurulmadı: mevcut gönderi, medya görüntüleyici, yorum/yanıt, emoji, beğeni, bildirim ve admin onayı kullanılır. Bekleyen/reddedilen/silinmiş içerikler sahibinin keşfet sayfasında da gösterilmez. Aktif/doğrulanmış uzman ve çift yönlü engelleme denetimleri her istekte uygulanır.

Kartlarda branş, takip düğmesi, uzman profili ve uygunluk varsa mevcut destek talebine bağlantı vardır. Destek uygunluğu kapasite ve geçici uzman kısıtlamalarıyla topluca hesaplanır; talep oluşturma ayrıca mevcut sunucu denetimine tabidir. Takip durumu aynı uzmanın bütün görünen kartlarında güncellenir; gecikmiş sayfa sonucu daha yeni takip tercihini geri alamaz. Kendi gönderisini yöneten uzman mevcut profil editörüne yönlenir.

API kimlik cursor'uyla son gönderilerden başlar; varsayılan 15, en fazla 30 gönderi. Konum silinince sayfalama çalışmaya devam eder. İlk sayfada tüm geçmişi sayan sorgu yoktur; metadata sorguları gönderi başına büyümez. Mevcut `/feed/following` API'sinin varsayılan cevap yapısı korunur; yeni sayfa için `details=true` ek alanlar getirir. Eski takip sayfası adresi Dental Akış'ın takip sekmesini açar. Ana sayfada besleme yüklenmez.

Yeni tablo, migration, AI çağrısı, arama sağlayıcısı veya ücretli servis eklenmedi. Kullanıcının örnek görsellerindeki anket/kredi/literatür odası özellikleri bu kapsamda değildir.

## Doğrulama

- İlk hedefli API/gerçek yerel PostgreSQL ve mevcut ilişki regresyonu: **41 geçti, 1 tarayıcı testi bu koşudan hariç bırakıldı**.
- Yeni Chromium senaryoları: 360/390/430/1280 px akış, filtre/sekme, takip durumunun kalıcılığı, destek/profil bağlantıları, mevcut yorum gönderimi, kendi gönderisini yönetme, hata sonrası yeniden yükleme ve gecikmiş sayfa.
- Bu ortamda Chromium başlatma denemesi AF_UNIX socket izin hatası nedeniyle uygulama açılmadan durdu. Gerçek tarayıcı doğrulaması PR'ın mevcut GitHub Expert Social iş akışında yapılır; yerel görüntü doğrulandı iddiası yoktur.
- Nihai tam regresyon, inceleme ve ekran kanıtı teslim kaydına eklenir. PR #254 sürümündeki bağımsız akademik/genel test başarısızlıklarının bu özellikte düzeltildiği iddia edilmez.

Çalışma ayrı PR olarak hazırlanır. Bu özellik için main birleştirmesi veya canlı dağıtım yapılmadı.
