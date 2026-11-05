# Sesli muayene kapsamı — 5 Kasım 2026

Bu belge uygulamadaki konu ve alan desteğini açıklar. Bir başlığın varlığı, bütün endikasyon/kontrendikasyonların doğrulandığı veya klinik güvenliğin kanıtlandığı anlamına gelmez.

## Muayene bilgileri

| Alan | Amaç |
|---|---|
| Başvuru şikâyeti | Hastanın yakınması, bölge, süre, tetikleyiciler ve devam eden belirtiler |
| Sağlık geçmişi | Sistemik hastalık, tetkik ve hasta beyanı; diş tedavisi geçmişinden ayrı |
| Önceki diş tedavileri | Eski kanal/dolgu/kaplama/implant ve bildirilen önceki sorunlar; bugünkü işlem sayılmaz |
| Ağız bakımı ve alışkanlıklar | Açıkça söylenen bakım, tütün, sıkma ve beslenme bilgileri; bilinmeyen sıklık eklenmez |
| İlaç / alerji bilgileri | Olumsuz, belirsiz, geçmiş ve güncel beyanları koruma; düzenli kullanım yokluğu başka bütün kullanımları dışlamaz |
| Muayene bulguları | Söylenen klinik/görüntüleme bulguları; planlanan test yapılmış sayılmaz |
| Konuşulan tedavi planı | Koşullu işlem, inceleme, yönlendirme ve takip; otomatik tedavi kararı verilmez |
| Hekimin ifadeleri | Geçici, kaynakla kontrol edilmesi gereken iddialar; doğru/yanlış ayrımı yalnız kaynak varlığına indirgenmez |
| Hasta iletişimi | Kaygı, maliyet, beklenti ve verilen açıklamalar; dosyaya otomatik yazılmaz |

Yeni dental_history ve oral_habits alanları çıkarım şemasından özet, düzenleme, seçmeli hekim onayı, kayıt ve onaylı geçmişi geri okumaya kadar desteklenir. Eski kayıtlar otomatik yeniden sınıflandırılmaz. Klinik olumsuzluk ve zaman etiketleri iç veride korunur; ekranda sade Türkçe gösterilir.

## Diş hekimliği alanları

| Ana alan | Konu kapsamından örnekler |
|---|---|
| Protetik tedavi | Kuron/köprü, hareketli protez, kapanış, siman, zirkonya/cam seramik/metal seramik/lamine, dijital ölçü, implant destekli hareketli protez |
| Endodonti | Tanısal değerlendirme, canlı pulpayı koruma, yeniden kanal, çatlak, alet/perforasyon/atlanan kanal, post-kor, irrigant ve dolgu patı |
| Restoratif tedavi | Çürük, derin çürük, doku koruma, tamir/yenileme, adeziv/kontakt, materyal, aşınma, hassasiyet ve estetik |
| Periodontoloji | Hastalık, cerrahi, greft/membran, implant çevresi dokular |
| İmplantoloji | Yerleşim/yükleme, protez, bağlantı/parça uyumu, bakım/takip |
| Çene cerrahisi | Çekim, yirmi yaş, kanama, sinir, sinüs, soket iyileşmesi ve kemik artırımı |
| Ortodonti | Aparey/plak, pekiştirme, kök riski, periodontal destekle tedavi ilişkisi |
| Çocuk diş hekimliği | Süt/genç daimi diş, pulpa, travma, davranış, yer/oklüzyon ve gelişim |
| Ağız hastalıkları | Mukoza, kalıcı lezyon, tükürük/kuruluk, enfeksiyon |
| Orofasiyal ağrı | Eklem/kas, diş dışı/nöropatik ağrı ve uyku/solunum bağlamı |
| Radyoloji | Görüntüleme seçimi, gerekçelendirme ve yorum sınırları |
| Anestezi/sedasyon | Lokal uygulama, advers olay, sedasyon ve izlem |
| Klinik aciller | Solunum, aspirasyon, senkop ve alerjik reaksiyon bağlamı; bitişte çalışan sistem gerçek zamanlı acil alarm sistemi değildir |
| Sistemik risk ve özel bakım | Hastalık, ilaç etkileşimi, kardiyak/kan basıncı ve özel hasta koşulları; mevcut eski konu kimlikleri korunur |
| Koruyucu bakım | Hijyen, beslenme/asit, florür, fissür örtücü ve risk temelli bakım |

Toplam92 kapalı konu kimliği vardır (önce80). Yeni12 konu: endo.vital_pulp, endo.retreatment, implant.planning, implant.maintenance, prosth.digital_workflow, prosth.overdenture, restorative.deep_caries, restorative.repair, ortho.periodontal, surgery.bone_augmentation, surgery.alveolitis, orofacial_pain.neuropathic. Her biri sabit kamusal kapsam ve sorguya bağlıdır; modelin serbest hasta araması oluşturmasına izin verilmez. Yeni konulara doğrulanmamış genel sayfa bağlantısı atanmadı; mevcut izinli kamusal araştırmada sabit kavramla aranırlar. Kaynak bulunamaması görünür eksikliktir.

Lamine ile zirkonya üzerine porselen tabakası aynı konu değildir; konu tanımı bu ayrımı açıklığa kavuşturur. Bu değişiklik gerçek modelin her koşulda doğru seçim yapacağının kanıtı değildir.

## Akış ve sınırlar

Dinlemede yalnız metin toplanır. Bitişte mevcut review_provider ile çıkarım, kapalı kimliklerle kamusal kaynak araştırması ve son değerlendirme çalışır. Yeni alan/başlık için ayrı model aşaması açılmadı. Kaynak araştırmasının24 konu,2 arama/3 getirme sınırları değişmedi; uzun çok konulu bir görüşmede her konuya özgül kanıt bulunması garanti edilemez. Kaynak yokluğu, materyalin uygunluğu veya klinik güvenlik onayı değildir.

Hastaya/dişe/bölgeye uygunluk, materyal alt türü, kalan doku, periodontal destek, kapanış/yük, izolasyon, bağlantı ve işlem tekniği yalnız konuşma ve erişilen kaynakların izin verdiği ölçüde değerlendirilebilir. Ölçüm, radyografi, ürün kullanım talimatı veya hasta bilgisi yoksa sistem bunları bilmiş gibi davranmamalıdır.

Yeni regresyonlar:12 doğal kısa ifade ile kapalı konu yönlendirmesi, ayrı geçmiş/alışkanlık alanları, olumsuz onayda yazmama, tüm11 alanı birlikte kaydetme, yeni alanları onaylı geçmişten geri okuma, soruyu hasta beyanı saymama ve birebir alıntıyı koruma. Bunlar altın klinik test seti veya1,5 dakikalık gerçek ses testleri değildir. Mevcut8 uzun sentetik klinik diyalog ayrıca korunmuştur.

Gerçek insan mikrofonu, fiziksel Android tekrar ölçümü ve hekim onaylı altın test seti tamamlanmadı. Genel uzak CI başarısızlıkları sesli testlerin geçmesiyle kapanmış sayılmaz.
