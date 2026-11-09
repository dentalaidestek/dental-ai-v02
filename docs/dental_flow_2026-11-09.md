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

## Ana sayfa kartı ve açıklama düzenleme devamı

- Seçilen 4:3 sosyal medya görseli `app/static/dashboard/mobile/dental_flow.webp` olarak ana işlem kartlarına eklendi. HTML başlık **Dental Akış**; hedef `/dental-akis`. Lazy loading, width/height ve WebP kullanılır; ana sayfa besleme istemez.
- Görsel Image Gen ile üretildi; son seçilen görsel üç diş hekimi, tablette sosyal akış, avatarlar, beğeni/yorum simgeleri ve yüzen gönderi kartları içerir. İstek: mevcut beyaz/mavi klinik fotoğraf tarzı, sosyal medya kimliği açık, yazısız, son oran 4:3. Kullanıcı son görseli açıkça seçti.
- Açıklama editörü mevcut medya/bağlantıyı gösterir; üstte Kaydet, metin altında etkileşimlerin korunduğu bilgisi vardır. Hatalı kaydetme taslağı korur; bekleyen kayıt sırasında editör değiştirilemez. Çıkış ve yönetim sekmesi değişikliği kaydedilmemiş açıklama için vazgeçme onayı ister.
- Aynı gönderi güncellenir. Yorum/yanıt, gönderi ve yorum beğenileri silinmez. Güvenli açıklama düzeltmesinde onaylı görsel yeniden kuyruğa alınmaz. Değişmeyen açıklama, onay kararını ve sürümü aynen korur. Riskli açıklama ve onaylanmamış görseller için inceleme sürer.
- Yeni API regresyonu önce beklenen 2 hatayı gösterdi (onaylı görseli gereksiz incelemeye alma ve değişmeyen açıklamada kararın kaybı); düzeltmeden sonra **6 test geçti**. Gerçek şablon/JS ile medya-bağlantı görünümü, başarısız kayıt, tekrar deneme ve düzenleme korumaları geçti; bağımsız incelemenin bulduğu iki vazgeçme sorunu da düzeltildi ve yeniden doğrulandı.
- Gerçek Chromium bu devam işinde de uygulama açılmadan `socket() failed: Operation not permitted` ile durdu. Yeni 390/1280 px tarayıcı senaryoları eklendi; ekran doğrulaması yapıldı sayılmaz.

## Eşzamanlılık ve 60.000 hesap denetimi

- Önceki uygulama commit'i `f576f7216d80c61ab98661f3fcb2bfc7a95b7154`: GitHub Expert Social **607 geçti, 5 atlandı**, koşu `42675745939`. Mobil 360/390/430 ve masaüstü1280 akış, yeni ana sayfa kartı ve düzenleme/tekrar deneme dahil. 390/1280 ekran görüntüleri incelendi. Bu, aşağıdaki yeni sağlamlaştırmaların tarayıcı sonucu değildir.
- PostgreSQL'de dört bağlantılık havuzla beş eşzamanlı yazma senaryosu geçti: beş farklı uzman, tek uzmanın beş farklı gönderisi, aynı isteğin beş tekrarı (tek kayıt), farklı anahtarla aynı içeriğin tekrarı (bir kayıt + dört429), önceden yüklenmiş beş farklı görselin sahiplikle doğru gönderiye bağlanması (incelemede). Kilitlenme ve bağlantı sızıntısı görülmedi.
- Yerel sentetik ölçüm: 60.000 hesap, 1.000 uzman, 60.000'er gönderi/yorum/beğeni. 16 istemciyle profil/Keşfet/takip için100karışık okuma, dört bağlantılık havuz, **0hata**. p50 **194ms**, p95 **410ms**, **68,78istek/sn**. Sayfa başına11–12sorgu, derin cursor11sorgu; sorgu sayısı veri miktarıyla büyümedi. Ayrıntı `docs/dental-flow/capacity-60000.json`.
- Bu ölçüm yerel sosyal API+gerçek PostgreSQL içindir. Gerçek ağ/CDN, görsel baytları, R2 gecikmesi, tüm uygulama middleware'i, AI/uzun stream ve Render donanımı ölçülmedi. **60.000 eşzamanlı kullanıcı kapasitesi değildir.** Mevcut tek ücretsiz Render servisi; kodun varsayılan web havuzu4, uygulama istek kabul sınırı8, aynı anda görsel yükleme sınırı1. Karma uzun istekler503admission veya havuz beklemesi oluşturabilir. Ücretli plan veya servis ayarı değiştirilmedi.
- Bulunan ve düzeltilen noktalar: akış avatarına profil bağlantısı; yalnızca503+Retry-After durumunda en çok4otomatik yükleme tekrarı (önizleme korunur); görsel cache kapasite hatasında500yerine503+Retry-After ve dahili feed görsellerinde en çok2yeniden yükleme; hesap kapanınca sıradaki dosyaları/tekrarları durdurma; aktif branş çipinde okunaklı beyaz metin.
- Son ilgili yerel regresyon **156geçti, 1tarayıcı testi hariç**. Yeni cache503testi önce beklenen hatayı gösterdi, düzeltme sonrası geçti. Beş gerçek-JS yükleme senaryosu (başarıya tekrar,5denemede durma, başlıksız503/400tekrar etmeme, logout) ve çoklu dosyalı logout yeniden doğrulandı. Bağımsız incelemede açık önemli bulgu kalmadı. Son browser CI sonucu ayrıca kaydedilir.
- Kalan altyapı sınırları: özel medya sunucu üzerinden aktarılıyor; cold-cache R2indirmesindeki süreç geneli ayırma kilidi talepleri sıraya sokabilir. Retry dayanıklılığı sağlar, kapasiteyi artırdığı iddia edilmez. 60bin kişinin aynı anda kullanımına yönelik kapasite onayı için gerçek karma ağ/medya/stream yükü ve üretime denk donanım ölçümü gerekir.
