# Sesli muayene kabul kontrolü — 7 Kasım 2026

## Amaç

Muayene sırasında yalnız metin toplamak; bitişte çıkarım, kapalı konu kimlikleriyle kaynak araştırması ve son değerlendirme yapmak. Sonuç okunabilir olmalı, aynı bilgi beş kartta tekrarlanmamalı, taslak hata/yenilemede korunmalı; hasta kaydı ancak seçim ve hekim onayıyla oluşmalı.

## Bu değişiklik

- Sonuç ekranı: Görüşme özeti, Dikkat edilecekler, Hastayla iletişim, Tamamlanacak bilgiler, Kaynaklar ve inceleme kapsamı. Anamnezde yalnız dökümde netleşmeyen başlıklar gösterilir; eksiksizlik/sağlık puanı verilmez.
- Materyal eksikliği ayrı bir kartta tekrar edilmez; klinik kontrol bölümünde görünür. Birebir hasta/kaynak alıntısı açılır ayrıntıdadır. Kaynak kapsamı cümleleri ana sonucu doldurmaz. Aynı sorunun birebir kopyası ve aynı iletişim tereddüdü tek maddede gösterilir. Ayrı hekim iddialarının farklı dayanakları korunur.
- Provider veri aracı subject etiketleri kişi kapsamını açık adlandırır: THIS_PATIENT/PATIENT_RELATIVE/OTHER_PERSON/UNCLEAR_PERSON. Konuşan hekim olması, hastaya ilişkin planı hekim öyküsü yapmaz. Eski etiketler normalize katmanında uyumlu okunur; OTHER/UNKNOWN güvenlik sınırları gevşetilmez.
- Atomik sağlık öyküsü ve plan alanlarında modelin yeniden yazdığı değer yerine gerçek alıntı korunur. Böylece yalnız diyabet tanısını reddeden sözden genel hastalık yokluğu veya plan cümlesinden yapılmış işlem üretilmez. Gerçek çıkarım yolunda beklenmeyen eski klinik özet alanları bu korumayı aşamaz.
- Genel kaplama ve zirkonya üstü veneering/veneered ifadesi laminate veneer olarak yönlendirilmez. Bu dar kontrol bütün materyal endikasyonlarının doğrulandığı anlamına gelmez.
- Kamusal araştırmaya NICE NG12 ağız lezyonu başlangıç kaynağı eklendi. Yalnız kapalı konu kimlikleri gider; hasta alıntısı bu araştırmaya gönderilmez. NICE eşikleri UK rehberidir; Türkiye sevk kuralı veya kesin tanı sayılmaz. Kaynak getirilmeden kaynaklı öneri üretilmez.
- Kaynak araştırması uzun klinik anlatım yerine kısa atıf ve eksik kapsam döndürmeye yönlendirilir. Sağlayıcı/model bağlantısı ve ücretli aşama sayısı değiştirilmedi.
- Aynı sekmede yenileme kurtarması: oturumluk tarayıcı alanında en fazla 1 MB, kullanıcı/hasta kapsamı ve son klinik değişiklikten 30 dakika geri yükleme sınırı. Başka kullanıcı/hasta açılınca önceki kapsam kaldırılır. Mikrofon, rıza, kayıt seçimleri ve hekim onayı geri yüklenmez. Tamamlanan çıkarım kontrol noktaları ve son çıktı korunabilir; sırf yenileme yeni model çağrısı yapmaz. Taslak temizleme/kayıt/sekme kapanışı kurtarmayı sonlandırır. Tarayıcı depolamayı engellerse uyarılır. Bu, sunucuda konuşma kaydı veya cihazlar arası yedek değildir.
- BFCache geri dönüşünde sunucu erişim/aidiyet kontrolü için sayfa yeniden yüklenir; ikinci pagehide saklanan taslağı silmez. Eski uzun metin kısaltılırsa eski parça imleci sıfırlanır; yeni metin silinmez. Geçerli 24 konu desteklenir; 13–24 konu yüzünden taslak atılmaz. Sayfa kapanışı süreyi yenileyip eski metni diriltmez.

