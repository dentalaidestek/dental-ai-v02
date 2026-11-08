# 8 Kasım 2026 — mobil profil ve sesli muayene

## Canlıda gözlenenler

- Yeni, kimliksiz ve yalnız sentetik verili muayene kaydı açıldı. Claude çıkarımı çalıştı. İlk kaynak araştırması başarısız oldu; metin korundu ve kayıt engellendi. Kullanıcının ekrandaki yeniden deneme işlemiyle iki kaynaklı değerlendirme tamamlandı.
- Alan seçmeden kayıt reddedildi. Şikâyet seçilip tek “Onayla ve kaydet” işlemiyle kayıt oluştu ve hasta dosyasına dönüldü. Sonuç hasta sayfasında kalıcı olarak görüldü.
- PubMed bağlantı kartı, Türkçe/emoji/satır sonları ve yenileme sonrası taslak koruma çalıştı. Aynı sayfada fotoğraf açma, yakınlaştırma ve geri tuşuyla kapatma çalıştı.
- Canlı DOI sorgusu başlık/yazar/yıl/dergi alanlarını doldurdu; bu kayıt kullanıcının yayını olarak kaydedilmedi. Hatalı ORCID kontrol hanesi reddedildi. Aziz Sancar'ın yayınları gerçek kullanıcının profiline aktarılmadı.
- “Klinikteyiz” gönderisi görsel mahremiyet politikası nedeniyle yönetici incelemesi bekliyor. Bu, kendiliğinden tamamlanacak bir AI işi değildir. Yönetici oturumu olmadığı için gerçek içerik hakkında karar verilmedi.

## Kök nedenler ve değişiklikler

| Sorun | Neden ve düzeltme |
| --- | --- |
| Takipçi sayaçları lacivert buton gibi | İstatistikler sosyal bileşen dışında kaldığı için genel `!important` buton stili kazanıyordu. Yalnız bu alana kapsamlı bir stil sıfırlaması uygulandı. |
| Profil, oluşturucu ve gönderi arasında aşırı boşluk | Tekrarlı açıklama, geniş başlatıcı ve paragraf/kart boşlukları birikiyordu. Başlatıcı tek satıra indirildi; aralıklar ve durum satırları sıkıştırıldı. |
| Yayımlanan gönderi ayırt edilemiyor | Durum etiketi yalnız incelemedeki gönderide vardı. Yayımlanan kartta küçük “Yayında”, sabit kartta “Sabit” gösteriliyor. |
| Yorum kapatılınca açık panel kalıyor | Kart değişirken üst katmandaki diyalog kapanmıyordu. Kapatma, ilgili paneli kaldırır ve yorum eylemini gizler; yeniden açma taslağı ve mevcut yorumları korur. Sunucu denetimleri sürer. |
| Çoklu fotoğraflar ızgara | Gönderi ve yükleme önizlemesi doğal yatay kaydırmalı galeriye çevrildi; konum sayacı, sıralama/kaldırma ve aynı sayfada büyütme korundu. Görseller esnetilmez/kesilmez. |
| Geçersiz bağlantı kartı kalıyor | İstemci HTTP hatasının durumunu kaybedip her hatayı önizleme eksikliği sanıyordu. Geçersiz/yetkisiz bağlantı taslaktan çıkarılır. Geçici bağlantı hatasında taslak korunur; geçerli URL'nin metadata hatası paylaşımı engellemez. |
| “Haftaya pazartesi” tarihi boş | Yerel tarih çözücüsü `hafta` içeren her ifadeyi reddediyordu. İstanbul takvimine göre gelecek hafta ve karşılıklı kabul çözülüyor. “11.00 gibi” yaklaşık saat olarak doldurulur, otomatik onaylanmaz. |
| Randevu saati düzeltilince kayıt kapanıyor | Takvim formu klinik değerlendirme imzasına dahildi. Takvim düzeltmesi klinik AI çağrısını tekrarlamaz; sunucu tarih ve çakışma kontrolünü yine yapar. Klinik metin değişikliği yeniden değerlendirme gerektirir. |
| Kayıt sonucu belirsiz | Hata mesajı butondan uzaktaydı, başarılı istekten sonra buton kısa süre yeniden açılıyordu. Buton yanında tek görünür durum/hata, yerel seçim kontrolü, gönderimde kilit ve başarıdan sonra “Kaydedildi” eklendi. |
| Kaydedilen sesli muayene “Yarım kaldı” | Genel analiz kartı `DRAFT` kaydını görüntü analizi gibi yorumluyordu. Sahibe ait tamamlanmış `VOICE_REVIEW` denetim kaydı tek sorguyla bulunur; satır ve ayrıntı “Sesli muayene / Kaydedildi” gösterir. Veritabanı klinik durumları değişmez. |
| Kaynak hatasının nedeni görünmüyor | Genel hata yakalama ayrıntıyı kaybediyordu. Yalnız sabit aşama/kategori, durum ve boyut/sayı alanları loglanır. Hasta metni, URL, anahtar, ham sağlayıcı yanıtı loglanmaz. İlk aralıklı hatanın nedeni henüz kanıtlanmadı. |

