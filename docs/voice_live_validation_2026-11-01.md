# Canlı sesli muayene doğrulaması — 1 Kasım 2026

Bu kayıt otomatik test sonuçlarından ayrı, gerçek dentalai.tr oturumunda gözlenen adımları raporlar. Metinler sentetik ve kimliksizdir; gerçek mikrofon/ASR testi henüz yapılmadı. Kullanıcı güvenli giriş formuyla oturum açtı; kimlik bilgileri modele veya rapora aktarılmadı.

## Gözlenen akış

- #217 sürümü 2aff1244 Render'da live; giriş ve sesli muayene sayfası açıldı. Dört sesli istemci dosyası yayınla birebir eşleşti.
- Ayrı anonim test muayenesi açıldı. Gerçek hasta kaydı kullanılmadı. Test metni protez çıkarılmasına rağmen haftalardır kapanmayan yara ve hekimin erken kesinlik iddiasını içeriyordu.
- 13:36 İstanbul: Metni işle ve değerlendir gerçek isteği Claude HTTP400 / schema_argument ile kesildi. Backend /text yanıtı422 oldu. Kaynak ve final aşamasına geçilmedi.
- Metin sayfada aynen kaldı, onay ve yeniden deneme kontrolü tekrar kullanılabildi; klinik çıktı veya hekim onaylı kayıt oluşmadı.
- İlk hata mesajı yanlışlıkla ses servisini suçladı. #218 bunu klinik metin aşaması olarak düzeltti; yalnız sabit tanı sözcükleriyle güvenli log eklendi. Ham sağlayıcı hata metni, anahtar ve hasta içeriği loglanmaz. 450 Python testi geçti; inceleme62/64 odaklı testi doğruladı.
- 13:42 İstanbul: #218 04684f92 live olduktan sonra aynı korunmuş metinle ikinci deneme yine400 verdi; sabit log etiketleri strict,type. Şema standart JSONSchema denetiminden geçti.
- #219 tek değişkenli uyumluluk denemesi: clinical_extract üzerindeki isteğe bağlı strict derleme seçeneğini kaldırır; zorunlu tool_choice, şema, kapalı taksonomi, alıntı ve klinik çıktı doğrulaması, sağlayıcı/model ve hekim onayı korunur. 450 Python testi geçti, bağımsız incelemede engelleyici bulgu yok. Canlı sonucu aşağıda eklenecek.

## Henüz doğrulanmamış

Gerçek sağlayıcıyla başarılı çıkarım, doğru kaynak getirme, nihai klinik uygunluk, yanlış alarm/kaçırılan uyarı oranı, gerçek mikrofon ve konuşmacı ayrımı. İlk iki sağlayıcı isteği başarısızken bunlara başarılı sonucu yazmak doğru olmaz. Başarısız sağlayıcı çağrılarının ücretlendirilmesi ölçülmedi. Yalnız sayfa içi metin korunması gözlendi; yenileme sonrası kalıcılık doğrulanmadı.

## Çıkarım düzeltmesinin canlı sonucu

13:46 İstanbul'da #219 7f1b9c40 live olduktan sonra aynı metinle deneme başarılı çıkarım verdi: /text200, tool_use1, eksik kök anahtar yok, 8 atomik adaydan4 dayanaklı alan. Süre, kanama, protez kullanılmaması, koşullu ileri inceleme ve netleştirme soruları ekranda görüldü. Bu tek vaka çıkarımının çalıştığını gösterir; klinik doğruluk oranı değildir.

Ardından kaynak aşaması /finalize422 ile durdu. Ekran kaynaklara erişilemediğini söyledi, metni ve çıkarılan alanları korudu, kayıt düğmesini devre dışı bıraktı. Kaynak araştırması başarısızlığının ayrıntısı henüz mevcut değildi; aynı sabit-sözcüklü HTTP tanılaması research aşamasına da eklendi. Son model çağrısına başarı yazılmadı.

## Kaynak ve final aşamasına gerçek geçiş

13:52 İstanbul'da #220 c0dcf7a7 live üzerinden yalnız final yeniden denendi. Yeni /text çağrısı oluşmadı; başarılı çıkarım tekrar çalıştırılmadı. Araştırma max_tokens ile kısmi bitti (24 blok), bir kaynak gösterildi; final200 döndü, sıfır kaynaklı klinik kontrol noktası ve hekimin kesinlik iddiası için açık 'doğrulanmadı' görünümü vardı. Bu tek koşuda yanlış kanser tanısı veya otomatik tedavi kararı gösterilmedi.

