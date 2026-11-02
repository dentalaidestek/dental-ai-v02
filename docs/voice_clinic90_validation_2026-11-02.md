# 90 saniyelik farklı klinik vaka ses testleri — 2 Kasım 2026

Amaç: hekim görüşme sırasında ekrana bakmadan konuşabilsin; hasta/asistan/hekim doğal günlük ifadeleri farklı diş hekimliği dallarında test edilsin. Bu paket hekim onaylı klinik altın standart değildir.

## Materyal

Sekiz özgün sentetik diyalog: periodontal kanama, varfarinli cerrahi değerlendirme, implant oynama/kanama, yeni kron yüksek kapanış, uzayan soğuk ağrısı, çocuk ön diş travması, ortodontik tel batması, protez çıkarılsa da geçmeyen yara. Her biri12tur,185–206kelime. Kaynak bağlantıları konuyu temellendirir; diyaloglar yayınlanmış hastaların kayıtları değildir. İlaç dozu/tedavi kararı türetilmez.

Her vaka için temiz ve uğultulu birer WAV üretildi: toplam16dosya, her biri tam90.000saniye,22050Hz mono16bit,8MBaltında. İlk/son sözler kesilmedi; zaman uyarlaması1.05–1.15 aralığında, konuşmadan sonra dolgu sessizliği var. Konuşmacı rol adları seslendirilmedi. Düşük frekanslı oda/havalandırma uğultusu, uzaktaki alet ve tepsi sesi sentetik olarak üretildi; gerçek klinik ortam kaydı değildir. İki gürültü seviyesi: aktif konuşma RMS'sine göre18/14dB. Hashler ve tohumlar voice_clinic90_audio_manifest.json içinde; üretici scripts/build_voice_clinic_audio.py, isteğe bağlı espeakng-loader==0.2.4 veffmpeg gerektirir.

Önemli sınır: eSpeak sesleri robotiktir; diyalog metni gündelik olsa da gerçek insan sesi doğallığı sağlanmış değildir. Daha doğal sentez için HeyGen bulundu ve önerildi; henüz bağlı olduğu doğrulanmadı. Hiçbir mevcut sağlayıcı bağlantısı değiştirilmedi.

## İlk canlı ölçümler

Render uygulama2abdbb4e; QA11geçici sayfaları; hiçbir kayıt onaylanmadı. Perio ve cerrahi uğultulu90s kayıtlar gerçek Gemini çağrısıyla yazıya çevrildi. Belirgin kelime/olumsuzluk kayıpları var. Cerrahide özgün “varfarin” yerine “Morfin” yazıldı. Aynı cerrahi sesinin temiz karşılaştırmasında “Warfarin” çıktı fakat metin çok kısaldı ve önemli konuşmalar atlandı. Dolayısıyla hata yalnız uğultuya bağlanamaz; sentetik ses niteliği ve çözümleme davranışı ayrıştırılmadan gerçek klinik doğruluk oranı verilmez. Kelimeyi sunucuda varfarin diye zorla değiştirmek uygulanmadı.

Perio ASR metni klinik çıkarıma gönderildiğinde PATIENT/OTHER örtüşmesi bütün değerlendirmeyi durdurdu; bu önceki implant vakasıyla aynı üretim hatasıdır. Üç regresyon önce bu global hatayla başarısız oldu. Yeni davranış: yalnız çakışan bilgi hasta alanlarına alınmaz, bağımsız dayanaklı bilgiler işlenir; kaynak/diş/düzeltme/randevu dışlama kapıları korunur. Sabit eksik kapsam uyarısı muayene sonunda görünür; otomatik yeni ücretli çağrı veya canlı hekime doğrulama adımı eklenmedi. Tüm bilgiler ayırt edilemezse mevcut boş-muayene koruması son modeli engeller.

Yerel494Python geçti (iki mevcut bağımlılık uyarısı); Node sonucu ve yayın sonrası vakalar aşağıda tamamlanacak. Bağımsız inceleme127odaklı test geçti, kod engeli bulunmadı. Genel site CI'nın önceki akademik hataları giderildi sayılmaz.
