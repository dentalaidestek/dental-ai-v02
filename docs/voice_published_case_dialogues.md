# Kaynaklı gündelik Türkçe sesli muayene senaryoları

Tarih: 31 Ekim 2026. Durum: taslak; hekim onayı bekliyor.

12 yayımlanmış vaka başlangıç fikri olarak kullanıldı; 12 karşılaştırma ile toplam 24 özgün konuşma ve 192 replik hazırlandı. Ayrıca iki mesleki kılavuz başvurusu var. Hasta kimliği ve gerçek hasta konuşması içermez. Asistanın replikleri, yeni belirtiler, işlem planları ve karşılaştırmalar kurgudur; yayımlanmış olguya ait birebir çeviri değildir.

Bu paketin amacı konu seçimi, alıntı dayanağı, konuşmacı atfı ve yanlış alarm kontrolüdür. Kaynakta anlatılan tedaviyi güncel standart saymaz. Beklenen konu kimlikleri ve klinik kontrol listeleri hekimce onaylanmış altın etiket değildir. Tüm diş hekimliğini kapsayan bir doğruluk örneklemi değildir; 10 noktalı taksonomi dalı ve ayrıca eski konu kimlikleri var.

## Çalıştırma ve dürüst ölçüm

```bash
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py --fixture tests/fixtures/voice_published_case_dialogues.json
PYTHONPATH=.:../testdeps python scripts/evaluate_voice_spoken.py --fixture tests/fixtures/voice_published_case_dialogues.json --live --limit 24 --repeat 5 --max-calls 120
```

İlk komut yalnız envanter/şema kontrolüdür, diyalogların modelce doğru çözüldüğünü göstermez. İkinci komut yapılandırılmış mevcut çıkarıcıyı kullanır; 120 üst seviye çıkarım çağrısı bütçesidir, sağlayıcı devam çağrılarının kesin HTTP/token/maliyet üst sınırı değildir. Beklentiler, kaynak listesi ve inceleme notları modele verilmez. 31 Ekim denemesi `missing_provider_configuration`, `model_calls=0`, çıkış 2 ile durdu. Gerçek çıkarım veya kaynak getirme/final değerlendirme başarı oranı raporlanmadı.

Otomatik araç yalnız yönlendirilen konu kimliğini, birebir alıntı dayanağını, belirli hekim atıflarını ve belirsizlik sorusunu puanlar. Nihai klinik uyarının uygulanabilirliğini, hastaya/asistana ait tüm klinik bilgilerin ayrımını ya da kaynak kalitesini bu komut otomatik puanlamaz. Aşağıdaki kontrol listeleri gerçek final çıktı üzerinden hekim tarafından incelenmelidir. Sonra onaylanmış eksiksiz etiketler ve gerçek koşu sonuçları `scripts/score_voice_clinical_review.py` biçimine aktarılabilir. Bu dosya kendiliğinden o araca onaylı veri sağlamaz.

## Hekim incelemesi

Her konuşmayı önce metinle, sonra üç kişi sırayla seslendirerek deneyin. Gerçek ses denemesinde konuşmacı etiketleri otomatik doğru kabul edilmemeli. İşitilmeyen ilaç adı veya diş numarası tamamlanmamalı. Çıkarım, getirilen kaynak ve nihai yorum ayrı ayrı kaydedilmeli; hatalı ve başarısız koşular da rapora girmeli.

Her koşuda kontrol: hasta bilgileri / diğer kişilerin bilgileri; mevcut / geçmiş / olumsuz / planlı ayrımı; beklenen ve beklenmeyen uyarılar; eksik bilgi soruları; hekim iddiası doğrulanmadı ile yanlış ayrımı; kaynak pasajının bu hastaya uygulanabilirliği; onay öncesi kayıt yapılmaması. Hata ve yeniden deneme için metin korunmalı; başarılı aşamanın ücretli çağrısı tekrarlanmamalı.

**Acil senaryoların sınırı:** Mevcut mimari bitişte değerlendirme yapar. Kayıp kaplama-solunum sorunu veya hızla artan şişlik-yutma sorunu senaryosu gerçek zamanlı acil alarm doğrulaması değildir. Konuşma içinde hekim/asistan acil işlemi başlatır; kaynak araması için bekleme talimatı verilmez.

## Diyaloglar

### persistent-denture-ulcer-index — Takma dişin altındaki yara — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: denture-ulcer, ada-lesions. Karşılaştırma: `persistent-denture-ulcer-contrast`.

**Hasta:** Alt damağımın altında bir yara var, haftalardır kapanmıyor.

**Hekim:** Takma dişi çıkardığınızda da devam ediyor mu?

**Hasta:** Bir süredir hiç takmıyorum ama yara aynı, bazen kanıyor.

**Asistan:** Hocam, önceki kontrolde de aynı yeri söylemişti.

**Hekim:** Takma diş vurmuştur, başka bir şey olamaz.

**Hasta:** Ama çıkardım, yine düzelmedi. İçim rahat etmedi.

**Asistan:** Ne zamandır sürdüğünü ve takmadığını not ediyorum.

**Hekim:** Yarayı tekrar inceleyelim, gerekirse ileri değerlendirmeyi konuşalım.

