# Anamnez ve materyal akışı — 6 Kasım 2026

## İncelenen mesleki kaynaklar

- [TDB hasta/anamnez/tedavi kartı — İzmir Dişhekimleri Odası](https://izdo.org/img/userfiles/files/TDB_Hasta_Anamnez_Formu.pdf): tedavi/ilaç, hastalık, radyoterapi, uzamış kanama ve diğer tıbbi sorunlara ilişkin öykü başlıkları. Revizyon tarihi doğrulanmadı; güncel klinik tedavi veya hukuk kuralı olarak kullanılmadı.
- [ADA Medical/Dental Health History](https://www.ada.org/resources/practice/practice-management/medical-dental-health-history): tıbbi/diş öyküsünü gözden geçirme ve güncelleme; yeni görüşmede eklenen bilgiyi koruma.
- [SDCEP Patient histories](https://psm.sdcep.org.uk/topics/record-keeping/records-required/patient-histories/): tıbbi, dental ve sosyal öykü; aile öyküsü, bakım alışkanlıkları ve kaygı bağlamı.
- [SDCEP akut başvuruda değerlendirme](https://www.acutedentalproblems.sdcep.org.uk/guidance/overarching-principles/patient-assessment-and-record-keeping/): odaklı başvuruda ilgili öykü, önceden alınmış ağrı kesiciler ve reaksiyonları dikkate alma. Akut değerlendirme tam rutin incelemeyle eşit sayılmadı.
- [SDCEP periodontal hasta öyküsü](https://periodontalcare.sdcep.org.uk/guidance/assessment/patient-history/): yakınma, bakım ve ilgili risk bilgilerini güncelleme.

Kaynaklar başlık tasarımının dayanağıdır; her hasta için otomatik risk, ilaç yasağı veya tedavi kararı üretmez. Kimlik/iletişim/meslek gibi form alanları sesli öyküye genişletilmedi. Ankara Dişhekimleri Odasının2020 formu da incelendi; tarihli COVID talimatları güncel sisteme aktarılmadı.

## Akışta yapılan değişiklikler

| Başlık | Korunan ayrım |
|---|---|
| Başvuru/şikâyet | Bölge, süre, seyir ve tetikleyiciler; ağrı yokluğu diğer şikâyeti silmez |
| Kişisel sağlık öyküsü | Kişinin hastalığı/yokluk beyanı; aile veya klinik ekibin öyküsüyle karıştırılmaz |
| İlaçlar | Düzenli, kısa süreli, aralıklı/enjeksiyon ve reçetesiz kullanım ayrımı; düzenli yok bütün kullanım yok değildir |
| Alerji/reaksiyon | Bildirilen madde/reaksiyon; bilinmiyor, yok ve hiç konuşulmadı ayrı kalır |
| Önceki diş tedavileri | Eski işlem ve yaklaşık zaman; bugünkü yapılmış işlemle eşitlenmez |
| Aile sağlık öyküsü | Ayrı family_history alanı ve FAMILY öznesi; doğrudan kişinin hastalığına çevrilemez |
| Bakım/alışkanlıklar | Söylenen bakım/tütün/beslenme/sıkma bilgisi; sıklık veya neden uydurulmaz |
| Konuşulan materyaller | Ayrı materials alanı; açık ad/ürün/tür, belirsiz seçim ve planlanan/uygulanmış ayrımı |
| Görüşmedeki yanıtlar | Hekim yanıtı, hasta geri anlatımı ve konuşmacısı bilinmeyen yanıt ayrı geçici türler |

Yedi anamnez grubunun genel inceleme kapsamı mevcut çıkarım ve son değerlendirme çağrılarına eklenir; ayrı anamnez modeli çağrılmaz. Bitişte Anamnezde konuşulanlar kartı yalnız bilgi var/dökümde yok gösterir. Bilgi var, anamnez tamamlandı veya hasta sağlıklı demek değildir. Dökümde yok, hekimin sormadığı demek değildir. Materyal bilgileri ayrıca özet ve seçmeli kayıtta görünür.

Materyal adı, alt tür/marka, ölçü, siman/bağlantı veya kullanım durumu konuşulmamışsa üretilmez. Konuşmada verilen isim birebir tutulur. Üretici IFU/ürün varyantı doğrulanmış sayılmaz; yeni üretici kataloğu eklenmedi. Kaynak parçası bulunamaması ile kaynak varken hasta özelinde kontrol üretilememesi ayrı gösterilir. Sözcük eşleşmesi uygunluk onayı değildir.

## Bulgular ve düzeltmeler

1. Tam olumsuz ilaç cümlesinin sonundaki nokta, önceki dar denetimin alıntı eşleşmesini bozuyordu. Kutu/reçete doğrulaması da yeni reçete sanılıp soru korunuyordu. Canlıda görülmüş ifade testte önce RED, sonra GREEN oldu. Kapsam hâlâ yalnız açık düzenli kullanım sorusudur; genel/PRN, yeni/planlanan ve kısa süreli ilaç soruları korunur. Geçmiş/belirsiz/planlanan yokluk güncel kullanımın cevabı sayılmaz.
2. Son modele özgün kısa dayanak verilmediğinde bazı ayrıntılar yalnız özette kalıyordu. Yeni istemci edited:false bilgisini açık gönderir; yalnız bu durumda özgün kısa evidence_quote korunur. Hekim düzenlediyse veya eski istemcide bu bayrak yoksa eski alıntı tekrar modele sokulmaz. Hekimin düzeltmesi geri alınmaz.
3. Aile öyküsü ile hastanın kendi olumsuz beyanı ayrı atomik alıntılara bağlanır. FAMILY/OTHER çakışması, cevapsız aile öyküsü sorusu ve klinik ekibin açık birinci kişi yakını ifadesi hasta aile kaydı yapılmaz.
4. Açık konuşmacı etiketlerinde en yakın satır içi etiket kullanılır. Aynı alıntı farklı/etiketsiz yerlerde geçiyorsa hekim yanıtı diye doğrulanmaz. Etiketsiz gerçek seste konuşmacı tespiti kanıtlanmış değildir.
5.13 alanın birlikte hekim onaylı kaydı testlidir. Kısa dayanak/düzenleme bayrağıyla bağlam büyüdüğü için istemci ve sunucu sınırı32KB oldu; daha uzun veri sessiz kesilmez. Son model80.000 karakter sınırı ve mevcut çağrı/kaynak bütçeleri korunur.
6. Materyal başına kamusal aday kaynak sayısı/kabul edilen kontrol sayısı günlüklenir. Hasta metni veya alıntı günlüğe eklenmez. Bu ölçüm klinik doğruluk değildir.

## Doğrulama sınırları

Son tam test, yayın ve inceleme sonuçları ilerleme belgelerine ayrıca yazılır. Testler sözleşme, alıntı/atıf, kayıt/onay, yeniden deneme ve DOM davranışını doğrular; klinik altın set değildir. Gerçek modelin tüm anamnez ayrıntılarını doğru seçtiği, hiçbir yanlış soru üretmediği veya her materyali güvenle değerlendirdiği kanıtlanmadı.

Önceki canlı post tekrarı AAE kaynağıyla0 kontrol üretmişti; yeni görünür tanılayıcı bilgi bu açığı gizlemez. Gerçek modelde yeniden sınanması gerekir. İnsan mikrofonu, fiziksel Android, hekim onaylı klinik altın set ve sayfa yenilemesinde kalıcı taslak kurtarma açık sınırlardır. Genel akademik CI hataları bu değişiklikte düzeltilmiş sayılmaz.

Önceki otomatik tarayıcı güvenlik incelemesi dentalai.tr işleme onayını ve sonrasında salt okunur erişimi engelledi. Bu çalışmada API, farklı oturum veya başka yüzey kullanılarak bu engel aşılmadı; yeni canlı model/mikrofon denemesi yapılmış gibi sunulmaz.

Son tam yerel doğrulama:603Python/11Node geçti; iki mevcut bağımlılık uyarısı. Bağımsız son odaklı inceleme143testte engel kalmadığını bildirdi. Yayın ve uzak CI sonucu ilerleme belgelerinde ayrıca kaydedilir.

Yayın öncesi ek gizlilik kontrolü: yaş alıntısı içinde isim geçerse final modele gereksiz kimlik taşınabiliyordu. RED regresyonla yakalandı; yaşın yalnız değeri aktarılır, yaş evidence_quote eklenmez. Bağımsız52 odaklı testte engel kalmadı. Son tam yerel koşu **604 Python/11 Node geçti** (iki mevcut bağımlılık uyarısı).


PR242/5738245f96cc5275fb39e44746beda9c8e23790d, Render dep-dbmn3hnf3r2c73aj82cg **6 Kasım09:22:32 Türkiye** itibarıyla live. Dağıtım SHA üzerinden doğrulandı; yeni tarayıcı ekranı veya gerçek model tekrarı yapılmadı. Sesli/contract/ready-model kontrolleri başarılı. Son uzak application-regressions43başarısız/2067başarılı/48atlanan/594alt-test başarılı, static-safety40başarısız/966başarılı/34atlanan, PostgreSQL2başarısız/42başarılı. Genel CI yeşil değil; ek hata adları test_production_optimization.py::test_study_generation_releases_db_connection_and_rechecks_course[False/True] ve test_study_index_v2_isolation.py::test_v2_streaming_is_feature_gated_end_to_end dahil akademik çalışma akışında.

Son uyumluluk düzeltmesi: eski açık istemciler yeni yanıt türünü category alanında görünce tanımsız iletişim başlığı gösterebiliyordu. Yanıt atfı ayrı response_type özelliğine taşındı; mevcut klinik iddia/engel kategorileri değiştirilmedi. Final eski category biçimini de okuyabilir. Bozuk liste/sözlük türleri önceden TypeError veriyordu;6 tür için route testi RED→GREEN, hepsi araştırmaya ulaşmadan422 döner. Son tam yerel doğrulama **611 Python/11 Node geçti**; iki mevcut bağımlılık uyarısı. Bağımsız113odaklı testte engel kalmadı. Uyumluluk yayını aşağıya eklenecek.


## Tespitlerin son durumu

| Sorun | Durum |
|---|---|
| Eski diş tedavisinin sistemik alana düşmesi | Ayrı alan önceki gerçek model tekrarında çalıştı; yeni anamnez kapsamı sözleşme testli |
| Aile hastalığı ile kişinin olumsuz yanıtının karışması | Ayrı FAMILY atfı ve çakışma/soru korumaları kod/test tamam; yeni model tekrarı gerekli |
| Materyal adının/kararsız seçimin kaybolması | Birebir materials alanı ve onaylı kayıt kod/test tamam; gerçek model tekrarı gerekli |
| Verilmiş hekim yanıtının yok sayılması | Kısa kaynak alıntısı ve yanıt türü kaybı düzeltildi; modelin yorum doğruluğu yeniden ölçülmeli |
| Cevaplanmış düzenli ilaç sorusunun tekrarı | Canlıdaki tam olumsuz örnek ve kapsam/zaman karşı örnekleri testli; genel anlamsal sorun tamamen kapanmış sayılmaz |
| Genel kaynakla özgül materyali onaylama | Mevcut materyal kapsam filtresi/eksik durumları korunuyor; uygunluk onayı üretilmez |
| AAE getirildiği halde post kontrolü0 | Açık; neden ayrımı ve tanılayıcı sayılar eklendi, gerçek model yeniden denenmeli |
| Tıklanmayan özet/taşan mobil/iç etiketler | Önceki düzeltmeler korunuyor; DOM testli, fiziksel Android yeniden doğrulanmadı |
| Hata ve yeniden denemede metin kaybı/çift çağrı | Aynı açık sayfada kontrol noktaları/fingerprint testli; sayfa yenilemede kalıcı kurtarma açık |
| Otomatik hasta kaydı | Seçim ve hekim onayı gerekir; bu oturumda hasta kaydı yapılmadı |
| Gerçek mikrofon/ASR ve klinik doğruluk | Yeni test yapılmadı; insan sesi ve hekim onaylı altın set gerekli |
| Tüm üretici/ürün IFU uygunluğu | Tamamlanmadı; ürün ailesi bilgisi belirli ürün onayı sayılmaz |


## 6 Kasım canlı vaka kampanyası (devam ediyor)

PR24366942150d6c284b924d947de591dd9913365deea,6Kasım09:35:34 Türkiye live doğrulandı. Yeni kullanıcı isteğiyle arayüz erişimi/işleme onayı çalıştı; eski tarayıcı engeli bu kampanya için geçerli değil. Sentetik üç konuşmacılı metinlerle cerrahi/varfarin, perio, implant, kron ve endodonti denendi. Gerçek mikrofon/ASR veya hekim onaylı klinik altın set değil; hasta kaydı yapılmadı.

Perio3kaynak/3kontrol, implant2kaynak/2kontrol; aile öyküsü ayrımı çalıştı. Cerrahi final iki kez422, üçüncüde2kaynak/4kontrolle kısmi hazır; önceki hataların nedeni kanıtlanmadı. Kron çıkarımında tools=2 hatası bulundu. Endodonti2kaynak/0kontrol; özgül pulpa belgesi yerine genel anestezi/AAPD Overview geldi. Plan/yanıt kaybı, bazı yanıtlara rağmen tekrar soru ve kişisel diyabet reddinin genel sistemik yokluğuna genişlemesi açık.

PR244ed0cf827620a030bca5933594e2106bce6e559af6Kasım09:52:20 Türkiye live: gizlilik koruyan stage/type/sabit neden/sayı tanılaması.613Python/11Node,32bağımsızodaklı test başarılı. PR245tek çıkarım aracına disable_parallel_tool_use=True ekledi; payload testiRED→GREEN,614Python,18provider testi. Klinik atıfları otomatik düzeltmez, ek ücretli otomatik çağrı veya başka sağlayıcı yok. Genel CI yeşil değil; sesli/contract/ready-model yeşil, akademik/PostgreSQL hataları mevcut.

Ayrıntı ve sentetik DOM kanıtları: [canlı kampanya](voice_live_campaign_2026-11-06.md). Devamındaki yayın ve yeniden deneme sonuçları o dosyaya eklenecek.

Kampanya tamamlandı:8farklı sentetik vaka,6kısmi final/2kaynak erişimi nedeniyle finalden önce durma. İlk hata denemeleri bu sayıya başarı diye gizlenmez. PR2455196f44440c5451fd5aa30d707cbe7c49c6a0405,6Kasım09:56:19Türkiye live ve eski hatalı kron metni yeniden işlendi; araç sayısı1 oldu.614Python/11Node son kodda geçti. Plan/yanıt kaybı, yanlış veneer konusu, özgül endodonti kaynağı yokluğu, süren yara değerlendirme kapsamı ve fazla/genişletilmiş negatif bilgiler hâlâ açık. Ayrıntı kampanya raporunda. Hasta kaydı/mikrofon testi yapılmadı.
