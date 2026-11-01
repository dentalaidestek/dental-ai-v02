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