Korunması gereken bilgi: Protez kullanılmadığı halde süren yara; Hasta kaygısı.

Çıkarılmaması gereken sonuç: Kesin kanser tanısı; Hekimin kesinlik iddiasının doğrulandığı.

Hekim incelemesi: Devam eden yaranın yalnızca protez vuruğu diye kapatılmaması; Hekimin kesinlik iddiasını ayrı incele.

Beklenen konu grupları (taslak): prosth.removable; oral_medicine.cancer / oral mucosal lesion diagnosis / oral_medicine.general.

### persistent-denture-ulcer-contrast — Takma dişin altındaki yara — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: denture-ulcer, ada-lesions. Karşılaştırma: `persistent-denture-ulcer-index`.

**Hasta:** Yeni takma diş dün takıldı, altı sürtüyor.

**Hekim:** Çıkarınca nasıl oluyor?

**Hasta:** Çıkarınca rahatlıyor. Daha önce orada yara yoktu.

**Asistan:** Hocam, dün ilk teslimini yaptık.

**Hekim:** Vuran yerini ve ağzın içini kontrol edelim.

**Hasta:** Kanama yok, ama takınca canımı acıtıyor.

**Asistan:** Kontrol için geliş gününü yazayım mı?

**Hekim:** Evet, düzelmezse yeniden değerlendirelim.

Korunması gereken bilgi: Dün başlayan, çıkarınca hafifleyen sürtünme.

Çıkarılmaması gereken sonuç: İlk vakadaki haftalar süren yaranın bu hastaya taşınması; Kesin iyi huylu tanı.

Hekim incelemesi: Muayene ve takip planını koru; vaka raporundaki tanıyı kopyalama.

Beklenen konu grupları (taslak): prosth.removable.

### canal-burning-index — Kanal temizliği sırasında yanma — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: irrigant-accident. Karşılaştırma: `canal-burning-contrast`.

**Hasta:** Geçen hafta dişin içi yıkanırken birden cayır cayır yandı.

**Hekim:** Sonrasında neler oldu?

**Hasta:** Damağım şişti, sonra et açıldı, sert beyaz bir yer görünüyor.

**Asistan:** Hasta yanmanın tam yıkama sırasında başladığını söylüyor hocam.

**Hekim:** Yıkamada kullanılan sıvıyı ve yapılan işlemi kontrol edelim.

**Hasta:** Normal işlem ağrısıdır diye bekledim, geçmedi.

**Asistan:** Eski işlem kaydını isteyeyim, şimdi de durumu not ediyorum.

**Hekim:** Ağız içini değerlendirelim, hasarın boyutu konuşmadan anlaşılamaz.

Korunması gereken bilgi: Yanmanın işlem sırasında başlaması; Sonrasında şişlik ve açık doku bildirimi.

Çıkarılmaması gereken sonuç: Kesin sıvı türü veya alerji; Konuşmada olmayan nekroz boyutu.

Hekim incelemesi: İşlem komplikasyonu için kaynak ara; Vaka raporundaki ilaç/dozu bu hastaya kopyalama.

Beklenen konu grupları (taslak): endo.general; emergencies.general / oral mucosal lesion diagnosis.

### canal-burning-contrast — Kanal temizliği sırasında yanma — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: irrigant-accident. Karşılaştırma: `canal-burning-index`.

**Hasta:** Dün dolgu yapıldı, soğuk su değince kısa bir sızı oluyor.

**Hekim:** Kendiliğinden yanma ya da şişlik var mı?

**Hasta:** Yok, su gidince geçiyor. Etimde açılma da yok.

**Asistan:** Hocam, yapılan işlem dolgu, kanal yıkaması yapılmamış.

**Hekim:** Dolgunun çevresini ve kapanışı kontrol edelim.

**Hasta:** Yemek yerken yüksekmiş gibi de gelmiyor.

**Asistan:** Şikâyetin ne zaman olduğunu kaydettim.

**Hekim:** Muayeneye göre konuşalım.

Korunması gereken bilgi: Kanal yıkaması yapılmadığı; Kısa süreli soğuk sızısı.

Çıkarılmaması gereken sonuç: Kimyasal doku hasarı kesinliği.

Hekim incelemesi: Dolgu sonrası belirtiyi önceki komplikasyonla birleştirme.

Beklenen konu grupları (taslak): restorative.hypersensitivity / restorative.general.

Çıkmaması beklenen konular (taslak): endo.instrument_separation, endo.root_perforation.

### bone-medicine-index — Kemik ilacı ve kapanmayan çekim yeri — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: antiresorptive. Karşılaştırma: `bone-medicine-contrast`.

**Hasta:** Çekilen dişin yeri aylardır kapanmadı, sivri sert bir şey var.

**Hekim:** Düzenli tedaviniz veya ilacınız var mı?

**Hasta:** Kanser için hastanede kemik güçlendirici ilaç veriliyor, adını bilmiyorum.

**Asistan:** Hastane ilaç listesini isteyelim hocam, şu an elimizde yok.

**Hekim:** İlacın adını, veriliş şeklini ve son uygulama tarihini doğrulayalım.

**Hasta:** Başka günlük hap yok, ama hastanede verilen o ilaç devam ediyor.

**Asistan:** Günlük hap yok derken hastane ilacını silmiyorum.

