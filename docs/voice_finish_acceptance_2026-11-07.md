# Sesli muayene kabul kontrolü — 7 Kasım 2026

> Güncel durum: PR248 iki serviste canlı. Son yerel koşu 640 Python / 11 Node geçti. Gerçek Chrome metin/sonuç kurtarma ve iki sentetik metin vakası doğrulandı. Klinik doğruluk, gerçek mikrofon ve bütün materyal endikasyonları tamamlandı denmez.

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

Yeni DOM ve Python regresyonları önce ilgili hatada RED görüldü, düzeltme sonrası GREEN. PR247 öncesi tam yerel koşu: **629 Python geçti**, iki mevcut bağımlılık uyarısı. Son Node koşusu: **11 geçti**. Bağımsız inceleme 232 odaklı Python ve entegre DOM testinde engel kalmadığını bildirdi. Son metin katlama değişikliğinde entegre DOM tekrar geçti. Bu paragraf PR247 öncesi kayıttır; sonraki yayın ve canlı sonuçlar aşağıdadır.

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

Aşağıdaki yayın ve vaka kayıtları uygulanır. Klinik kullanıma hazır veya bütün diş hekimliği durumları eksiksiz doğrulanmış denmez.

## Yayın kaydı

PR247 birleştirildi: d9e303616e379fbe25ffd19c75a1cee26be6547f. Ana site dağıtımı dep-dbne44p42hec73cbick0, görüntü servisi dağıtımı dep-dbne44p42hec73cbicgg ayrı izleniyor. Bu satırın yazıldığı anda ana site update_in_progress; canlı sonucu ayrıca eklenecek.

PR247 uzak kontroller: voice, contract-tests, ready-model-contract ve CodeRabbit başarılı. İş logları incelendi: static-safety40başarısız/966başarılı/34atlanan/566alt-test; application-regressions43başarısız/2092başarılı/48atlanan/594alt-test; PostgreSQL2başarısız/42başarılı. Akademik dışındaki3başarısızlık da çalışma alanı akışına ait: test_production_optimization.py::test_study_generation_releases_db_connection_and_rechecks_course[False/True] ve test_study_index_v2_isolation.py::test_v2_streaming_is_feature_gated_end_to_end. Genel CI yeşil değildir.

## PR247 canlı sonucu ve takip düzeltmesi

Ana site d9e303616e379fbe25ffd19c75a1cee26be6547f **7 Kasım11:33:54 Türkiye** live; görüntü servisi aynı SHA ile **11:37:51** live. Güncel iki dağıtım da başarılıdır; eski port zaman aşımı kaydı yeni dağıtım hatası diye sunulmaz.

Gerçek tarayıcıda işlenmemiş1482karakterlik sentetik kron metni normal yenilemede1482olarak döndü; rıza/onay sıfır. Gerçek modelde kron ve protez planları artık korundu (4/4 ve3/3dayanaklı hasta planı). Kron genel prosth.fixed seçti, yanlış veneer görünmedi.3kaynak/0kabul edilmiş kontrolle kısmi sonuç verdi; özgül klinik kontrol başarılı sayılmaz. Aynı tamamlanmış sonucu normal yenilemede yeni text/finalize olmadan geri getirdi, seçimler0 ve onay/rıza false kaldı.

Daha ileri gerçek tarayıcı geçmiş denemesinde /voice-exams→Back sonrası kartlar korunurken metin0oldu. Native tarayıcı form restorasyonunun başlangıçtaki değerleri ezmesiyle uyumlu bir bulgu; aynı durum DOM yaşam döngüsünde tekrarlandı. v28takip düzeltmesi kurtarma verisini load/pageshow sonrasındaki görevde yeniden uygular, o zamana kadar önbellek yazısını ve kontrolleri bekletir. Geçerli taslak olmasa da yerel tarayıcıdan geri gelen rıza/onay/seçimler sıfırlanır. Normal/eksik/süresi dolmuş/bozuk önbellek ve native form simülasyonları RED→GREEN; gerçek tarayıcıda v28tekrarı henüz yapılmış sayılmaz.

Protez finali provider aşamasında Incomplete clinical review ile durdu; ham model içeriği loglanmadığından gerçek stop nedeni henüz bilinmiyor. Takip değişikliği yalnız izinli stop etiketi ve tamsayı çıktı token sayısını loglar; hasta/provider metni loglanmaz. Yanıt sınırı veya sağlayıcı henüz değiştirilmedi, otomatik ücretli tekrar eklenmedi.

Canlıda birleşik ilaç/alerji yokluğu medical_history içine düşmüştü. Yeni dar yönlendirme yalnız THIS_PATIENT/PATIENT, NEGATED, bütün alıntısı kesintisiz dayanaklı ve tamamı tanınan1–2ilaç/alerji yokluğu cümlesinden oluşan ifadeyi kendi alanlarına ayırır. Belirsiz/geçmiş/başkasına ait veya karışık tıbbi ifade değiştirilmez. İki konuşmacıdan alıntı birleştiren karşı örnek RED→GREEN. Alerji atomik değeri de literal tutulur; bilinmeyen ilaçtan spesifik penisilin alerjisi üretilmez. Açık Hasta etiketli şikâyet muayene bulgusu yerine başvuru yakınmasında tutulur; etiket yoksa konuşmacı uydurulmaz.

