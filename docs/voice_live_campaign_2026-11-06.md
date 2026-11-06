# 6 Kasım 2026 canlı sesli muayene testleri — 8 vaka

## Kapsam

Kullanıcı isteği üzerine dentalai.tr arayüzünden, mevcut gerçek model sağlayıcısıyla sentetik hekim/hasta/asistan metinleri gönderildi. Konuşmalar yaklaşık90 saniyelik okuma hedefiyle hazırlanmıştır; gerçek mikrofon/ASR, insan sesi veya klinik doğruluk ölçümü değildir. Hiçbir alan seçilmedi, hekim kayıt onayı verilmedi ve hasta kaydı yapılmadı.

Runtime: PR243,66942150d6c284b924d947de591dd9913365deea; Render dep-dbmn9gm8bjmc73ds0irg 6Kasım09:35:34 Türkiye live doğrulandı.

| Vaka | Gözlenen sonuç | Açık sorun |
|---|---|---|
| Cerrahi/varfarin | Çıkarım başarılı; final iki denemede422; metin ve alanlar korundu. Loglarda ikinci text/extraction yok, yalnız finalize tekrarlandı. | Final nedenini eski loglar ayırmıyor.5 dayanaklı planın5'i OTHER işaretlenip dışlandı. İkinci denemede araştırma yeniden çağrıldı; çıkarım tekrarlanmadı. |
| Diş eti kanaması | Final kısmen hazır;3kaynak/3kabul edilmiş kontrol. Aile diyabeti ile kişisel tanı reddi doğru ayrı. | Plan yok; verilen hekim yanıtları kayboluyor ve bazı cevaplanmış konular tekrar soruluyor. İlgisiz xerostomia kaynağı da getirildi. |
| İmplantta oynama | Final kısmen hazır;2kaynak/2kontrol. Asistanın kendi kanaması hasta yakınmasına eklenmedi, anne diyabeti ayrı. |3PATIENT planı dayanaklı olmasına rağmen plan alanı yok; atıf çakışması ayrıca incelenmeli. Hekimin sökme kararı vermediği açıklaması kaybolup yeniden soru oldu. Kişisel diyabet reddi genel sistemik hastalık yokluğuna genişletilmiş. Sigaranın güncelliği zaten bildirilmişken tekrar soruluyor. |
| Endodonti/uzayan soğuk ağrısı | Final kısmen hazır;2kaynak/0kabul edilmiş kontrol.3muayene/test planı korundu; bilinmeyen çocukluk ilaç reaksiyonu belirsiz kaldı. | Eski dolgu bilgisi kayboldu. AAE/pulpit belgesi yerine ADA anestezi ve AAPD genel Overview getirildi; özgül pulpa kontrolü yok. Bazı hekim yanıtları yine kayıp. |
| Çocuk travması | Çıkarım tamam; tüm kaynaklar erişilemez olduğunda final model çağrısından önce durdu. | Klinik değerlendirme oluşmadı; taslak korundu. |
| Ortodontik tel batması | Çıkarım tamam; kaynaklara erişilemedi, taslak korundu. | Klinik değerlendirme oluşmadı. Hasta bildirimi clinical_findings içine de alındı; yapılmayan kesme girişimi oral_habits altında. |
| Hareketli protez/kalıcı yara |3kaynak/4kontrolle kısmi sonuç. |5planın5i OTHER nedeniyle yok. Yara bölgesi ve sigara sıklığı zaten kayıtlıyken yeniden yok/net değil deniyor. Genel kuruluk önerisi geldi; süren yara için özgül değerlendirme eksik. |
| Yeni kron/yüksek kapanış | Çıkarım422, taslak korundu. | Provider stop=tool_use tools=2; tek obje sözleşmesi iki araç çağrısını reddetti. İsteğe disable_parallel_tool_use=True eklendi; payload testi RED→GREEN. |

Ham DOM kanıtları yalnız sentetik test metinlerini içerir. Kaynak alıntısının kabulü, hastaya özgü klinik uygunluk veya güvenlik onayı değildir.

## Hata tanılama değişikliği