**Hekim:** Açık alanı incelemeden adını kesin koymayalım.

Korunması gereken bilgi: Hastanede uygulanan adı belirsiz aktif ilaç; Günlük hap yok ifadesi önceki tedaviyi iptal etmez.

Çıkarılmaması gereken sonuç: Zoledronat ya da denosumab adını uydurma; Hastaya ilacı kendi kendine kestirme.

Hekim incelemesi: İlaç ve çekim bağlamını ilişkilendir; Açık kemik ve süreyi hekim değerlendirmesine taşı.

Beklenen konu grupları (taslak): antiresorptive medication osteonecrosis jaw; tooth extraction complications.

### bone-medicine-contrast — Kemik ilacı ve kapanmayan çekim yeri — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: antiresorptive. Karşılaştırma: `bone-medicine-index`.

**Hasta:** Geçen ay çekilen dişin yeriyle ilgili kontrol için geldim.

**Hekim:** Açık yer veya ağrı kaldı mı?

**Hasta:** Hayır, kapandı. Bir de kanser için verilen kemik ilacım sürüyor.

**Asistan:** İlaç adını hastane listesinden teyit edelim hocam.

**Hekim:** Sonraki işlemleri planlarken o tedaviyi dikkate alalım.

**Hasta:** Bugün yeni çekim yapılmayacak, değil mi?

**Asistan:** Bugünkü randevu sadece kontrol diye kayıtlı.

**Hekim:** Evet, önce kontrol ve bilgi doğrulama.

Korunması gereken bilgi: Çekim yerinin kapandığı; Yeni çekim yapılmadığı.

Çıkarılmaması gereken sonuç: İyileşmiş yerde mevcut osteonekroz tanısı; İlaç tedavisini unutma.

Hekim incelemesi: Risk araştırmasını mevcut komplikasyon tanısından ayır.

Beklenen konu grupları (taslak): antiresorptive medication osteonecrosis jaw.

### missing-crown-index — Kaplama parçası nereye gitti — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: crown-aspiration. Karşılaştırma: `missing-crown-contrast`.

**Hasta:** Dişi takarken bir şey boğazıma kaçtı, öksürüyorum.

**Hekim:** Nefesiniz nasıl?

**Hasta:** Göğsümde takılmış gibi, rahat nefes alamıyorum.

**Asistan:** Hocam, küçük kaplamayı ağızda da tepside de bulamadım.

**Hekim:** İşlemi durduruyoruz, acil yardım gerekiyor.

**Hasta:** Sanki yuttum ama emin değilim.

**Asistan:** Acil yardım çağrısını yapıyorum.

**Hekim:** Yutulduğunu varsaymayalım; değerlendirme kaynak aramasını beklemeyecek.

Korunması gereken bilgi: Kayıp parça ve solunum yakınması; Yutma ile solunum yoluna kaçmanın belirsizliği.

Çıkarılmaması gereken sonuç: Kesin mideye gitti; Muayene bitene kadar bekleyebilir.

Hekim incelemesi: Acil bulguları görünür tut; bu sistem canlı acil alarmı değildir.

Beklenen konu grupları (taslak): emergencies.general.

### missing-crown-contrast — Kaplama parçası nereye gitti — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: crown-aspiration. Karşılaştırma: `missing-crown-index`.

**Hasta:** Kaplama yerinden çıktı, korktum ama burada elimde.

**Hekim:** Boğaza kaçma veya öksürük oldu mu?

**Hasta:** Olmadı, parça baştan beri avucumda. Nefesim normal.

**Asistan:** Hocam, parçanın tamamı burada görünüyor.

**Hekim:** Altındaki dişi ve parçayı kontrol edelim.

**Hasta:** Tekrar takılabilir mi?

**Asistan:** Önce kontrol edeceğiz, randevuya işlemi yapılmış yazmıyorum.

**Hekim:** Uygunluğuna bakmadan karar vermeyelim.

Korunması gereken bilgi: Parçanın tamamen hastanın elinde olduğu; Öksürük/solunum sorunu olmadığı.

Çıkarılmaması gereken sonuç: İlk vakadaki aspirasyonu bu hastaya taşıma; Kaplama yeniden takıldı.

Hekim incelemesi: Varsayımsal acili gerçek hasta bulgusu sayma.

Beklenen konu grupları (taslak): prosth.cementation / prosth.fixed.

Çıkmaması beklenen konular (taslak): emergencies.general.

### lost-front-tooth-index — Düşme sonrası yerinden çıkan ön diş — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: avulsed-tooth. Karşılaştırma: `lost-front-tooth-contrast`.

**Hasta:** Düştüm, ön dişim köküyle birlikte çıktı, annem süte koydu.

**Hekim:** Ne kadar oldu, bu daha önce değişen büyük dişin miydi?

**Hasta:** Yaklaşık iki saat oldu. Evet, küçükken süt dişim düşmüştü, bu onun yerine çıkmıştı.

**Asistan:** Kabı getirdiler hocam, süreyi yaklaşık diye not ettim.

**Hekim:** Bekletmeden muayene edelim; ne yapılabileceği dişin durumuna bağlı.

**Hasta:** Yerine takılırsa kesin eskisi gibi olur mu?