Kaynak kapsamı açılınca somut kusur görüldü: gösterilen PMC belgesinin başlığı 'Checking your browser - reCAPTCHA' idi. Klinik öneriye dayanak yapılmamasına rağmen kaynak sayısına katılmıştı. Bu bir erişilmiş klinik belge değildir. Known interstitial sayfalarının referans sayılmaması ve hepsi erişim engeliyse ücretli son model çağrısından önce durulması için RED/GREEN testleri eklendi. Tek bir kelime yasağı yerine belirli engel başlıkları/başlangıç işareti kullanılıyor; gerçek bir makaledeki CAPTCHA sözcüğü engel sayılmıyor.

Ayrıca kapalı konu kimliğine bağlı mevcut mesleki başlangıç URL'leri (DOCUMENTS/TOPIC_DOCUMENTS) yalnız kamusal araştırma isteğine eklendi. En çok2/adet konu; kullanıcıdan gelen URL/alıntı/query aktarılmaz. Bunlar kaynak kanıtı değil, Claude'un önce ilgili meslek kuruluşu HTML sayfasını incelemesi için başlangıç noktasıdır. Yerel otomatik kaynak fallback'i ve model değişimi yok. Gerçek klinik kapsamı fetched pasaj belirler.

## Engel filtresinden sonra canlı durum

14:00 civarı İstanbul'da #221 afc40e46 üzerinden aynı klinik bilgilerle final yeniden çalıştı. ADA Cancer (Head and Neck) ve ADA Xerostomia sayfaları gerçek bağlantılar olarak görüntülendi; reCAPTCHA kaynağı artık yoktu. Sonuç hâlâ kısmi kapsam ve sıfır kaynaklı klinik kontrol noktası gösterdi. Hekim iddiası doğrulanmış/yanlış diye etiketlenmedi. Bu sonuç, kaynağın ulaşılabildiğini fakat bu vakaya yeterli klinik dayanak üretildiğini göstermediğini ayırır.

Ayrı canlı kayıt kapısı kontrolü: yalnız başvuru alanı seçildi, hekim onay kutusu işaretlenmeden Kaydet düğmesine basıldı. Ekran 'Seçilen alanları kontrol edip onay kutusunu işaretle' dedi; otomatik klinik kayıt yapılmadı.

Kaynak pasajı seçicisinde ek bir laboratuvar kusuru RED testleriyle gösterildi: paragraf ayracı olmayan, uzun menüden sonra klinik paragraf içeren bir belgenin ilk1800 karakterini almak gerçek ilgili pasajı kaybediyordu. Bu bulgu canlıdaki sıfır kontrol noktasının tek nedeni olduğunu kanıtlamaz. Düzeltme, birebir alıntıları önce korur; yalnız sunucuya ait doğrulanmış konu terimleriyle1800 karakterlik,1400 adımlı gerçek metin pencerelerini sıralar. Kaynak/alıntı bütçesi ve6 pasaj sınırı değişmez; yeni model çağrısı veya hasta metni aktarımı eklenmez. Eski konu kimlikleri de yalnız bilinen kimlik listesinden türetilir.

Aynı dalda özel bir konu için eşlenmiş başlangıç sayfası varsa genel konunun ek başlangıç URL'leri bastırılır; seçilen konu kimlikleri silinmez. Örneğin kanser konusu varken genel ağız hastalıkları eşlemesindeki ilgisiz ağız kuruluğu başlangıcı araştırmayı dağıtmaz. Bu bir klinik öneri kuralı değildir. Ara testte eski kimlik senaryosu başarısız oldu; bilinen kimliğe güvenli fallback ile düzeltildi. Bağımsız inceleme119 odaklı testin geçtiğini doğruladı. Sıralama klinik uygunluk kanıtı değildir.

## Son canlı tekrar — #222

#222 a06f4654 Render dep-dbjhqtjm8hqs73fpnf6g ile14:09:20 İstanbul'da live oldu. Korunmuş ilk vaka alanlarıyla yalnız kaynak/final yeniden denendi; yeni çıkarım yapılmadı.14:10:44'te /finalize200, sources1, accepted3, rejected_reasons{} gözlendi. UI'da gerçek ADA Cancer (Head and Neck) kaynağıyla üç kontrol noktası vardı: kalıcılık/süre ve görünümün netleştirilmesi, koşula bağlı ileri inceleme/biyopsi veya sevk değerlendirmesi, hekimin kesinlik iddiasının dayanağının kontrolü. Kesin kanser tanısı, otomatik tedavi veya hekimin yanlış yaptığı kararı verilmedi. 'Kaynak alıntılı kontrol noktası var' ibaresi doğruluk/güvenlik onayı sayılmaz.