Final hatası iki kez canlıda görüldüğü için stage/type/sabit izinli neden/liste sayısı tanılaması eklendi. Ham exception/provider/hasta metni veya traceback loglanmaz. Klinik davranış ve taslak koruma değişmedi. İki test önce RED sonra GREEN;613Python/11Node geçti, iki mevcut bağımlılık uyarısı. Bağımsız inceleme32odaklı testle onayladı. PR244 tanılama yayını; bu altta yatan hatanın çözüldüğü anlamına gelmez.

Genel CI önceki sürümde akademik/PostgreSQL hataları nedeniyle kırmızıydı; sesli kontroller başarılıydı. Yeni PR'ın sonucu ayrıca doğrulanacaktır.

Tek araç düzeltmesinin dayanağı: [Claude resmi paralel araç belgesi](https://platform.claude.com/docs/en/agents-and-tools/tool-use/parallel-tool-use). Bu özellik yalnız çıkarım veri aracına uygulandı; kamusal kaynak araştırmasının araç sınırları değiştirilmedi. İki yanıtı keyfi birleştirme veya otomatik ücretli tekrar yok.18provider testi geçti.

## Final yeniden deneme ve yayın

PR244/ed0cf827620a030bca5933594e2106bce6e559af Render dep-dbmnhfss728c739d1840 ile6Kasım09:52:20 Türkiye live. Aynı açık cerrahi sayfadan yalnız final tekrarlandı; bu kez2kaynak/4kontrolle kısmi sonuç geldi. Önceki iki hatanın nedeni henüz kanıtlanmadı; tanılama klinik davranışı değiştirmediği için bu başarı bir hata düzeltmesi veya tutarlılık kanıtı değildir. Önceki plan/yanıt kaybı devam ediyor.

Tek araç sınırı PR245/d0eed32f982b7925201f9dcfa24365ca189f9e61:614Python/11Node (Node koşusu backend değişikliğinden önce),18odaklı bağımsız provider testi. Yayın sonrası kron yeniden denemesi gerekiyor.

Plan/yanıt çakışması yerelde tekrarlandı: aynı alıntıda PATIENT plan + OTHER clinician_response ikisi de dışlanıyor. Gerçek model çıktısının ham özel gövdesi loglanmadığından bu mekanizmanın canlıdaki plan kaybını kesin açıkladığı söylenemez. Hekim/asistanın kendi öyküsünü hastaya taşımamak için OTHER etiketleri topluca PATIENT'e çevrilmedi.

PR245/5196f44440c5451fd5aa30d707cbe7c49c6a0405 Render dep-dbmnjflckfvc738qefe0 **6Kasım09:56:19 Türkiye live** doğrulandı. Dağıtım sırasında açılan yeni bir sekmede502 görüldü; live sonrası tek yeniden yüklemeyle200arayüz geldi. Kronun korunmuş metniyle çıkarım ve çocuk travması testi yeni sürümde başlatıldı.

PR245 uzak kontroller: voice, contract-tests, ready-model-contract başarılı. İş logları okundu: static-safety40başarısız/966başarılı/34atlanan/566alt-test; application-regressions43başarısız/2077başarılı/48atlanan/594alt-test; PostgreSQL2başarısız/42başarılı. Başarısızlık adları önceki akademik çalışma akışıyla aynı alanlarda; voice test başarısızlığı görülmedi. Genel CI yeşil değildir.

Kronun yeni sürüm tekrarı çıkarım hatasını aşarak3kaynak/0kontrolle kısmi sonuca ulaştı. Yeni tools=2 reddi görülmedi; tek deneme genel güvenilirlik kanıtı değildir. Özgül materyal belirtilmemişken model lamine/veneer konusunu seçti; uygunluk denetimi tamamlanmadı. Plan alanı yine kayıp, yapılmış açıklamalar tekrar isteniyor. Materyal başlığı canlıda kapatılıp açıldı; DOM open=False→True ve ekran görüntüsüyle doğrulandı. Bu masaüstü tarayıcıdır, fiziksel Android testi değildir.

Çocuk travması yeni sürümde çıkarımı tamamladı (yaş8, kalıcı/süt dişi belirsiz, evde yerine koyma yapılmamış, muayene/görüntüleme planlı). Kaynakların tamamına erişilemediğinde final çağrısından önce durdu; alanlar ve metin korunuyor. Klinik travma kontrolü başarıyla yapılmış sayılmaz.

Son değişiklik sonrası Node koşusu tekrarlandı:11/11başarılı.

## Sonuç ve öncelikler

Sekiz farklı vaka çalıştırıldı: altısı kısmi final çıktı üretti, ikisi kaynak erişimi nedeniyle final modele geçmeden durdu. Bu bir başarı oranı/duyarlılık ölçümü değildir. Cerrahinin ilk iki final denemesi ve kronun ilk çıkarımı ayrıca başarısızdı; yalnız son çıktıyı saymak bu sorunları gizler.

| Öncelik | Açık bulgu | Gerekli doğrulama |
|---|---|---|
| Yüksek | Hekim planları OTHER işaretlenebiliyor; transient response/statement aynı alıntıyı nonpatient saydırıp PATIENT planı da engelleyebiliyor. | Konuşmacı ile bilginin öznesini ayrı sözleşmeyle sınamak; gerçek klinik ekip kendi öyküsü karşı örneklerini korumak. Toplu PATIENT dönüştürme yapılmadı. |
| Yüksek | Genel kaplama lamine/veneer seçildi; endodonti özgül kaynağı yok. | Kaynak/konu eşleşmesi ve eşleşmeyen araştırma kapsamını gerçek model tekrarlarıyla ölçmek. |
| Yüksek | Süren protez yarası genel protez/kuruluk notlarıyla kaldı. | Süre/açıklanamayan yara ve yönlendirme kapsamını hekim onaylı altın vakada değerlendirmek. |
| Yüksek | İki final hatası üçüncü tekrarda kayboldu; neden kanıtlanmadı. | Yeni gizlilik koruyan tanılama ile tekrar oluşursa aşama/neden ölçmek; tek başarıyla kapatmamak. |
| Orta | Yanıtlanmış sorular yeniden soruluyor, bilinen bölge/sigara sıklığı yok sayılıyor. | Alanlar arası ve hekim yanıtı bağlamının kapsamını değerlendirmek. |
| Orta | Hastanın diyabet tanısı reddi genel sistemik hastalık yokluğuna genişliyor. | Yalnız reddedilen hastalık kapsamını tutan ayrı negatif kontroller. |
| Orta | Yeni kaplama materials alanında ama dental_history yok; anamnez tablosu önceki diş tedavisine bilgi yok diyor. | Aynı bilginin farklı alanda bulunmasını dikkate alan mevcudiyet değerlendirmesi. |

Süren yara için karşılaştırma kaynağı: [NICE NG12§1.8.2](https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer). NICE, **üç haftadan uzun** açıklanamayan ağız ülserinde kanser şüphesi yoluyla yönlendirmeyi değerlendirmeyi önerir. Bu vakanın ifadesi **üç hafta**, kesin >3hafta veya açıklanamayan lezyon tanısı değil; süre ve muayene netleştirilmeden eşik aşılmış sayılmamalı. İngiltere yolu Türkiye mevzuatı veya otomatik yönlendirme kuralı olarak uygulanmadı. Buna rağmen süre ve muayene/yönlendirme kapsamının özgül kaynakla ele alınmaması bir değerlendirme açığı olarak kaydedildi; kanser tanısı çıkarılmadı.

Son runtime:5196f44440c5451fd5aa30d707cbe7c49c6a0405,6Kasım09:56:19Türkiye live. Kod614Python/11Node yerel testini geçti. Son8vaka insan sesi/mikrofon değil, canlı gerçek sağlayıcıya sentetik metin aktarımıdır. Hekim onaylı doğruluk, insan ASR, fiziksel Android, ürün IFU tam kapsamı ve yenileme sonrası taslak kurtarma tamamlanmadı. Hasta kaydı yapılmadı.

Ekran kanıtı: [canlı kron sonucu](voice_live_campaign_crown_2026-11-06.png). Başlık açılışı kontrol edildi; ekran aynı zamanda yanlış veneer konusunu ve tamamlanamayan uygunluğu gösterir.