Takip kodu: **640 Python/11 Node geçti**, iki mevcut bağımlılık uyarısı. İkinci takip yayın ve canlı tekrar henüz yapılmış sayılmaz. Mevcut iki vaka sentetik METİN üzerinden gerçek provider denemesidir; mikrofon/gürültü/klinik altın set değildir. Hasta kaydı yapılmadı.


## PR248 yayın ve v28 gerçek tarayıcı tekrarı

PR248, `981d27422b7f61e6805653f483e51e5af898f3ab` olarak birleştirildi. Ana site `dep-dbnefnu8bjmc73a5hurg` dağıtımı **7 Kasım 11:58:28 Türkiye** live oldu. Uzak voice, contract-tests ve ready-model-contract başarılı; CodeRabbit neutral. Yerel son tam doğrulama **640 Python / 11 Node**, sıfır başarısızlık, iki bağımlılık uyarısı. Bağımsız inceleme 112 odaklı Python ve entegre DOM testinde engel bulmadı. Genel CI yeşil değildir.

Gerçek Chrome'da v28 scripti görüldü. Yeni, işlenmemiş 1.482 karakterlik kron diyaloğu ile sesli başlangıç sayfasına gidip Back dönüşü yapıldı: **1.482 karakter aynen geri geldi**, rıza ve kayıt onayı false kaldı. Önceki v27 Back hatası bu tekrarda oluşmadı. Bu sentetik metin üzerinden tarayıcı testidir; fiziksel Android/mikrofon testi değildir.

Protez taslağı v28 yenilemesinde **1.516 karakter ve 5 alan** ile döndü, rıza/onay false. Başarılı çıkarımı yinelemeden yalnız final tekrarlandı: `stop=end_turn output_tokens=3881`, **3 kaynak / 2 kabul edilmiş kontrol**, `/finalize` 200. Bu tekrar aralığında yeni `/text` veya çıkarım çağrısı görülmedi. NICE NG12 kalıcı ağız ülserasyonu ve ADA protez uyumu kaynakları getirildi. Kesin tanı konmadı, yara yalnız protez vuruğu kabul edilmedi, hasta kaydı yazılmadı. Önceki eksik yanıtın gerçek stop nedeni geriye dönük kanıtlanamadı; tek başarılı tekrar tutarlılık/klinik doğruluk garantisi değildir.

Bu protez tekrarı eski çıkarım kontrol noktasını kullandığı için eski birleşik ilaç/alerji alanını yeniden yazmadı. Yeni kron çıkarımında ilaç yokluğu ve alerji yokluğu doğru ayrı alanlarda, hastanın yüksek kapanış şikâyeti de muayene bulgusu yerine başvuru şikâyetinde görüldü.

Görüntü servisi `dep-dbnefnu8bjmc73a5huo0`, aynı SHA ile **12:02:48 Türkiye** live oldu. İki servis de son kodu çalıştırıyor.

Yeni kron finali: `end_turn`, 4.188 output token, **2 kaynak / 1 kabul edilmiş kontrol**, kaynak eksiği nedeniyle kısmi sonuç. AAE çatlak diş kaynağı koşullu olarak kullanıldı; kesin çatlak tanısı üretilmedi. Genel kaplama laminate veneer yapılmadı. İşlenmiş sonuçla da başlangıç sayfası → Back yapıldı: **1.482 karakter + 6 kart korundu**, rıza/onay false, seçili alan 0. Yeni text/finalize çağrısı görülmedi. Geri dönüş bekleme aracında bir protokol zaman aşımı oluştu; sonraki doğrudan DOM gözlemi bu başarılı durumu doğruladı; site hatası diye sınıflandırılmadı.

### Açık kalite eksikleri

- Kron sonucunda ilgisiz randevu netleştirmesi ve muayene öncesinde yanıtlanmış ayrıntılara yakın sorular hâlâ üretildi.
- Protez iletişim bölümünde aynı korkunun farklı alıntılardan iki öneriye dönüşmesi hâlâ mümkün. Birebir kopya temizliği anlamsal tekrarın tamamen çözümü değildir.
- Yeni kron çıkarımında dört gün önceki kaplama bilgisi materyal alanına da düştü; eski dental_history ile aynı sınıflandırma kararlılığı sağlanmadı. Klinik dayanak kaybolmadı, fakat alan kalitesi eksiksiz değil.
- Protez tekrarının başarılı olması eski final hatasının nedenini veya beş tekrar tutarlılığını kanıtlamaz.
- Materyal üretici IFU kapsamı, hekim onaylı altın set, gerçek mikrofon/gürültü ve fiziksel Android kabulü açık. Bu nedenle bütün istekler klinik açıdan tamamlandı veya sistem güvenlik onayı verir denmez.

Kanıtlar: [protez DOM sonucu](voice_v28_denture_final_2026-11-07.json), [kron DOM sonucu](voice_v28_crown_final_2026-11-07.json), [canlı sonuç ekranı](voice_v28_denture_proof_2026-11-07.png). Hasta kaydı yazılmadı.
