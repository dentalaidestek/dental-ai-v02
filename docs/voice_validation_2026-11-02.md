# 2 Kasım 2026 — yayın ve akış doğrulaması

Başlangıç kontrolü: yerelde commit edilmemiş izlenen dosya yok (yalnız Python önbellekleri). Son yerel683cc30; GitHub main f52922e9; Render live43ddb4b1/dep-dbjm7kdg1s2s7384bk1g. GitHub compare API ile43ddb4b1..f52922e9 farkı yalnız dört rapor dosyası; main üzerindeki son uygulama kodu canlı; bu kontrol eski açık dalları kapsamıyordu. Sonraki PR215 incelemesi aşağıdadır. Render servisi My Workspace/dental-ai-v02, main ve otomatik commit dağıtımı. İlk gerçek tarayıcı isteğinde Render ücretsiz servis uyanma ekranı görüldü; bu kodun yayımlanmaması anlamına gelmez.

Açık plan eksikliğinin kökünü ayırmak için yalnız sayısal tanılama eklendi: plan aday sayısı, geçerli alıntı sayısı, PATIENT/OTHER/UNKNOWN/eksik etiket sayıları ve çıktıdaki plan varlığı. Konuşma, ilaç adı, serbest model alanı veya kimlik bilgisi loglanmaz. Üç regresyon önce başarısız oldu, sonra474Python ve11Node geçti (iki mevcut bağımlılık uyarısı). Tanılamanın varlığı klinik hatanın giderildiği anlamına gelmez; gerçek koşu sonuçları aşağıda kaydedilecektir.


## Eski dal denetimi ve düzeltmeler

PR215 hâlâ açık ve main ile çakışıyor. Tamamının canlı olduğu söylenemez. Eski ses denetleyicisini doğrudan taşımak canlı bölüm başına klinik çıkarımı geri getireceği, yeni kaynak/parmak izi/konuşmacı kontrollerini kaybettireceği için uygulanmadı. Eski istek kuyruğu ve sağlayıcı slotu için iptal/lease temizliği ayrıca uyarlanmalı; eski sağlayıcı slotunda tekrarlanan iptalde sızıntı riski incelemede bulundu. Bunlar yayımlandı diye sayılmıyor.

Eksik iki bağımsız onarım taşındı: mobil mesaj adaptörü offload edilmiş async yanıtı await eder; oturum veya bearer ile klinik yanıtlar açık immutable cache başlığına rağmen private,no-store olur. Gerçek mobil kök /api/mobile/v1 kullanıldı; profil/statik açık cache politikası korunur. On test gerçek handler gövdelerini izole çalıştırır; tam uygulama/Android uçtan uca doğrulaması değildir.

## Plan kaybı: gerçek sağlayıcılı canlı tanılama

PR230/main751a10ba, Render dep-dbk1nuqvcj2c73fhovc0 05:15:16Z live. Aynı 26 turluk3905karakterlik bone-medicine-extended metni QA11 ekranında çalıştırıldı. 05:17:36Z tanılama: candidates=0 anchored=0 patient=0 other=0 unknown=0 missing=0 recorded=0. Model hiç plan adayı üretmedi; filtre kaybı değil. 05:18:31Z final: sources=2 accepted=3. Ekranda kısmi kaynak uyarısı var; sonuç tamamlanmış klinik kontrol kabul edilemez. Son model, konuşmada açıklama/durma hakkı olmasına rağmen bazı iletişim açıklamalarını eksik saydı; açık kalite sorunu olarak kalıyor.

Çıkarım talimatına günlük dildeki inceleme/film/ilaç listesi doğrulama planları açıkça eklendi. Sunucu anahtar kelimelerden plan icat etmez. Üç uzun vakada plan alanı artık zorunlu test beklentisi; kaynak konusu doğru olsa bile plan yoksa test başarısız. Bu alan varlığı denetimi, planın klinik doğruluğunu kanıtlamaz. Dört yeni test düzeltmeden önce başarısız oldu.

Yerel doğrulama:488Python geçti; iki mevcut bağımlılık uyarısı. Node sonucu ve yayın sonrası gerçek tekrar ayrıca kaydedilecek. Gerçek mikrofon, insan tarafından onaylı altın set ve uzak CI yeşilliği kanıtlanmış değildir. Hasta dosyasına kayıt onaylanmadı.

## PR231 gerçek yayın sonrası tekrar

