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
- Geniş yerel pakette **480 geçti, 4 atlandı**. Ayrı ilişki koşusuyla örtüşmeyen toplam **504 geçti, 4 atlandı**; hedefli 41 test bu sayılara dahildir. Eski yorum taslakları için iki JSDOM senaryosu da geçti. Gerçek `expert-social.js` ile ek üç JSDOM kontrolü geçti: gecikmiş sayfada takip tercihi korunması, takipten çıkınca bütün kartların kaldırılması ve başarısız yüklemeden sonra çalışan yeniden deneme. Bunlar tarayıcı yerleşim testi yerine geçmez. PR #254 sürümündeki bağımsız akademik/genel test başarısızlıklarının bu özellikte düzeltildiği iddia edilmez.

## PR ve tarayıcı doğrulama engeli

[PR #255](https://github.com/dentalaidestek/dental-ai-v02/pull/255), kaynak commit `be4815326d00d88217a5c52e46d32fe66365f66c`.

GitHub Expert Social koşusu `42671476759` test işi oluşturmadan başarısız sona erdi (`jobs: []`). Aynı commit'in diğer üç iş akışında da test işi yok. Yeniden çalıştırma API'si 403 `This workflow run cannot be retried` döndürdü. Sağlayıcı yanıtında kesin neden yoktur; kota veya uygulama hatası olduğu varsayılmadı. Bu nedenle Chromium senaryoları ve 360/390/430/1280 px ekran görüntüleri doğrulanamadı. GitHub koşusu geçmiş sayılmaz. Kod bağımsız incelemede önemli açık bulgu vermedi.

PR tarayıcı doğrulaması bekleyen taslak olarak tutuldu. Bu özellik için main birleştirmesi veya canlı dağıtım yapılmadı.
