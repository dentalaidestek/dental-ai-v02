# Uzman gönderilerinde beğenme ve yayın paylaşımı — 8 Kasım 2026

## Tespit edilen nedenler ve düzeltmeler

| Sorun | Neden | Son davranış |
| --- | --- | --- |
| Beğenme anlaşılmıyor | İstek ve sayaç kaydı çalışıyordu; harici SVG dosyası IMG olarak çizildiği için seçili kalp dolmuyordu. Erişilebilir etiket değişmiyordu. | Kalp aynı isteğin sonucunda dolar, sayaç güncellenir, etiket “Beğenmekten vazgeç” olur. Yenilemede durum korunur. Tek seferde bir istek gönderilir. |
| Beğenme hatası görünmüyor | Hata, uzun profilin üstündeki mesaj alanına yazılıyordu. | Hata ilgili gönderinin etkileşim satırında görünür. Başarısız istek sayacı veya beğenme durumunu değiştirmez. |
| ORCID yayını iki kez yazılıyor | Başlık ve URL açıklama alanına otomatik kopyalanıyor, aynı bilgi yayın kartında tekrar ediyordu. | Açıklama alanı boş ve isteğe bağlıdır; yayın tek bağlantı kartıdır. Eski otomatik başlık+URL paylaşımları da kaydedilen metin silinmeden bir kez gösterilir. Uzmanın kendi açıklaması korunur. |
| Kapak iki kez görünüyor | Kapak hem fotoğraf karuseline hem bağlantı kartına ekleniyordu. | Kapak yalnızca kartta gösterilir; değiştirme/kaldırma ve yükleme durumu ayrı, küçük kontrollerdir. Normal fotoğraflar yatay karuselde kalır. |
| Paylaşım sonucu belirsiz | Sonuç mesajı ekranın üstünde kalıyor, yönetim ekranındaki yayın listesi yeni gönderiyi aşağı itiyordu. | Yeni gönderiye kaydırılır. Görünür mesaj “Yayımlandı / İncelemeye alındı / Yayımlanmadı” sonucunu ve “Gönderiye git” düğmesini gösterir. Hata açıklama ve medyayı korur. |
| Temizlenen taslak geri dolabiliyor | Önceki metin için bekleyen bağlantı önizleme zamanlayıcısı ve yanıtı iptal edilmiyordu. | Taslak temizleme/değiştirme önceki istekleri geçersiz kılar; hazırlık kaldırıldığında Paylaş düğmesi yeniden kullanılabilir. |

## Kapsam

- Uygulama: `app/static/expert-social.js`, `app/static/expert-social.css`.
- Paylaşılan şablon ve önbellek sürümü: `_expert_social.html`, `expert_public_profile.html`, `expert_profile_edit.html`, `expert_following.html`, `admin_social.html` → `20261108-3`.
- Regresyonlar: `test_like_feedback_browser.py`, `test_publication_share_feedback_browser.py`, `test_preview_browser.py`, `test_browser.py`, `test_relationships.py`, `test_live_researcher_browser.py`.
- Veritabanı, yetki denetimi, görsel mahremiyet politikası ve danışmanlık servisleri değiştirilmedi. Yeni ücretli servis veya AI çağrısı eklenmedi.

## Doğrulama

- Yeni beğenme testleri: **7 geçti**; uzman/üye, gerçek veritabanında 0→1→0 ve yenileme, dolu kalbin görüntü pikselleri, eşzamanlı çift tıklama, gerçek 401 ve simüle 503 hatası.
- Yayın paylaşımı ilk mobil kontrolü: **12 geçti**, 360 ve 430 px, hem profil hem yönetim ekranı.
- Taslak düzeltmesinden sonraki birleşik önizleme/paylaşım/beğenme testleri: **26 geçti**.
- Aziz Sancar’ın herkese açık ORCID kaydı yerel test hesabına aktarıldı: **61 yayın**, ikinci aktarım kopya oluşturmadı; gerçek kaynak verisinden gönderi paylaşımı geçti. Bu test ORCID sahipliğini veya akademik unvanı doğrulamaz.
- Son sınır kontrolleri: **9 geçti**; yayın hazırlığını kaldırma, eski yanıtı yok sayma, eski otomatik metni sade gösterme ve takip akışında beğenme.
- Tam sosyal regresyon: **265 geçti, 5 isteğe bağlı dış servis testi atlandı**. Gerçek yerel PostgreSQL yarış/benzersizlik kontrolleri ve 360/390/430/1280 px tarayıcı senaryoları dahil. JavaScript sözdizimi ve git diff kontrolleri geçti.
- Bağımsız kod incelemesinde açık P0/P1/P2 bulgusu kalmadı.
- GitHub Expert Social CI: **509 geçti, 5 atlandı**. Mevcut sesli muayene, danışmanlık, dosya depolama ve güvenlik regresyonları da bu pakete dahildir. Security Recovery CI geçti.
- Genel CI tamamen yeşil değildir: Academic V2'de 40 başarısız sonuç (listelenen 30 test kimliği), genel uygulama paketinde 44 başarısız sonuç (listelenen 34 test kimliği), semantik PostgreSQL'de 2 başarısız test vardır. Üçünün de başarısız test kimlikleri önceki PR #252 sürümüyle birebir aynıdır; yeni başarısız test kimliği bulunmadı. Bu değişiklikte akademik AI altyapısı değiştirilmedi.

## Sürüm kaydı

- PR: https://github.com/dentalaidestek/dental-ai-v02/pull/253
- İncelenen dal: `fix/publication-share-feedback-20261108`, GitHub başı `58fddfd0fb5273382ef7bb78b9a96bbb9ea1bea0`.
- Birleştirilen uygulama commit'i: `efbdf703e096aad45ef68898e24ab77986a0280d`.
- Render dağıtımı: `dep-dboaov8473hc73adehd0`.
- Dağıtım **LIVE**: 8 Kasım 2026 17:10:21 UTC / 20:10:21 Türkiye saati.
- Canlı `/healthz` yanıtı `{"ok":true}`; oturumsuz gönderi API'si “Üye girişi gerekiyor” yanıtı verdi, uzman sayfası giriş ekranına yönlendi.
- Yeni JS/CSS sürümü: `20261108-3`.

## Görsel kanıt

Testlerdeki hasta içermeyen sentetik veriler kullanılmıştır:

- `docs/social-completion/publication-composer-profile-360.png`
- `docs/social-completion/publication-composer-manager-430.png`

Canlı tarayıcıda açık bir hesap oturumu bulunmadığı için bu değişiklikte gerçek kullanıcı hesabıyla canlı paylaşım/beğenme testi yapılamadı. Render uygulama commit'i ve canlı sağlık/erişim kontrolü doğrulandı. Tarayıcı doğrudan JavaScript dosyasına gitmeyi `ERR_BLOCKED_BY_CLIENT` ile engellediği için canlı dosyaların bayt karşılaştırması tamamlanamadı. Kapak içeren içerik güvenlik kuralı gereği incelemede kalabilir; bu durum yayın hatası olarak gösterilmez.