**Asistan:** Bunu garanti diye yazmayacağım.

**Hekim:** Kesin sonuç sözü veremeyiz, takip de gerekecek.

Korunması gereken bilgi: Kalıcı diş bilgisi; Yaklaşık süre ve sütte taşıma.

Çıkarılmaması gereken sonuç: Kesin kurtulur; Vakadaki tüm işlem basamaklarının bu hastada yapıldığı.

Hekim incelemesi: Travma yönlendirmesi; zaman ve diş türünü koru.

Beklenen konu grupları (taslak): dental trauma management / pediatric.trauma.

### lost-front-tooth-contrast — Düşme sonrası yerinden çıkan ön diş — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: avulsed-tooth. Karşılaştırma: `lost-front-tooth-index`.

**Hasta:** Düştüm, ön taraftan bir parça koptu ama dişim ağzımda.

**Hekim:** Dişin tamamı dışarı çıktı mı?

**Hasta:** Hayır, aynada kalan kısmı görüyorum, sadece köşesi yok.

**Asistan:** Parçayı getirmişler hocam, olay yarım saat önce olmuş.

**Hekim:** Dişi ve çevresini kontrol edelim.

**Hasta:** Kökü de çıktı sanmıştım ama diş duruyor.

**Asistan:** Tam diş çıktı diye kaydetmiyorum.

**Hekim:** Muayene etmeden kırığın derinliğini bilemeyiz.

Korunması gereken bilgi: Diş ağızda, yalnız parça kopmuş; İlk hastadaki iki saat/süt bilgisini taşıma.

Çıkarılmaması gereken sonuç: Tam diş avülsiyonu; Kök kırığı kesinliği.

Hekim incelemesi: Kırık parçasını tüm diş gibi değerlendirme.

Beklenen konu grupları (taslak): dental trauma management / pediatric.trauma.

### implant-bleeding-index — Vidayla yapılan dişin çevresi — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: peri-implant. Karşılaştırma: `implant-bleeding-contrast`.

**Hasta:** Vidayla yapılan dişin dibinden kan ve bazen kötü tat geliyor.

**Hekim:** Oynama var mı, ne zamandır oluyor?

**Hasta:** Kendisi oynamıyor ama eti şiş, bir süredir var.

**Asistan:** Hocam, dişin yanındaki et de dokununca kanıyor.

**Hekim:** Çevresini ölçüp filmiyle birlikte değerlendirelim.

**Hasta:** Yani vida kesin kaybedildi mi?

**Asistan:** Film henüz çekilmedi hocam.

**Hekim:** Öyle bir sonucu şu an söyleyemeyiz.

Korunması gereken bilgi: İmplant çevresinde kanama/şişlik; Film olmadığı.

Çıkarılmaması gereken sonuç: Kesin kemik kaybı miktarı; İmplant kaybedildi.

Hekim incelemesi: Biyolojik komplikasyon kaynağı; muayene gerekliliği.

Beklenen konu grupları (taslak): perio.peri_implant.

### implant-bleeding-contrast — Vidayla yapılan dişin çevresi — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: peri-implant. Karşılaştırma: `implant-bleeding-index`.

**Hasta:** Vidayla yapılan dişin üst tarafı tık tık oynuyor.

**Hekim:** Etrafında kanama veya şişlik var mı?

**Hasta:** Yok, sadece üstteki diş sallanıyor gibi.

**Asistan:** Hocam, hareket eden üst parça mı, kontrol edelim mi?

**Hekim:** Evet, bağlantıyı ve çevre dokuyu birlikte kontrol edeceğim.

**Hasta:** Altındaki vida sağlam mıdır bilmiyorum.

**Asistan:** Sadece hastanın üst parçayla ilgili söylediğini yazdım.

**Hekim:** Film ve muayene olmadan kemik kaybı diyemeyiz.

Korunması gereken bilgi: Üst parçanın oynama şikâyeti; Kanama/şişlik reddi.

Çıkarılmaması gereken sonuç: Vida gevşemesi kesin tanısı; Otomatik implant kaybı.

Hekim incelemesi: Mekanik sorun olasılığını araştır, muayenesiz tanı koyma.

Beklenen konu grupları (taslak): implant.prosthesis.

### gum-or-root-index — Diş eti mi dişin içi mi — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: periodontal-abscess, sdcep-red-flags. Karşılaştırma: `gum-or-root-contrast`.

**Hasta:** Alt ön dişimin arkasındaki et şişti, dokununca çok acıyor.

**Hekim:** Ne zamandır var, yiyip içebiliyor musunuz?

**Hasta:** İki gündür var, fırçalarken de kanıyor. Yutabiliyorum.

**Asistan:** Hocam, etin üzerinde şişlik ve birikmiş taş görülüyor.

**Hekim:** Dişin içini de kontrol edelim, yalnız görüntüye bakıp kanal kararı vermeyelim.

**Hasta:** Yani hemen diş çekilmeyecek mi?

**Asistan:** Bugün çekim yapılmış gibi kayıt açmıyorum.

**Hekim:** Önce muayene, gerekli testler ve film.

Korunması gereken bilgi: Diş eti şişliği ve kanama; Test/film henüz yapılmadığı.

Çıkarılmaması gereken sonuç: Kesin ölü diş; Çekim ya da kanal yapılmış.