Render dep-dbk1tpnb9u1s73c8vfbg, uygulama commit2957bfcd, 05:27:33Z live. Üç vaka aynı QA11 hasta ekranında bağımsız geçici sayfalarda özgün rol etiketli metinle çalıştırıldı; kayıt onaylanmadı. Bunlar gerçek sağlayıcı çağrısıdır, mikrofon/ASR koşusu değildir.

| Vaka | Gözlenen sonuç | Açık sorun |
| --- | --- | --- |
| Kemik ilacı,26tur | Plan artık var: muayene, ilaç listesi/tarih, hastane kaydı. Aktif hastane tedavisi korundu; asistanın diş sıkması hasta alanına alınmadı.3kaynak,5kontrol | Kaynak kapsamı kısmi. Plan içinde “muayene bulgusu henüz paylaşılmadı” gibi plan olmayan model ifadesi var; alan varlığı klinik doğruluk değil. |
| Çıkan kaplama,24tur | Muayene/gerekirse görüntü planı; çekim/implant kararı yok ayrımı; geçmiş antibiyotik. Reddedilen yarın randevusu otomatik oluşturulmadı.2kaynak,2kontrol | “üstündeki kaplama” modelce “üstteki” diye yazılıp üst çene/47 yanlış çelişkisine dönüştü. Alerji beyanı yanlışlıkla sistemik öyküye yazıldı. |
| İmplant kanaması,24tur | İki ayrı çıkarım denemesi de PATIENT/OTHER alıntı çakışmasında durdu; tam metin korundu, yeni deneme düğmesi açıldı | Final değerlendirme üretilmedi; başarılı vaka diye sayılamaz. Çakışmanın ham model yanıtı loglanmadığı için hangi alıntının çakıştığı belirlenmedi. |

Görünür DOM kanıtları voice_live_results_2026-11-02.json içinde. Kaynak sayısı, doğru klinik uyarı oranı değildir. Sonraki daraltılmış alıntı düzeltmesinin sonucu ayrıca kaydedilecek.

## Uzak CI ve fixture izolasyonu

PR231/main2957bfcd için GitHub Actions run41393991682 bu kez adımları gerçekten çalıştırdı. contract-tests ve ready-model-contract başarılı; application-regressions5toplama hatasıyla durdu: gerçek app.main tabloları ile test_voice_exam sahte User tablosu aynı global SQLModel metadata'sında çakıştı. postgres-integration42geçti/2başarısız: akademik arama testi MAX_SOURCE_SEARCHES+1 reddi bekliyor, üretim bilerek konu+ifade birleşimi için2*MAX_SOURCE_SEARCHES kabul ediyor. Bu farklı sorundur; üretim sınırı test yeşillensin diye düşürülmedi.

PR232 yalnız test izolasyonu: özel registry, altı sahte model ve gerçek WorkJob şemasının özel metadata'ya eşlenmiş kopyası. Üretim metadata'sı temizlenmez/değişmez; monkeypatch fixture sonunda geri gelir. Ayrı subprocess regresyonu önce aynı User çakışmasıyla başarısız oldu, sonra489Python geçti; bağımsız128test geçti. Main88772e5e [skip render] ile birleştirildi; çalışma kodu değişmediğinden Render2957bfcd kalması beklenir. Uzak son kontrol sonucu ayrıca kaydedilecek.

PR232 sonrası uzak application-regressions job125113365383 tam toplama/koşuya ulaştı:1952geçti,43başarısız,48atlandı,594alt test geçti. Önceki beş voice toplama hatası yok, başarısız listede test_voice dosyası yok. Genel CI hâlâ kırmızı; akademik/çalışma akışı hatalarının bu sesli düzeltmelerle çözüldüğü iddia edilmez. Bu somut sonuç eski “hiç adım başlamıyor” sınırının güncel koşuda geçerli olmadığını gösterir; geçmiş başarısızlıkların nedeni için geriye dönük tahmin yapılmaz.

## Son dar düzeltme: PR233

İki başvuru şikâyeti regresyonu (eski fields ve atomic clinical_facts yolu) yanlış çene eklenen model paraphrase'ini önce kabul etti ve başarısız oldu. Artık chief_complaint özgün alıntı metnini korur; aynı yaklaşım zaten ilaçlarda kullanılıyordu. İki eski aidiyet testi literal hasta cümlesini bekleyecek şekilde güncellendi, OTHER/UNKNOWN dışlama kontrolleri korundu. Bir cümlede baba/hasta anlatımını ayrı kesintisiz cümlecikler halinde alıntılaması modelden açıkça istenir; mevcut çakışma reddi gevşetilmez. Ayrı cümleciklerin hasta olumsuz beyanını koruduğu test edildi.492Python geçti;11Node aynı istemci kodunda geçti. Bağımsız incelemede kod engeli bulunmadı. Klinik alerji kategorisi/plan olmayan plan maddesi ve final iletişim yanlış alarmları bu değişiklikle çözüldü sayılmaz.


