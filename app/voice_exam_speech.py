"""Interpretation guidance for the existing model; never a phrase-matching router.

Illustrations are not exhaustive or diagnostic labels. Evaluation dialogues live
separately and are never injected as expected answers into production prompts.
"""
_RULES = (
 'Günlük anlatımı, konuşmanın bütünü ve hekimin sorusu/yanıtı içinde anlamlandır; hastadan tıbbi terim bekleme.',
 'Önce kimin hakkında konuşulduğunu, belirtilen bölgeyi, önceki işlemi, başlangıç/süreyi, tetikleyiciyi ve halen mi geçmişte mi olduğunu ayır. Eksik ayrıntıyı doldurma.',
 'Tek kelimeyi tanıya çevirme: sallanma doğal diş, protez veya implant üstü parçaya ait olabilir; önce referansı çöz. Kesinleşmiyorsa genel dal konusu ve kısa netleştirme sorusu kullan.',
 'Hekimin olası açıklaması, örnek hastası, tedavi önerisi ve tamamlanmış işlem farklıdır. Öneriyi yapılmış komplikasyon veya hastada kesin tanı gibi kaydetme.',
 'Yok, olmadı, eskiden, annemde, belki ve henüz başlamadık gibi anlamları; hangi soruya verildiğiyle birlikte koru. Geçmiş veya başkasına ait bulguyu güncel hasta bulgusu yapma.',
 'Şuradaki, o, yine, takılan şey gibi göndermeleri yalnız açık konuşma bağlamıyla çöz; bağlam yoksa diş numarası, materyal, işlem veya ilaç adı uydurma.',
 'Konuşma dökümü bozuk/eksik olabilir. Belirsiz sözü sessizce tıbbi terime düzeltip kesinleştirme; duyulan kısa alıntıyı ve doğrulama ihtiyacını koru.',
 'Birden fazla gerçek sorun varsa ilişkili dalları birlikte seç. Yakınmayı ağrı, ilaç veya en son söylenen konuya indirgeme; zaten cevaplanmış soruyu yeniden sorma.',
 'Duygusal veya maddi engeli fiziksel hastalık diye sınıflandırma; geçici iletişim önerisinde değerlendir. Kayıt ve klinik bulgu ile ayrı tut.',
 'Kaynak konusu seçmek tanı koymak değildir. Bir belirti birden fazla nedenle açıklanabiliyorsa kesin hastalık yerine değerlendirme kapsamını seç, eksik bilgiyi belirt.',
 'Aşağıdaki örnekler açıklama içindir, gerçek hastanın sözleri değildir. clinical_text veya önceki doğrulanmış bağlamda bulunmayan bir örneği alıntı/klinik bilgi olarak kullanma.',
)
_AMBIGUOUS = (
 {'mention':'vida / takılan diş / parça oynuyor', 'clarify':'İmplant gövdesi, doğal diş, protez veya üst bağlantı mı; hangi işlemden sonra?'},
 {'mention':'sinir alındı / içi temizlendi', 'clarify':'Hangi dişe hangi işlem yapılmış, bitti mi; güncel yakınma ne?'},
 {'mention':'damak / üstteki / lastik / tel', 'clarify':'Doğal doku, hareketli protez veya ortodontik aparey mi; konuşma bağlamından anlaşılmıyorsa sor.'},
 {'mention':'iğne dokundu / alerji yaptı', 'clarify':'Gerçek belirtiler, zamanlama, kullanılan ürün ve hekimin değerlendirmesi; sırf çarpıntıyı kesin alerji sayma.'},
)
_EXAMPLES = (
 ('prosth', 'prosth.occlusion', 'Yenisi takıldığından beri dişlerimi birleştirince ilk o yakalıyor.', 'Yeni restorasyon ve kapanış ilişkisini değerlendir; muayene olmadan yüksek restorasyon tanısı koyma.'),
 ('prosth', 'prosth.removable', 'Konuşurken üstteki takma damağım aşağıya geliyor, kenarı da vuruyor.', 'Tutuculuk/uyum ve yumuşak doku etkisi; sadece genel diş ağrısı değildir.'),
 ('ortho', 'ortho.retention', 'Telleri çıkarttık, geceleri taktığımı bıraktım; önler yine birbirine bindi.', 'Tedavi sonrası seyir ve pekiştirme bağlamını birlikte anla.'),
 ('pediatric', 'pediatric.occlusion', 'Ufaklığın süt azısı gidince arkadaki o boşluğa yürümüş.', 'Yaş, erken diş kaybı ve boşluk ilişkisi; kesin kayma ölçümü uydurma.'),
 ('perio', 'perio.general', 'Fırçaladığımda köpük pembe oluyor, ön dişlerin arası açıldı gibi.', 'Kanama/periodontal değerlendirme; ölçüm olmadan kemik kaybı tanısı koyma.'),
 ('surgery', 'surgery.nerve', 'Arkada gömülü olanı aldırdım; dudağımın yarısı hâlâ bana ait değil gibi.', 'İşlem zamanı ve duyu değişikliği değerlendirmesi; kalıcı hasar sonucu çıkarma.'),
 ('oral_medicine', 'oral_medicine.saliva', 'Dilimin yapıştığını hissediyorum, su içmeden kuru şeyleri yiyemiyorum.', 'Kuruluk ve tükürük değerlendirmesi; tek hastalık adına zorlamadan bağlamı koru.'),
 ('restorative', 'restorative.adhesion', 'İki dişimin arasına her yemekte bir şey doluyor; beyaz dolgu yapılınca başladı.', 'Restorasyon, kontakt ve temizlenebilirlik; çürük/işlem hatası kesin değildir.'),
 ('implant', 'implant.prosthesis', 'Çeneye vidalı olanın üstündeki kapak tık tık oynuyor, dipteki sabit gibi.', 'Gövde ve üst yapı ayrımını netleştir; tüm implantın hareket ettiğini varsayma.'),
 ('endo', 'endo.cracked_tooth', 'Sıkarken bazen yok, lokmayı bırakırken içime bir elektrik vuruyor.', 'Çatlak/pulpa/restorasyon ayırıcı değerlendirmesi; belirtiyi çatlak tanısına çevirme.'),
 ('imaging', 'imaging.general', 'Geçen hafta büyük filmi çektirdim; şimdi üç boyutlusu niye isteniyor?', 'Önceki görüntü, planlanan işlem ve görüntüleme gerekçesi birlikte değerlendirilir.'),
 ('anesthesia', 'anesthesia.general', 'Uyuşturan iğneden sonra kalbim hızlı attı, ama dökülmedim ve nefesim daralmadı.', 'Çarpıntı ve açık olumsuz belirtileri koru; doğrulanmış alerji yazma.'),
 ('emergencies', 'emergencies.general', 'Ağzımdaki küçük parçayı bulamadık; o anda öksürük tuttu.', 'Yabancı cisim/solunum değerlendirmesi; kesin aspirasyon tanısı koyma veya yardımı kaynak aramasına bağlama.'),
 ('special_care', 'special_care.general', 'Babam başıyla boynuna ışın aldı, şimdi kalan dişlerini aldıracak.', 'Konuşulan kişinin kimliği, radyoterapi ve planlanan işlemi ayır; konuşan hekimin hastası olduğu net değilse sor.'),
 ('prevention', 'prevention.diet', 'Bütün gün çayı şekerli yudumluyorum, akşam yıkayınca geçmez mi?', 'Tüketim sıklığı, hijyen ve koruyucu bakım ilişkisi; davranıştan hastalık uydurma.'),
 ('orofacial_pain', 'orofacial_pain.sleep', 'Eşim gece sustuğumu sonra nefes nefese kaldığımı söylüyor, gündüz gözüm kapanıyor.', 'Uyku-solunum değerlendirmesi; eş gözlemini doğrulanmış uyku testi sayma.'),
)


def interpretation_guide():
    return {'rules': list(_RULES), 'ambiguous_mentions': [dict(item) for item in _AMBIGUOUS],
            'examples': [{'branch': branch, 'possible_topic': topic, 'patient_words': words,
                          'interpretation_limit': limit} for branch, topic, words, limit in _EXAMPLES]}