Hekim incelemesi: Kök ve diş eti kaynağını ayırmak için eksik bilgiyi belirt.

Beklenen konu grupları (taslak): periodontitis diagnosis treatment / perio.general; odontogenic infection management.

### gum-or-root-contrast — Diş eti mi dişin içi mi — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: periodontal-abscess, sdcep-red-flags. Karşılaştırma: `gum-or-root-index`.

**Hasta:** Alt dişim ağrıyordu, şimdi çenemin altı hızla şişti.

**Hekim:** Yutmanız ve nefesiniz nasıl?

**Hasta:** Tükürüğümü bile zor yutuyorum, nefes de zor geliyor.

**Asistan:** Hocam ağzını açması da çok kısıtlı.

**Hekim:** Bu durum acil değerlendirme gerektiriyor, beklemeyelim.

**Hasta:** Diş ağrısı geçer diye evde beklemiştim.

**Asistan:** Acil yardım için hazırlığı başlatıyorum.

**Hekim:** Diş kaynaklı olabilir ama kesin tanı için bekleyerek zaman kaybetmeyelim.

Korunması gereken bilgi: Hızla artan şişlik; Yutma ve nefes güçlüğü.

Çıkarılmaması gereken sonuç: Basit lokal apse diye beklet; Vakadaki ilaç reçetesini kopyala.

Hekim incelemesi: Acil yönlendirme gecikmemeli; bitişte çalışan sistemin sınırını belirt.

Beklenen konu grupları (taslak): odontogenic infection management; emergencies.general.

### jaw-and-headache-index — Baş ağrısı ve çene hareketi — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: jaw-pain. Karşılaştırma: `jaw-and-headache-contrast`.

**Hasta:** Yıllardır başım ağrıyor, son zamanlarda kulağımın önü de acıyor.

**Hekim:** Ağzınızı açarken veya çiğnerken artıyor mu?

**Hasta:** Evet, çiğnerken artıyor, bazen ağzımı tam açamıyorum.

**Asistan:** Hocam, baş ağrısı için başka doktora da gitmiş.

**Hekim:** Bütün baş ağrınız kesin diş sıkmaktan, başka neden aramayalım.

**Hasta:** Ama bunun hepsi aynı şey mi, emin olamadım.

**Asistan:** Eski baş ağrısı değerlendirmesini de isteyelim mi?

**Hekim:** Evet, çene muayenesiyle birlikte diğer değerlendirmeyi de görelim.

Korunması gereken bilgi: Çene hareketiyle artan ağrı; Baş ağrısının önceki değerlendirmesi.

Çıkarılmaması gereken sonuç: Tüm baş ağrılarının kesin diş kaynaklı olduğu.

Hekim incelemesi: Hekimin kesinlik iddiasını ayrı kaynak kontrolüne taşı.

Beklenen konu grupları (taslak): orofacial_pain.general / temporomandibular disorders diagnosis.

### jaw-and-headache-contrast — Baş ağrısı ve çene hareketi — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: jaw-pain. Karşılaştırma: `jaw-and-headache-index`.

**Hasta:** Benim çenem değil, eşimin çenesi ses yapıyor.

**Hekim:** Siz hangi şikâyetle geldiniz?

**Hasta:** Dün düşen dolgum için geldim, çenemde ağrı ya da açılma sorunu yok.

**Asistan:** Ben de geceleri diş sıkıyorum ama bu benim kendi derdim hocam.

**Hekim:** Sizin düşen dolgunuzu inceleyelim.

**Hasta:** Evet, baş ağrım da yok.

**Asistan:** Eşinin ve benim anlattığımı hasta şikâyetine eklemiyorum.

**Hekim:** Hastanın kendi şikâyetinden ilerleyelim.

Korunması gereken bilgi: Hasta çene şikâyetini reddediyor; Eşin ve asistanın ayrı kişisel öyküleri.

Çıkarılmaması gereken sonuç: Hastada bruksizm veya çene ağrısı.

Hekim incelemesi: Üç konuşmacıda hasta-dışı öyküyü ayır.

Beklenen konu grupları (taslak): restorative.general.

Çıkmaması beklenen konular (taslak): temporomandibular disorders diagnosis, orofacial_pain.general.

### ortho-root-change-index — Tel tedavisinde kök değişikliği — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: ortho-root. Karşılaştırma: `ortho-root-change-contrast`.

**Hasta:** Tel tedavimde son filmde ön dişimin kökü kısalmış olabilir dediler.

**Hekim:** Önceki filminiz yanınızda mı?

**Hasta:** Telefonda var, ama yeni filmle aynı mı bilmiyorum.

**Asistan:** Hocam, karşılaştırmak için eski filmi de açayım.

**Hekim:** Filmleri inceleyip tedavi planını buna göre değerlendirelim.

**Hasta:** Dişim kesin düşecek mi?

**Asistan:** Söylenenin bir olasılık olduğunu not ettim.

**Hekim:** Kesin sonuç veya neden söylemeden değerlendirmeyi tamamlayalım.

Korunması gereken bilgi: Film hakkında aktarılan ihtimal; Karşılaştırmanın henüz yapılmadığı.