Araştırma yine max_tokens ile bitti; UI bu nedenle kısmi kapsam ve eksik kaynakları yeniden deneme durumunu korudu. Bu, klinik kapsamın eksiksiz olduğunu kanıtlamaz. Yerel sözlükle pasaj sıralama klinik uygunluğu doğrulamaz; kaynak alıntısı ve hastaya uygulanabilirlik hekimce ayrıca incelenmeli.

## İkinci canlı karşılaştırma

Ayrı sentetik muayenede hastanın düşen dolgusu, eşinin çene sesi ve asistanın kendi diş sıkma öyküsüyle üç konuşmacılı diyalog çalıştırıldı. /text200 ve son değerlendirme200 döndü. Eşin ve asistanın rahatsızlığı hastanın kaydına yazılmadı; hastanın çene ağrısı/açılma sorunu ve baş ağrısı olmadığını söylemesi korundu. ADA Materials for Direct Restorations kaynak bağlantısı ve malzeme/neden belirsizliğini koruyan bir kontrol noktası gösterildi. Hastaya bruksizm/TMD tanısı eklenmedi. Bu tek koşu bütün konuşmacı ayrımı başarısı değildir.

Görülen küçük eksik: ikinci vakada hekim muayene planı 'Planlanan' etiketiyle korunmakla birlikte klinik bulgular alanına yerleştirilmişti; gerçekleşmiş bulgu diye yazılmadı fakat alan sınıflaması iyileştirilebilir. Bazı sorular/özet ifadeleri tekrar ediyor. Bunlar klinik olarak onaylanmış iyi/kötü etiketler veya ölçülmüş yanlış alarm oranı değildir.

## Kapsam ve sonuç

- Gerçek oturumda iki sentetik **metin** vakası çalıştırıldı;24 diyaloğun tamamı gerçek modelde çalıştırılmış sayılmaz.
- Canlıda çıkarım400 uyumluluk hatası giderildi; hatalı ses-servisi mesajı düzeltildi. Gerçek erişim engeli sayfasının kaynak sayılması engellendi. Menü öncesi metin kırpma kusuru testle yeniden üretilip düzeltildi. Aynı çıkarımla kaynak/final yeniden denemesi gözlendi; onaysız kayıt ön yüzde engellendi.
- Son üretim kodu: a06f4654. Son otomatik sesli snapshot: **460 Python passed**,2 bağımlılık uyarısı,13.71s. Node26/jsdom30.1.3: daha önce bu oturumda **11 passed**; son değişiklikler yalnız sunucu tarafında. Gerçek tarayıcı kullanımı ve gerçek Claude uç noktası bu raporda yer alır; gerçek mikrofon/Gemini ses çözümleme testi yer almaz.
- Klinik alanlar hekim onayıyla kaydedilmedi; yalnız ayrı anonim test hasta satırları açıldı. Klinik doğruluk/duyarlılık/yanlış alarm oranı, hekimce onaylı altın set, gerçek mikrofon ve pozitif onaylı kayıt senaryosu bu çalışmayla doğrulanmadı. GitHubActions yeşilliği iddia edilmedi.


## Ek canlı koşular — 1 Kasım 2026, 11:47–11:49 UTC

Mevcut giriş oturumu korunmuştu; yeniden şifre istenmeden iki ayrı kimliksiz sentetik muayene açıldı. Gerçek hasta kaydı kullanılmadı; alan seçimi veya onaylı klinik kayıt yapılmadı. Bunlar gerçek üretim arayüzü ve gerçek Claude/kaynak çağrılarıdır; mikrofon/ASR testi değildir.