## Kanıt ve yayın

Yeni DOM ve Python regresyonları önce ilgili hatada RED görüldü, düzeltme sonrası GREEN. Son tam yerel kod koşusu: **629 Python geçti**, iki mevcut bağımlılık uyarısı. Son Node koşusu: **11 geçti**. Bağımsız inceleme 232 odaklı Python ve entegre DOM testinde engel kalmadığını bildirdi. Son metin katlama değişikliğinde entegre DOM tekrar geçti. Canlı yayın ve yeni gerçek model tekrarı henüz yapılmış sayılmaz; sonuçları aşağıya eklenecek.

Render teşhisi: ana site srv-daeb9d740ujc73ei7gmg 5196f44 sürümü live. Görüntü servisi srv-dai8bj6k1f9s73cokbjg önceki ed0cf82 dağıtımında port taraması zaman aşımı/update_failed yaşadı; ardından aynı serviste 5196f44 dağıtımı live oldu. Port açılmasını geciktiren daha alt neden kanıtlanmadı; sesli kodu değiştirerek düzeltilmiş gibi sunulmaz. İki servis ayrı izlenir.

## Kabul matrisi

| İstek | Durum ve sınır |
|---|---|
| Dinleme sırasında yalnız metin | Önceki uygulama korunuyor; Node gerçek panel/iki denetleyici testi |
| Bitirince tek çıkarım akışı ve son kontrol | Parçalı metin kontrol noktaları, çift tıklama ve bekleyen aktarım testli |
| Kapalı kaynak konuları, gizlilik | Kimlik doğrulama ve araştırmaya yalnız kamusal konu/ad geçmesi Python testli |
| Hata/yeniden deneme, başarılı aşamayı koruma | Kontrol noktaları ve kaynak parmak izi testli; final başarısızsa metin korunuyor |
| Yenilemede taslak | Yeni aynı-sekme kurtarma testli; depolama engeli ve başka cihaz kısıtı mevcut |
| Anamnez ve aile/kişisel öykü | 7 alan grubu, kişi atfı ve dar negatif kapsam korumaları var; gerçek model yeni sürümde sınanacak |
| Günlük dil, tüm diş hekimliği dalları | Kapalı 92 konu/15 dal ve doğal diyalog fikstürleri var; her klinik durumun doğru yorumlandığı kanıtlanmadı |
| Materyal/işlem uygunluğu | Konuşulan ad, işlem bağlamı, kaynak kapsamı ve belirsizlik gösteriliyor; tüm marka/ürün IFU veritabanı tamamlanmadı |
| Hekim iddiaları ve iletişim | Ayrı geçici kaynak kontrolü; doğru/yanlış ile doğrulanmadı ayrımı korunuyor; yeni gerçek model kalitesi sınanacak |
| Hasta kaydı | Açık seçim/onay, revizyon ve idempotency testli; bu oturumda hasta kaydı yapılmadı |
| Mobil görünüm ve başlık açılışı | DOM kontrolü var; fiziksel Android ölçümü yapılmadı |
| Gerçek mikrofon/gürültülü klinik | Tamamlanmadı; sentetik metin ve DOM testi yerine geçirilmez |
| Klinik doğruluk/altın set | Hekim onaylı yanlış alarm/kaçırma ölçümü tamamlanmadı |
| Genel CI | Önceki akademik/PostgreSQL hataları açık; sesli değişiklikte gizlenmez |

## Kaynaklar

- [NICE NG12, oral cancer bölümü](https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer)
- [Önceki sekiz canlı vaka ve eksikler](voice_live_campaign_2026-11-06.md)

## Canlı doğrulama

Yayın sonrasında eklenecek. Genel uygulama geliştirmesine paralel ilerlemek mümkün olsa da klinik kullanıma hazır veya bütün diş hekimliği durumları eksiksiz doğrulanmış denmez.