Çıkarılmaması gereken sonuç: Kesin kök kaybı miktarı; Tel tedavisi kesin hatalı.

Hekim incelemesi: Kök değişikliği araştır, nedensellik ve prognozu uydurma.

Beklenen konu grupları (taslak): ortho.resorption.

### ortho-root-change-contrast — Tel tedavisinde kök değişikliği — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: ortho-root. Karşılaştırma: `ortho-root-change-index`.

**Hasta:** Telleri dün sıktılar, ön dişlerime basınca sızlıyor.

**Hekim:** Filmde kökle ilgili bir şey söylendi mi?

**Hasta:** Hayır, yeni film çekilmedi, öyle bir şey de söylenmedi.

**Asistan:** Hocam, dün rutin tel kontrolü yapılmış.

**Hekim:** Ağrının yerini ve kapanışı kontrol edelim.

**Hasta:** Sızlama dün başladı, öncesinde yoktu.

**Asistan:** Süreyi bir gün olarak kaydettim.

**Hekim:** Tek başına sızlamadan kökün kısaldığı sonucunu çıkaramayız.

Korunması gereken bilgi: Tel ayarından sonra başlayan sızı; Kök değişikliği bilgisi olmadığı.

Çıkarılmaması gereken sonuç: Ağrıdan tek başına kök rezorpsiyonu.

Hekim incelemesi: Ayarlama sonrası şikâyeti kök hasarı diye etiketleme.

Beklenen konu grupları (taslak): ortho.appliances / ortho.general.

Çıkmaması beklenen konular (taslak): ortho.resorption.

### bite-pain-index — Isırınca sızlayan diş — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: cracked-tooth. Karşılaştırma: `bite-pain-contrast`.

**Hasta:** Sert bir şeyi ısırınca bir dişim fena sızlıyor, soğukta da oluyor.

**Hekim:** Ağrının yeri hep aynı mı?

**Hasta:** Bazen gösteremiyorum, üst tarafta. Daha önce filmde bir şey çıkmadı.

**Asistan:** Hocam, eski film var ama bugünkü muayene henüz yapılmadı.

**Hekim:** Dişi ve ısırmayı ayrı ayrı kontrol edelim.

**Hasta:** Film temizse dişte hiçbir sorun yok mudur?

**Asistan:** Hastanın hangi diş olduğunu tam seçemediğini yazıyorum.

**Hekim:** Film tek başına bütün olasılıkları dışlamaz.

Korunması gereken bilgi: Isırma ve soğukla ağrı; Diş lokalizasyonunun belirsizliği.

Çıkarılmaması gereken sonuç: Kesin çatlak veya diş numarası; Önceki filmin normal oluşundan sağlıklı tanısı.

Hekim incelemesi: Çatlak konusu araştırılmalı; tanı hekimde kalmalı.

Beklenen konu grupları (taslak): endo.cracked_tooth.

### bite-pain-contrast — Isırınca sızlayan diş — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: cracked-tooth. Karşılaştırma: `bite-pain-index`.

**Hasta:** Geçen hafta yapılan dolgu ağzımı kapatınca ilk o değiyor.

**Hekim:** Sert bir şeyi ısırmasanız da o yüksekliği hissediyor musunuz?

**Hasta:** Evet, boş kapatırken bile o diş önce buluşuyor.

**Asistan:** Hocam, şikâyet dolgu yapıldıktan sonra başlamış.

**Hekim:** Kapanışı ve dolguyu kontrol edelim.

**Hasta:** Daha önce o dişimde bu his yoktu.

**Asistan:** Hangi dolgudan bahsettiğini işaretleyelim mi?

**Hekim:** Evet, muayenede doğrulayalım.

Korunması gereken bilgi: Dolgu sonrası erken temas.

Çıkarılmaması gereken sonuç: Kesin çatlak tanısı; Dolgu ayarı yapılmış.

Hekim incelemesi: Kapanış şikâyetini alternatifleri kapatmadan değerlendir.

Beklenen konu grupları (taslak): prosth.occlusion / restorative.general.

### pregnancy-gum-mass-index — Hamilelikte büyüyen diş eti — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: pregnancy-mass. Karşılaştırma: `pregnancy-gum-mass-contrast`.

**Hasta:** Hamileyim, diş etimde bir et parçası büyüdü, yemek yerken kanıyor.

**Hekim:** Ne zamandır büyüyor, kaç haftalık hamilesiniz?

**Hasta:** Birkaç haftadır büyüyor, üç ayı geçtim ama haftayı tam hatırlamıyorum.

**Asistan:** Hocam, takip kartından haftayı teyit edebiliriz.

**Hekim:** O bölgeyi inceleyip kanamayı ve büyümeyi değerlendirelim.

**Hasta:** Hamileyim diye doğuma kadar hiç bakılmaz mı?

**Asistan:** Bugün herhangi bir şey kesilmiş gibi kayıt tutmuyorum.

**Hekim:** Değerlendirmeyi ertelemeyelim, yapılacak işi muayeneye göre konuşalım.

Korunması gereken bilgi: Hastanın gebeliği ve hafta belirsizliği; Büyüme ve tekrarlayan kanama.

Çıkarılmaması gereken sonuç: Kesin piyojenik granülom tanısı; Her girişim mutlaka ertelenmeli ya da yapılmalı.