| Vaka | Gözlenen sonuç | Açık bulgu / sınır |
| --- | --- | --- |
| bone-medicine-index | Aylardır kapanmayan çekim yeri ve adı bilinmeyen aktif hastane ilacı korundu. “Başka günlük hap yok” ilacı silmedi. İlaç adı, uygulama yolu ve son tarih soruldu; belirli etken madde uydurulmadı. AAE MRONJ sayfası ve NHS çekim sayfası getirildi. | İletişim bölümünde “Açık alanı incelemeden adını kesin koymayalım” sözü yanlış biçimde ilaç adını koymamak diye yeniden anlatıldı. Kaynak kapsamı kısmi; NHS erken iyileşme metninin aylar süren vakaya uygulanabilirliği açıkça doğrulanmamış olarak gösterildi. |
| Planlanan 46 çekimi / ileride implant | Yarınki 46 çekimi ve gelecekte görüşülecek implant plan olarak kaldı. Bugün çekim/implant yapılmadığı korundu; yapılmış çekim diş işareti gösterilmedi. Asistanın 47 dolgusu hekim teyidi sorusuna taşındı. Randevu karşılıklı kabul eksik; otomatik onay yok. | 47 “üzerinde” dolgu yerine “yanında” dolgu paraphrase hatası var. EFP implant sonrası 2–6 aylık iyileşme alıntısı, çekim sonrası iyileşme planıyla uyumlu diye bağlandı; bunlar aynı iyileşme dönemi değildir. Bu hasta-kaynak uygulanabilirlik kusuru çözülmüş sayılmıyor. |

Güvenli operasyon kayıtları: ilk çıkarım 11:47:40Z, `candidates=7 grounded_fields=4`; araştırma `stop=max_tokens blocks=17`; final 11:48:26Z `sources=2 accepted=2`. İkinci çıkarım 11:48:29Z `candidates=7 grounded_fields=3`, randevu `acceptance_missing`; araştırma `stop=max_tokens blocks=24`; final 11:49:08Z `sources=2 accepted=2`. Kabul sayısı yalnız alıntı/alan kontrolünün sonucudur, klinik doğruluk puanı değildir. Her iki UI sonucu kısmi kapsam uyarısını gösterdi.

İlk somut iletişim kusuru için modelden gelen yanlış paraphrase ile gerçek normalizer üzerinde RED test yazıldı ve başarısızlığı izlendi. `clinician_response` artık yalnız dayanaklı birebir yanıtı gösterir; doğrulanmamış yeniden anlatım önerisi yayımlanmaz. Hasta kaygısı önerileri ve ayrı klinik hekim iddiası kontrolü değişmedi. Bu önlem klinik alanların tümündeki paraphrase sorununu veya final kaynak uygulanabilirliğini çözmez. Son değerlendirme zaten iletişim dayanağı olarak birebir alıntıyı alır; bu korunur.

Doğrulama: 461 Python testi geçti (2 bağımlılık deprecation uyarısı, 15.04 s); Node26.12.1/jsdom30.1.3 ile 11 Node dosyası geçti (3.29 s). Bağımsız inceleme 74 odaklı testte engel bulmadı; yalnız boş öneriye ait kozmetik etiket kaldığını belirtti. Yeni düzeltmenin dağıtımı ve aynı canlı vakanın tekrarı aşağıda ayrıca kaydedilmelidir; bu bölüm kendi başına yeni düzeltmenin canlı olduğunu iddia etmez.


## 1 Kasım — seçilmiş özet görseliyle karşılaştırma

Kullanıcının önceki “Dental AI muayene özeti.png” görseli açılıp üretimde yeniden oluşturulan gerçek sentetik sonuç ekranıyla karşılaştırıldı. Canlı durum uzun, sürekli açık paragraflar ve üstte kayıt formu gösteriyordu; seçilmiş açılır kart hiyerarşisi uygulanmamıştı. Yerel değişiklik: klinik özet, kontrol noktaları, iletişim ve sorular native details/summary kartlarına ayrıldı; öğe sayıları gösteriliyor; birebir aynı özet/dayanak tekrarı kaldırıldı. Kontrol, hasta dayanağı, eksik bilgi ve seçenek ayrı etiketlerle; her kontrolün gerçek belge alıntısı ve bağlantısı kendi açılır satırında. Kaynak kapsamı/eksiklik uyarıları varsayılan açık klinik kartta kalır. Kayıt seçimleri, dişler ve randevu tek açılır bölümde, değerlendirmeden sonra; mevcut açık hekim onayı kapısı korunur. Boş iletişim önerisine ait boş etiket de kaldırıldı.

Entegre gerçek Jinja paneli/jsdom testi önce “Clinical summary must be a native collapsible card” ile başarısız oldu. Düzeltmeden sonra aç/kapat, literal alıntı ve bağlantı, tekrarsız özet, onaylı seçimin aynı payload ile kaydı ve kart açınca tek final çağrısı kalması test edildi.11 Node dosyası geçti. Bu görsel düzenleme klinik yorum doğruluğunu düzeltmez; yeni dağıtım sonrası gerçek ekran ayrıca doğrulanmalıdır. Piksel eşitliği veya gerçek mobil cihaz/mikrofon testi iddiası yok.