Önbellek sürümleri bütün sosyal ekranlarda `20261108-2`, sesli muayenede CSS15/JS32 olarak birlikte güncellendi. Yeni bağımlılık, ücretli servis, tablo veya migration eklenmedi.

## Doğrulama

- 717 sesli muayene, uzman kimliği ve danışmanlık Python testi geçti.
- 11 Node tarayıcı/DOM davranış testi geçti.
- Mobil sosyal görünüm ve bağlantı hataları: 26 test geçti; 360/390/430/1280 px.
- Sesli muayene kayıt akışı, takvim düzeltmesi, hata/başarı ve hasta geçmişi: ilgili tarayıcı/HTML testleri geçti. Yaklaşık randevunun onaysız olarak doldurulması ayrıca test edildi.
- Randevu çözümleme, klinik alanlar ve son değerlendirme: 153 test geçti (717 testin alt kümesi).
- İlk geniş sosyal taramada iki eski beklenti yeni “Yayında” etiketi ve önbellek sürümüyle uyuşmadı; beklentiler güncellendi. Masaüstü yorum testi bir kez başarısız oldu, ayrı tekrarda geçti; kalıcı kök neden üretilemedi. Son sürüm taraması aşağıda yer alır.
- Son sosyal tarama, izole PostgreSQL ve Chromium ile: **241 geçti, 5 isteğe bağlı test atlandı**, 184,84 saniye. Son sesli kayıt mobil taraması: **4 geçti**; takvim düzeltmesinde tekrar AI çağrısı yok, hata/başarı ve yaklaşık saatin onaysız öneri olması doğrulandı.
- Kod incelemesinde doğrulanmış P0/P1/P2 hata bulunmadı.

Sentetik ekran örnekleri:

- [Profil ve gönderi](social-completion/mobile-polish-profile-390.png)
- [Yana kaydırılmış ikinci görsel](social-completion/mobile-polish-gallery-390.png)
- [Yorum paneli](social-completion/mobile-polish-comments-open-390.png)
- [Çoklu fotoğraf oluşturucu](social-completion/mobile-polish-composer-390.png)
- [Kayıt hatası](social-completion/voice-save-feedback-360.png)
- [Başarılı kayıt](social-completion/voice-saved-360.png)

## Sınırlar

Bu çalışma 60.000 eşzamanlı kullanıcı kapasitesi veya hukuki uygunluk garantisi değildir. Gerçek telefon mikrofonu ve klavyesiyle test, iki ayrı canlı test hesabıyla takip/yorum/destek işlemleri ve yönetici kararı bu rapordaki masaüstü/mobil emülasyon testlerinden ayrıdır. Yönetici giriş isteği zaman aşımına uğradı; doğrulanmış yönetici oturumu elde edilmedi. Mevcut hastalar, yayınlar ve gönderiler değiştirilmedi. Yalnız sentetik yeni muayene kaydı oluşturuldu.

## Canlı dağıtım sonucu

- PR: https://github.com/dentalaidestek/dental-ai-v02/pull/252 — birleştirildi.
- Çalışan kod: `a874e9cf20fe7fe1c5815ae61e66c28c3dd4b4bb`.
- Render dağıtımı: `dep-dbo5r8ss728c739qrj40`, **8 Kasım 2026 14:33:53 Türkiye saati** itibarıyla `live`.
- `/healthz` ve `/readyz`: 200. Girişsiz takip akışı, gönderi, özel görsel ve sesli muayene yetenek uçları: 401.
- Canlı sosyal JS/CSS ile sesli muayene JS/CSS dosyalarının dördü de test edilen yerel dosyalarla SHA256 düzeyinde eşleşti.
- Yeni örneğin uygulama başlangıcı tamamlandı; bu dağıtım için sorgulanan kısa gözlem aralığında hata seviyesinde log bulunmadı.
- Yeni tarayıcı oturumu giriş ekranında. Yeni sürümün oturum gerektiren canlı senaryoları için kimlik doğrulama gerekiyor; bunlar yerel/CI testleriyle karıştırılmadı.

GitHub sosyal iş akışı **485 geçti / 5 atlandı**. Sesli muayene, yönetici güvenliği, güvenlik kurtarma ve Android kontrolleri başarılı. Akademik kontrolün 30 başarısız test kimliği ve PostgreSQL kontrolünün 2 başarısız kimliği önceki sürümle aynı. Genel uygulama taraması 44 başarısız / 2382 başarılı / 66 atlandı; başarısız test kimliklerinin tamamı önceki sürümde de var (önceki tarama 45 başarısız). Bu eski hatalar bu mobil düzeltmeyle giderilmiş sayılmaz.

Bu raporun sonradan güncellenmesi yalnız dokümantasyondur; `[skip render]` ile çalışan kodun gereksiz yeniden dağıtımı önlenir.
