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