Hekim incelemesi: Gebelik bağlamı ve lezyon incelemesi; Vaka tedavisini genel reçete sayma.

Beklenen konu grupları (taslak): pregnancy dental care; oral mucosal lesion diagnosis / oral_medicine.general / perio.general.

### pregnancy-gum-mass-contrast — Hamilelikte büyüyen diş eti — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: pregnancy-mass. Karşılaştırma: `pregnancy-gum-mass-index`.

**Hasta:** Diş etim fırçalarken kanıyor.

**Hekim:** Hamilelik veya düzenli ilaç var mı?

**Hasta:** Ben hamile değilim. Ablam hamile, telefonda ondan söz etmiştim.

**Asistan:** Hocam, gebelik kartı hastanın ablasına aitmiş.

**Hekim:** Sizin diş etlerinizi kontrol edelim.

**Hasta:** Büyüyen et parçası da yok, sadece fırçalayınca kanıyor.

**Asistan:** Ablasının bilgisini hastaya yazmıyorum.

**Hekim:** Muayene bulgularını ayrı kaydedelim.

Korunması gereken bilgi: Gebelik hastaya değil ablasına ait.

Çıkarılmaması gereken sonuç: Hasta hamile; Hastada büyüyen kitle.

Hekim incelemesi: Yakın öyküsünü hasta öyküsüne taşıma.

Beklenen konu grupları (taslak): periodontitis diagnosis treatment / perio.general.

Çıkmaması beklenen konular (taslak): pregnancy dental care.

### wire-and-gums-index — Aynı yerde tekrar eden diş eti şişliği — vaka esinli

Yayın yalnızca klinik başlangıç fikridir. Türkçe replikler, konuşmacılar, işlem planı ve ek ayrıntılar özgün kurgudur; gerçek hastanın sözü değildir.

Kaynak kimlikleri: foreign-body-gum. Karşılaştırma: `wire-and-gums-contrast`.

**Hasta:** Aynı dişimin eti yine şişti, daha önce de olmuştu.

**Hekim:** O bölgeyi zorlayan bir alışkanlığınız var mı?

**Hasta:** İşte kablonun ucunu bazen dişimle soyuyorum, tam oraya geliyor.

**Asistan:** Hocam, hasta aynı noktayı gösteriyor.

**Hekim:** Araya bir şey kaçmış mı ve diş eti nasıl, inceleyelim.

**Hasta:** Demek bütün sorun kesin kablodan mı?

**Asistan:** Alışkanlığı söylediği gibi kaydettim, neden diye kesinleştirmedim.

**Hekim:** Muayene etmeden tek neden diyemeyiz.

Korunması gereken bilgi: Tekrarlayan aynı bölge şişliği; Hastanın kablo soyma alışkanlığı.

Çıkarılmaması gereken sonuç: Kesin yabancı cisim var; Tek sebep kesin alışkanlık.

Hekim incelemesi: Lokal etkeni araştır, neden-sonuç kesinliği kurma.

Beklenen konu grupları (taslak): perio.general / periodontitis diagnosis treatment.

### wire-and-gums-contrast — Aynı yerde tekrar eden diş eti şişliği — karşılaştırma

Araştırmacı tarafından uydurulmuş karşılaştırma; kaynakta bildirilmiş ikinci vaka değildir. Değişen bilgiye göre yorumun değişmesi sınanır.

Kaynak kimlikleri: foreign-body-gum. Karşılaştırma: `wire-and-gums-index`.

**Hasta:** Diş etim kanıyor, kontrol ettirmek istedim.

**Hekim:** Dişinizle tel ya da kablo tutuyor musunuz?

**Hasta:** Ben yapmıyorum, öyle bir işim de yok.

**Asistan:** Kabloyu dişimle ben açıyorum hocam, hasta değil. Ben elektrik işi de yapıyorum.

**Hekim:** Hastanın şikâyetini ayrı değerlendirelim.

**Hasta:** Bende sadece fırçalarken kanama var.

**Asistan:** Kendi anlattığımı hasta dosyasına geçirmiyorum.

**Hekim:** Diş eti muayenesinden sonra konuşalım.

Korunması gereken bilgi: Kablo alışkanlığı asistana ait; Hasta alışkanlığı reddediyor.

Çıkarılmaması gereken sonuç: Hasta dişleriyle kablo soyuyor; Asistan hastanın diş hekimi gibi klinik iddia sahibi.

Hekim incelemesi: Asistan kişisel öyküsünü hastaya/hekime atfetme.

Beklenen konu grupları (taslak): perio.general / periodontitis diagnosis treatment.

## Kaynaklar ve erişim sınırları

PMC/PubMed bir dizin/depo erişimidir; vaka yayıncıları farklıdır. Vaka raporu tek başına tedavi kılavuzu veya nedensellik kanıtı değildir. Tam metin CAPTCHA ile açılamadıysa yalnız tarama aracının getirdiği indekslenmiş vaka/özet bölümü kullanıldı; tüm makale okunmuş gibi işaretlenmedi. Yayın tarihi doğrulaması kaynak bazında sınırlıdır; erişim tarihi bütün kaynaklar için 31 Ekim 2026.