PR233 Render dep-dbk22kavcj2c73fi399g, commit2abdbb4e 05:38:03Z live. Yayın sonrası kaplama ve implant özgün metinleri yeniden gönderildi. PR231 bone sonucu ekranında onay kutusu işaretlenmeden kaydet düğmesine basıldığında “Seçilen alanları kontrol edip onay kutusunu işaretle.” gösterildi; kayıt yapılmadı.

PR233 baş commitb6322c64 için uzak **voice** job125114274998 başarıyla tamamlandı; Python ve Node adımları gerçekten çalıştı, Node11geçti/0başarısız. Bu, önceki “sesli uzak CI yeşil değil” kaydını bu commit için günceller; bütün site CI'sının yeşil olduğu anlamına gelmez. Aynı başta application-regressions/postgres-integration ve akademik testler içeren static-safety başarısız kaldı. Yerel492test sayısı tüm sesli snapshot Python dosyalarını kapsar; uzak voice komutu yalnız tests/test_voice*.py seçer.

Son uzak voice jobunda482Python ve11Node geçti; yereldeki ek10test mobil/cache handler testidir. İmplant özgün metni PR233 sonrası üçüncü toplam denemede de aynı aidiyet çakışması hatasıyla durdu. Kısa cümlecik prompt'u bu gerçek vakayı çözmedi. Başarılı gibi işaretlenmez; daha fazla kör ücretli tekrar yapılmadı. Metin kaybı görülmedi. Kaynak/final aşamasına ulaşmadı.

### Son yayın sonrası kaplama sonucu

PR233/2abdbb4e üzerinde özgün24turluk kaplama metni tekrarlandı: başvuru şikâyetinde “meğer üstündeki kaplama çıkmış” korunuyor; önceki üst çene/47 çelişki kartı bu koşuda yok.47düzeltmesi,46eski dolgu/yeni işlem yapılmadı ayrımı ve muayene/gerekirse görüntüleme planı korunmuş. Alerji bu sefer doğru alanda, ancak bu kategorileme için ayrı deterministik düzeltme yapılmadı; tek koşu tutarlılık kanıtı değildir. Yarın için randevu oluşturulmadı.2kaynak ve0dayanaklı kontrol; ekranda “Bu, risk olmadığı anlamına gelmez.” ve kısmi kapsam uyarısı var. Sonuç klinik güvenlik onayı değildir.

## Tamamlananlar ve açık kalanlar

- Yayın kontrolü: son çalışma kodu2abdbb4e ile Render live SHA birebir doğrulandı. Daha sonraki rapor/test-only commitlerinin çalışma kodu farkı yoktur.
- Canlı model/metin UI testi: PR230tanılama1, PR231sonrası4, PR233sonrası2 = toplam7gerçek çıkarım denemesi. Bunların3ü aynı implant vakasında engellendi; başarılı final üretilmiş gibi sayılmaz. Altı yayın sonrası denemenin tam görünür DOM çıktıları JSON'da, ilk tanılama koşusu operasyonel sayaç ve yukarıdaki ekran gözlemleriyle kaydedildi.
- Kayıt kapısı canlıda onaysız kaydı engelledi. Hiçbir hasta alanı veya randevu onaylanıp kaydedilmedi.
- Yerel492Python/11Node geçti; PR233başında uzakvoice482Python/11Node geçti. Genel site CI hâlâ kırmızı ve akademik hatalar ayrı açık konu.
- Açık: implantta aidiyet çakışması, klinik alan/plan kategorileme hataları, final iletişim yanlış alarmları, kısmi kaynak kapsamı, gerçekmikrofon/insan konuşması ve hekim onaylı altın set doğrulaması. EskiPR215kuyruk/lease çalışması tam taşınmış sayılmıyor.

Bu nedenle yayın tamamlandı, sınırlı test kampanyası çalıştırılıp başarısız vakalar kaydedildi; klinik akışın tamamının sorunsuz olduğu veya bütün eski dalların eksiksiz yayımlandığı söylenemez.