#224 iletişim düzeltmesi 2f26d4d5, dep-dbjl8ibncjis73dmthvg ile18:03:28 İstanbul'da live doğrulandı. Aynı kemik ilacı vakasının yeni gerçek koşusu: çıkarım15:04:02Z, araştırma15:04:25Z max_tokens/14blok, final15:04:40Z sources1 accepted0. Bu kez yalnız değerlendirilmemiş yayın metni getirildi, UI kaynaklı kontrol üretmediğini açıkça bildirdi. Önceki başarılı AAE koşusu bu nedenle tutarlılık kanıtı değildir. İlacın aktifliği korundu; yeni iletişim yanıtı birebir gösterildi ve yanlış ilaç-adı paraphrase görünmedi; aynı belirsiz hekim sözü bu sefer klinik plan/bulgu alanında yer aldı. Dar normalizer regresyonu bütün yeniden anlatımları veya alan sınıflamasını çözmüş sayılmaz.

Arayüz değişikliği sonrası tam sesli snapshot Python koşusu:461 passed,2 bağımlılık uyarısı,16.61s. Bağımsız arayüz incelemesinde kayıt/gizlilik/çağrı engeli bulunmadı; klinik seçenek etiketi koşullu anlamını koruyacak şekilde bırakıldı.


## #225 sonrası gerçek ekran doğrulaması

#225 fb041879, Render dep-dbjlcj3m8hqs73ftika0 ile18:11:54 İstanbul'da live doğrulandı. Mevcut kimliksiz düşen dolgu/üç konuşmacı sentetik vakası yeni sayfada yeniden çalıştırıldı. Operasyon kayıtları:15:12:38Z çıkarım,4atomik aday/2alan;15:13:00Z araştırma max_tokens/24blok;15:13:10Z final sources1/accepted0. ADA Materials for Direct Restorations bağlantısı gerçekten açılır Kaynaklar grubunda gösterildi; bu koşuda kaynaklı klinik kontrol üretilmediği ve kapsamın kısmi olduğu açıkça yazıldı. Önceki aynı vakada1kontrol çıkması ile bu fark tutarlılık eksikliğini korur.

Gerçek tarayıcı DOM ve ekranıyla doğrulanan adımlar:
1. Klinik bulgular kartı açıldı;2öğe ve tekrarsız özet görüldü. Eş/asistan rahatsızlığı hastaya eklenmedi. Durum: çalıştı; planın bulgular alanına konması hâlâ açık.
2. Kaynaklar kartı açıldı; gerçek ADA bağlantısı ve meslek kuruluşu etiketi görüldü. Durum: çalıştı; vaka-kaynak uygunluğu bu görsel testle doğrulanmadı.
3. Kayıt alanları kartı açıldı, yalnız başvuru alanı seçildi; hekim onayı boşken Kaydet tıklandı. UI “Seçilen alanları kontrol edip onay kutusunu işaretle.” diyerek engelledi. Sonra seçim kaldırıldı; pozitif klinik kayıt yapılmadı. Durum: onaysız kayıt engeli çalıştı.
4. Kartlar kapatıldı; eksik kaynak/kontrol yok uyarıları varsayılan açık klinik kartta görünür kaldı. Yerel gerçek ekran kanıtı: voice-summary-live-cards-final-20261101.jpg (görüntünün kapsamı sonuç ekranının alt bölümü); önceki ekran voice-summary-live-before-20261101.jpg. Tam sayfa ek görüntü isteği tarayıcı protokol zaman aşımıyla alınamadı; mevcut gerçek ekran görüntüsü kullanıldı. Durum: kart hiyerarşisi doğrulandı, piksel eşitliği iddiası yok.

Erişilebilirlik sınırı: native summary kontrolleri aç/kapat anlamı ve odak stili taşıyor; klavye/ekran okuyucu ve fiziksel mobil cihazda eksiksiz erişilebilirlik testi yapılmadı. Gerçek mikrofon/ASR, pozitif hekim kaydı,24vaka×5tekrar ve hekim altın seti hâlâ tamamlanmadı. Arayüz klinik kaynak uygulanabilirliği kusurlarını çözmez.
