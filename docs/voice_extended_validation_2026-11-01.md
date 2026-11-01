# Uzun günlük konuşma testleri — 1 Kasım 2026

Bu testler gerçek hasta içermez. Önceki vaka esinli sentetik diyaloglar uzatılmıştır; klinik altın set değildir. Beklenen sonuçlar model girdisine eklenmez.

| Vaka | Replik | Yapay ses süresi | Bölüm | Sınanan durum |
| --- | --- | --- | --- | --- |
| bone-medicine-extended | 26 | 5 dakika14 saniye | 5 | Günlük hap yok / aktif hastane ilacı, kapanmayan yara, alerji ve belirsizlik, asistanın kendi şikâyeti, korku/ücret konuşması |
| crown-plan-extended | 24 | 4 dakika43 saniye | 4 | Elde getirilen kaplama / aspirasyon yok,46→47 düzeltmesi,46eski dolgu, geçmiş ilaç, reddedilen yarın randevusu, yapılmamış çekim/implant |
| implant-gums-extended | 24 | 4 dakika55 saniye | 4 | Fırçalamada var/kendiliğinden yok kanama, babanın diyabeti, asistanın kendi şikâyeti, belirsiz hareketlilik, yapılmamış ölçüm/film/temizlik |

Toplam yaklaşık14dakika52saniye ses,74replik;13bölümün her biri26–77saniye ve8MB altında. Her konuşmacı için farklı Türkçe yapay ses kullanıldı; “Hasta/Hekim/Asistan” etiketleri sesli okunmadı. eSpeak tabanlı yapay ses gerçek insan konuşması, gerçek ortam gürültüsü veya fiziksel mikrofon değildir. Bölümler tüm replik sınırlarında ayrıldı, tek bir replik kesilmedi. Süreler/sha256: tests/fixtures/voice_extended_audio_manifest.json. Gerçekçi olmayan sistem-test yönlendirmeleri repliklerden çıkarıldı; aidiyet ve düzeltmeler günlük konuşma bağlamında bırakıldı.

Başlıklar sadeleştirildi: “Görüşmeden çıkan bilgiler”, “Kaynaklara göre kontrol edilecekler”, “Hastayla iletişim”, “Netleştirilecek sorular”, “Kaydedilecek bilgiler”. Tedavi yapıldığı/kararlaştırıldığı izlenimi veren başlık kullanılmıyor. Sıfır öneri, risk yok diye sunulmuyor.

Değerlendirme aracının12replik sınırı48e yükseltildi;49reddedilmeye devam ediyor.48replik için önce başarısız test görüldü, sonra düzeltildi. Üretimde ses bölümünün90saniye/8MB ve metin sınırları değiştirilmedi. Çevrimdışı envanter3vakayı doğruladı, model_calls=0; bu model/klinik başarısı değildir.

Başlık ve test aracı değişikliği sonrası462Python/11Node geçti. Canlı ses aktarımı, metinle karşılaştırma ve değerlendirme bulguları aşağıda ayrı kaydedilecek; üretilmiş dosya olması canlı testin geçtiği anlamına gelmez.


## Gerçek üretim koşuları — #227

#227 664cc917, dep-dbjlpo3ncjis73dnggtg ile18:39:53 İstanbul'da live doğrulandı.13ses bölümü gerçek arayüzden gönderildi. Üç konuşma da metne birikti, aktarım boyunca değerlendirme paneli kapalı kaldı; klinik çıkarım yalnız bitirme düğmesiyle başladı. İmplant vakasının ikinci ses bölümü ilk denemede422/meşgul görünümü verdi; önceki803karakter metin ve bekleyen ses korundu, tek açık yeniden denemede aynı bölüm eklendi.13başarılı ses aktarımı için toplam14deneme yapıldı. Kaplama finali ilk seferde başarısız oldu; yalnız son değerlendirme yeniden çalıştırılarak kısmi sonuç alındı. Son hata nedenini doğrulamak için Render log sorgusu denendi,503/Loki erişim hatası döndü; kök nedenin kota, süre veya çıktı sınırı olduğu iddia edilmiyor.

