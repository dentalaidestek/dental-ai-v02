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