- **denture-ulcer** — [Oral squamous cell carcinoma misdiagnosed as a denture-related traumatic ulcer: A clinical report](https://pubmed.ncbi.nlm.nih.gov/26581660/). Kapsam: Özet: protez sonrası başlayan ve protez çıkarılınca da geçmeyen yaranın tanısında gecikme. Erişim: Abstract reviewed; dialogue and contrast invented.
- **irrigant-accident** — [Bone necrosis as a complication of sodium hypochlorite extrusion. A case report](https://pmc.ncbi.nlm.nih.gov/articles/PMC9617265/). Kapsam: Kanal yıkaması sırasında yanma; sonrasında doku hasarı. Vaka bir tedavi kılavuzu değildir. Erişim: Indexed case text reviewed; direct full-text open hit CAPTCHA.
- **antiresorptive** — [Multidisciplinary approach for medication-related osteonecrosis of the jaws: a case report and literature review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061783/). Kapsam: Kanser için kemik ilacı kullanımı ve çekim sonrası uzun süren açık kemik. Erişim: Indexed case text reviewed; direct full-text open hit CAPTCHA.
- **crown-aspiration** — [Crowning achievement: a case of dental aspiration](https://pmc.ncbi.nlm.nih.gov/articles/PMC4661492/). Kapsam: İşlem sırasında kaplamanın solunum yoluna kaçtığı bildirilmiş vaka. Erişim: Indexed case text reviewed; direct full-text open hit CAPTCHA.
- **avulsed-tooth** — [Replantation of an Avulsed Tooth: A Case Report](https://pmc.ncbi.nlm.nih.gov/articles/PMC10276759/). Kapsam: Düşmeyle yerinden çıkan kalıcı ön diş; süt içinde taşınma ve geçen sürenin kaydı. Erişim: Indexed case text reviewed; direct full-text open hit CAPTCHA.
- **peri-implant** — [The challenge of periimplantitis management: a case report](https://pubmed.ncbi.nlm.nih.gov/36571747/). Kapsam: İmplant çevresinin klinik ve radyografik değerlendirilmesi; tek protokolün üstünlüğü çıkarılamaz. Erişim: PubMed abstract reviewed.
- **periodontal-abscess** — [Management of Acute Periodontal Abscess Mimicking Acute Apical Abscess in the Anterior Lingual Region: A Case Report](https://pmc.ncbi.nlm.nih.gov/articles/PMC6822886/). Kapsam: Diş eti kaynaklı apsenin kök kaynaklı sorunla karışabilmesi; muayene ve testlerle ayrım. Erişim: Full case text reviewed.
- **jaw-pain** — [An Unusual Case of Temporomandibular Joint Disorder Resembling Migraine](https://pmc.ncbi.nlm.nih.gov/articles/PMC9923078/). Kapsam: Uzun süren baş ağrısına çene hareketiyle artan ağrının eşlik etmesi. Erişim: Indexed case text reviewed; direct full-text open hit CAPTCHA.
- **ortho-root** — [Effective endodontically treated incisors with external root resorption during orthodontic movement: A case report](https://pmc.ncbi.nlm.nih.gov/articles/PMC10041545/). Kapsam: Ortodontik tedavi sırasında kök değişikliği ve endodonti-ortodonti değerlendirmesi. Erişim: Indexed abstract reviewed; no images reused.
- **cracked-tooth** — [Cracked Tooth: A Report of Two Cases and Role of Cone Beam Computed Tomography in Diagnosis](https://pmc.ncbi.nlm.nih.gov/articles/PMC3502789/). Kapsam: Isırma ve ısıyla ağrı; ilk filmde belirgin bulgu olmaması çatlağı tek başına dışlamaz. Erişim: Indexed case text reviewed.
- **pregnancy-mass** — [Clinical management and surgical intervention for oral pyogenic granuloma during pregnancy: a case report](https://pmc.ncbi.nlm.nih.gov/articles/PMC13336780/). Kapsam: Gebelikte büyüyen ve kanayabilen diş eti oluşumu; konuşmayla patolojik tanı konmaz. Erişim: Indexed case text reviewed; treatment not adopted as a recommendation.
- **foreign-body-gum** — [Recurrent periodontal abscess associated with “teeth as a tool”](https://pmc.ncbi.nlm.nih.gov/articles/PMC3357018/). Kapsam: Dişi kablo soymak için kullanma alışkanlığıyla ilişkili tekrarlayan diş eti apsesi. Erişim: Indexed abstract reviewed; causal certainty not generalized.
- **sdcep-red-flags** — [Dental abscess — Drug Prescribing for Dentistry (SDCEP)](https://sdcepdentalprescribing.nhs.scot/guidance/bacterial-infections/dental-abscess/). Kapsam: Yutma/solunum güçlüğü ve ciddi şişlik gibi bulgularda acil değerlendirme; vaka sonrası bekleme testi değildir. Erişim: Official guidance reviewed.
- **ada-lesions** — [Oral Cancer Guideline (2026 Update) — ADA](https://www.ada.org/resources/research/science/evidence-based-dental-research/oral-cancer-guideline). Kapsam: Şüpheli ağız lezyonunun değerlendirilmesi; histopatolojik tanı konuşmadan çıkarılamaz. Erişim: Official guideline overview reviewed; not a clinical adjudication.