| Koşu | Gerçek son durum | Korunanlar / sorunlar |
| --- | --- | --- |
|5:14kemik ilacı sesi |3528karakter;2kaynak/4kontrol; kısmi | Çekim yeri süresi korunuyor; ancak asistanın kendi yakınması hastanın şikâyetine eklendi. Ses metninde kemik ilacı “kemoterapi” oldu, “sol alt” yalnız “sol” oldu. Bir devam eden tedavi cümlesi “Geçen ay bittim” diye bozuldu. Özgül kemik ilacı konusu bu girdide kayboldu. |
|4:43kaplama sesi |3159karakter;3kaynak/1kontrol; final yeniden denemesinde kısmi |47/46ayrımı kısmen korunuyor, kesin diş etiketi üretilmedi. Reddedilen randevu onaylanmadı, çekim/implant yapılmış sayılmadı. Ancak “gelemem” sesi “geleceğim”, “çıkan kaplama” sesi “çürük kaplama” oldu. Çıkarım “bakmadan yapıştırma” olumsuzluğunu da yanlış yeniden anlattı. |
|4:55implant sesi |3272karakter;3kaynak/3kontrol; kısmi | Babanın diyabeti hastada kesin tanıya dönüşmedi; hareketlilik belirsiz kaldı, işlem/ölçüm uydurulmadı. ASR “kanama derdim” sözünü “kanal tedavim” yaptı; bu yüzden olmayan kanal tedavisi hasta alanına girdi. Asistanın kanaması ve arkadaş hakkında anlatı da hasta alanlarına sızdı. |
|Aynı26replik özgün, rol etiketli metin |3905karakter;2kaynak/3kontrol; kısmi | Sol alt, kemik tedavisi ve aktif tedavi bağlamı daha iyi korundu. Buna rağmen asistanın diş sıkması “hasta öyküsü değil” açıklamasıyla tıbbi öyküye kondu. Hekimin ilaç sorusu da mevcut ilaç gibi kayda aday oldu. Demek ki hata yalnız ASR değildir. |

Bütün koşullarda kaynak erişimi/kapsamı kısmi. Kontrol sayıları klinik doğruluk veya başarı puanı değildir. Erken çekim sonrası kaynakların aylar süren açık alana uygulanması, ilgisiz alt konular, fazla iletişim/soru tekrarları ve koşullu planın hatalı yeniden anlatılması açık bulgulardır. Bu robot sesleriyle ölçülen sonuç insan sesi başarı oranı değildir; ses motorunun Türkçe artikülasyonu da deneyin bir sınırıdır. ASR'deki yanlış sözcük/olumsuzlukların düzeldiği iddia edilmiyor.

Hiçbir alanda hekim onayı verilmedi; seçili kayıt alanı sayısı ve hekim onayı tüm koşularda0/false. Pozitif hasta kaydı yapılmadı. Diş etiketi ve randevu da kaydedilmedi. Ham sentetik ASR metni ve kaydedilebilir alanların değişiklik öncesi anlık çıktısı: docs/voice_extended_results_2026-11-01.json. Tam final-source metni bu dosyaya kopyalanmadı.

## Bulgu sonrası doğrulamalar

1. PLANNED olarak gelen clinical_findings artık plan alanına yönlendirilir; geçmiş/güncel bulgular ve planlanan ilaç defteri ayrı kalır. Aynı planı taşıyan eski fields.clinical_findings yolu da geçersiz bırakılır. “Film çekelim mi?” gibi koşullu inceleme sorusu korunur.
2. Atomik klinik bilgiye subject PATIENT/OTHER/UNKNOWN eklendi. Konuşan değil bilginin kime ait olduğu istenir. İlaç adının bilinmemesi ilacın sahibinin bilinmemesi değildir. OTHER/UNKNOWN dayanakları hasta alanlarına, aynı alıntıya dayalı kaynak rotasına, dişlere ve iletişim çıkarımlarına alınmaz. PATIENT ile başka kişi alıntıları örtüşürse veri sessizce kaybolmaz; açık aidiyet hatası ve taslak korunması gösterilir.
3. Soru işaretiyle biten salt hastalık/ilaç/alerji/bulgu sorusu hasta beyanı yerine kullanılamaz. Koşullu işlem planları bu filtreden çıkarılır.

Bu, modelin verdiği aidiyet etiketini denetler; bağımsız ses konuşmacısı doğrulaması değildir. Eski etiketsiz normalizer girdileri uyumluluk için desteklenir. Model yanlış PATIENT etiketi koyarsa veya ASR konuşmayı değiştirirse bütün hataları yakaladığı söylenemez. Kaynak uygunluğu ve serbest klinik paraphrase problemleri tamamen çözülmedi.

Önce başarısız testler görüldü: plan/bulgu, OTHER/UNKNOWN kayıt ve kaynak sızıntısı, sorudan ilaç üretme; bağımsız incelemede bulunan eski alan yolu, örtüşen alıntı ve koşullu soru sıralaması da ek RED/GREEN testleriyle giderildi. Son471Python testi geçti(2bağımlılık uyarısı,16.95s); son Node koşusu11dosya geçti. Bağımsız son inceleme83odaklı testte engel bulmadı. Düzeltme sonrası gerçek çıkarım tekrarı ayrıca kaydedilmelidir.

Son aidiyet kontrolü ayrıca başka kişinin ilaç bırakma sözüyle hastanın eski bilgisinin silinmesini, konu/diş silme ve randevu oluşturma yolunu da engeller. Bu ek regresyon önce başarısız oldu;471Python/11Node ve83bağımsız odaklı test geçti.
