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
