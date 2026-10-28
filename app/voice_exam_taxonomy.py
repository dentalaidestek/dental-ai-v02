"""Server-owned dental scope IDs. Selection is semantic, never a diagnosis or search string.

General branch IDs route unfamiliar situations without inventing a new query. A
branch-level document does not establish evidence for a specific complication.
"""
MAX_TOPICS = 24
BRANCH_LABELS = {
    'prosth': 'Protetik diş tedavisi', 'ortho': 'Ortodonti', 'pediatric': 'Çocuk diş hekimliği',
    'perio': 'Periodontoloji', 'surgery': 'Ağız, diş ve çene cerrahisi',
    'oral_medicine': 'Ağız hastalıkları', 'restorative': 'Restoratif diş tedavisi',
    'implant': 'İmplantoloji', 'endo': 'Endodonti', 'imaging': 'Oral radyoloji',
    'anesthesia': 'Anestezi ve sedasyon', 'emergencies': 'Klinik aciller',
    'special_care': 'Sistemik hastalık ve özel bakım', 'prevention': 'Koruyucu diş hekimliği',
    'orofacial_pain': 'Orofasiyal ağrı ve çene eklemi',
}
# ID, label, semantic scope, fixed scientific query, legacy/local keyword hints.
_ROWS = (
 ('prosth.general', 'Protetik değerlendirme', 'Sabit/hareketli protez planı, işlem sırası, başarısızlık veya özel alt başlığı olmayan protetik sorun.', '(prosthodontic treatment OR dental prosthesis) AND (planning OR complications OR failure)', ('protez', 'takma diş', 'takma damak')),
 ('prosth.fixed', 'Kuron, köprü ve preparasyon', 'Kaplama/köprü endikasyonu, diş kesimi, marjinal uyum, geçici restorasyon, dayanak ve biyolojik komplikasyonlar.', '(dental crown OR fixed dental prosthesis) AND (preparation OR marginal fit OR complications)', ('kaplama', 'kuron', 'köprü', 'preparasyon')),
 ('prosth.removable', 'Hareketli protez', 'Tam/parsiyel protez tutuculuğu, stabilite, vuruk, kaide, kroşe, besleme ve yeniden yapım.', '(complete denture OR removable partial denture) AND (retention OR fit OR complications OR maintenance)', ('damağım', 'kroşe', 'protez vur')),
 ('prosth.occlusion', 'Protezde kapanış ve dikey boyut', 'Yeni restorasyona önce temas, yüksek kapanış, oklüzal uyumsuzluk, dikey boyut; ağrı tek başına endodontik tanı değildir.', '(dental prosthesis OR crown) AND (occlusion OR occlusal adjustment OR vertical dimension)', ('yüksek kapanış', 'oklüzyon', 'önce değiyor')),
 ('prosth.cementation', 'Simantasyon ve bağlantı', 'Siman seçimi/kalıntısı, adeziv bağlantı, desimantasyon ve izolasyonun protetik uygulaması.', '(dental crown OR prosthesis) AND (cementation OR luting OR debonding OR residual cement)', ('simantasyon', 'siman', 'desimante')),
 ('prosth.materials', 'Protez malzemesi ve kırık', 'Seramik/zirkonya/metal seçimi, veneer, chipping, protez kırığı, tamir ve materyal uyumu.', '(dental prosthesis OR crown) AND (ceramic OR zirconia OR material selection OR fracture)', ('zirkonya', 'seramik', 'chipping')),
 ('ortho.general', 'Ortodontik değerlendirme', 'Maloklüzyon, çapraşıklık, tedavi planı/zamanı ve özel alt başlığı olmayan ortodontik risk.', '(orthodontic treatment OR malocclusion) AND (assessment OR complications OR planning)', ('ortodont', 'çapraşık', 'teller')),
 ('ortho.appliances', 'Ortodontik apareyler', 'Sabit aparey, şeffaf plak, braket, biyomekanik ve hijyenle ilişkili sorunlar.', '(orthodontic appliance OR aligner OR bracket) AND (complications OR effectiveness OR adverse effects)', ('braket', 'şeffaf plak', 'aparey')),
 ('ortho.retention', 'Pekiştirme ve nüks', 'Tedavi sonrası yeniden çapraşma, retainer/pekiştirme ve takip.', '(orthodontic retention OR retainer OR relapse)', ('retainer', 'pekiştirme', 'yeniden çapraş')),
 ('ortho.resorption', 'Ortodontik kök riski', 'Kök rezorpsiyonu, gömülü/ektopik diş, komşu kök ve hareket sınırları.', '(orthodontic treatment OR impacted canine) AND (root resorption OR adverse effects)', ('kök rezorpsiyon', 'gömülü kanin', 'köpek dişim damakta')),
 ('pediatric.general', 'Çocukta dental değerlendirme', 'Yaşa/gelişime özgü süt/karma/genç daimi diş işlemi; süt dişi erişkin daimi diş gibi değerlendirilmez.', '(pediatric dentistry OR primary teeth) AND (treatment planning OR complications)', ('süt diş', 'çocuk', 'biberon')),
 ('pediatric.pulp', 'Çocukta pulpa tedavisi', 'Süt veya genç daimi dişte pulpotomi, pulpektomi, vital pulpa, açık apeks ve rejenerasyon.', '(primary teeth OR immature permanent teeth) AND (pulpotomy OR pulpectomy OR vital pulp therapy)', ('pulpotomi', 'pulpektomi', 'açık apeks')),
 ('pediatric.trauma', 'Çocukta dental travma', 'Süt/genç daimi diş travması; avülsiyon, lüksasyon ve diş gelişimine uygun değerlendirme.', '(primary teeth OR immature permanent teeth) AND (dental trauma OR avulsion OR luxation)', ('süt dişi travma', 'çocuk düştü')),
 ('pediatric.behavior', 'Çocukta davranış yönetimi', 'Çocukta kaygı, iş birliği, ebeveyn iletişimi, davranış yönlendirmesi; sedasyon ayrı değerlendirilir.', '(pediatric dentistry) AND (behavior guidance OR dental anxiety OR cooperation)', ('çocuk kork', 'kooperasyon')),
 ('pediatric.occlusion', 'Gelişen dentisyon ve yer tutma', 'Erken süt dişi kaybı, boşluk kapanması, yer tutucu, sürme, çapraz kapanış ve gelişen oklüzyon.', '(developing dentition OR primary teeth) AND (space maintainer OR premature loss OR eruption OR occlusion)', ('yer tutucu', 'süt azısı', 'erken süt dişi')),
 ('perio.general', 'Periodontal değerlendirme', 'Diş eti kanaması, cep, ataşman/kemik kaybı, mobilite ve periodontal tedavi/takip.', '(periodontal disease OR periodontitis) AND (diagnosis OR treatment OR maintenance)', ('diş eti kan', 'fırçalarken kan', 'periodontal')),
 ('perio.surgery', 'Periodontal cerrahi ve mukogingival sorun', 'Flep, rejenerasyon, greft, çekilme, kök yüzeyi ve cerrahi sonrası sorunlar.', '(periodontal surgery OR gingival recession OR mucogingival surgery) AND (complications OR treatment)', ('diş eti çekil', 'dişeti greft', 'flep')),
 ('perio.peri_implant', 'Peri-implant hastalık', 'İmplant çevresinde kanama/iltihap, mukozitis, periimplantitis ve kemik kaybı.', '(peri-implantitis OR peri-implant mucositis) AND (diagnosis OR treatment)', ('periimplant', 'implant çevresinde')),
 ('surgery.general', 'Cerrahi değerlendirme', 'Çekim ve çene cerrahisi planı, işlem riski, iyileşme ve alışılmadık cerrahi komplikasyon.', '(oral surgery OR tooth extraction) AND (complications OR risk assessment OR postoperative care)', ('cerrahi', 'diş çekim')),
 ('surgery.third_molar', 'Gömülü diş ve üçüncü molar', 'Yirmilik/gömülü diş endikasyonu, perikoronitis, komşuluk ve cerrahi planlama.', '(impacted third molar OR pericoronitis) AND (management OR complications OR indications)', ('yirmilik', 'gömülü diş', 'perikoron')),
 ('surgery.bleeding', 'Çekim sonrası kanama ve iyileşme', 'Kanama, alveolit, iyileşmeyen soket ve çekim sonrası bakım; ilaç öyküsü ayrıca değerlendirilir.', '(tooth extraction) AND (postoperative bleeding OR alveolar osteitis OR wound healing)', ('alveolit', 'soket', 'çekim sonrası kan')),
 ('surgery.nerve', 'Cerrahi sonrası duyu değişikliği', 'Dudak/dil uyuşukluğu, parestezi ve sinir yakınlığı; konuşma tek başına sinir hasarı tanısı koydurmaz.', '(oral surgery OR third molar surgery) AND (nerve injury OR paresthesia OR neurosensory)', ('parestezi', 'dudağımı hisset', 'dil uyuş')),
 ('surgery.sinus', 'Sinüs ilişkisi ve oroantral açıklık', 'Üst çene arka bölge işleminden sonra buruna sıvı geçmesi, sinüs yakınlığı ve açıklık şüphesi.', '(oroantral communication OR oroantral fistula OR odontogenic sinusitis) AND management', ('oroantral', 'burnuma su', 'sinüs')),
 ('oral_medicine.general', 'Ağız hastalıkları değerlendirmesi', 'Mukoza/dil/tükürük bezi bulgusu, alışılmadık oral belirti ve ayırıcı değerlendirme.', '(oral medicine OR oral mucosal disease) AND (diagnosis OR management)', ('mukoza', 'dilimde', 'ağız hastalık')),
 ('oral_medicine.cancer', 'Kalıcı veya şüpheli lezyon', 'İyileşmeyen sert/ülseratif/beyaz-kırmızı lezyon, biyopsi/sevk gereksinimi; şüphe kanser tanısı değildir.', '(oral potentially malignant disorder OR oral cancer) AND (early diagnosis OR biopsy OR referral)', ('geçmeyen yara', 'lökoplaki', 'biyopsi')),
 ('oral_medicine.saliva', 'Ağız kuruluğu ve tükürük', 'Kuruluk, tükürük bezi işlevi/taşı ve sistemik/ilaç bağlantıları; belirti hastalık kanıtı değildir.', '(xerostomia OR salivary gland disease) AND (diagnosis OR treatment)', ('ağız kurulu', 'kupkuru', 'tükürük')),
 ('oral_medicine.infection', 'Oral enfeksiyon ve mukozit', 'Kandidiyazis, viral/mukozal enfeksiyon, mukozit ve tekrarlayan oral ülserler.', '(oral candidiasis OR oral mucositis OR recurrent aphthous stomatitis) AND treatment', ('kandid', 'aft', 'mukozit')),
 ('restorative.general', 'Restoratif değerlendirme', 'Dolgu/restorasyon planı, izolasyon, kontakt/kenar ve tekrarlayan başarısızlık; özel kapsam yoksa dal düzeyinde değerlendir.', '(dental restoration OR operative dentistry) AND (failure OR complications OR technique)', ('restoratif', 'dolgu')),
 ('restorative.adhesion', 'Adeziv restorasyon ve kontakt', 'Bonding, polimerizasyon, izolasyon, sekonder çürük, kontakt ve marjinal uyum.', '(dental restoration) AND (adhesion OR polymerization OR isolation OR proximal contact OR marginal adaptation)', ('bonding', 'polimerizasyon', 'kontakt')),
 ('restorative.wear', 'Diş aşınması ve erozyon', 'Erozyon, atrizyon/abrazyon, aşınma nedenleri ve restoratif planlama.', '(tooth wear OR dental erosion OR tooth abrasion) AND (management OR restoration)', ('erozyon', 'diş aşın', 'atrizyon')),
 ('restorative.hypersensitivity', 'Hassasiyet ve restorasyon sonrası belirti', 'Dentin hassasiyeti ve dolgu sonrası belirti; çatlak/pulpa/oklüzyon ayrımı klinik muayene gerektirir.', '(dentin hypersensitivity OR postoperative sensitivity) AND dental restoration', ('hassasiyet', 'dolgu sonrası')),
 ('implant.general', 'İmplant değerlendirmesi', 'İmplant endikasyonu, konum, yükleme, biyolojik/mekanik başarısızlık ve risk.', '(dental implant) AND (planning OR complications OR failure OR loading)', ('implant', 'vidayla yapılan diş')),
 ('implant.prosthesis', 'İmplant üstü protez', 'Vida gevşemesi/kırığı, bağlantı, pasif uyum, siman ve implant üstü protez bakımı.', '(implant supported prosthesis) AND (screw loosening OR fracture OR misfit OR maintenance)', ('vida gevşe', 'implant üstü')),
 ('endo.cracked_tooth', 'Çatlak diş değerlendirmesi', 'Isırma/bırakma ile düzensiz sızı, çatlak şüphesi ve pulpa-restorasyon ayırımı; belirti tek başına çatlak tanısı değildir.', '(cracked tooth OR tooth crack) AND (diagnosis OR management OR biting pain)', ('çatlak diş', 'ısırmayı bırak')),
 ('restorative.esthetics', 'Renk ve estetik girişimler', 'Diş rengi, beyazlatma, estetik beklenti, restorasyonla renk farkı ve uygulama sonrası hassasiyet.', '(tooth whitening OR dental bleaching) AND (sensitivity OR efficacy OR restorations)', ('beyazlat', 'diş rengi')),
 ('orofacial_pain.sleep', 'Uyku ve solunumla ilişkili değerlendirme', 'Horlama, uykuda soluk durması/gündüz uykululuğu ve dental aparey/sevk bağlamı; gözlem kesin uyku apnesi tanısı değildir.', '(sleep apnea OR sleep disordered breathing) AND (oral appliance OR dental assessment)', ('horlama', 'uykuda nefes')),
 ('pediatric.development', 'Diş gelişimi ve sürme', 'Geciken/erken sürme, diş sayısı/şekli, mine gelişimi, ebeveyn gözlemi ve gelişimsel değerlendirme.', '(tooth eruption OR dental developmental defects) AND pediatric dentistry', ('diş çıkmıyor', 'sürme', 'mine gelişim')),
 ('prevention.diet', 'Beslenme ve alışkanlık riski', 'Şeker/asit tüketim sıklığı, biberon, atıştırma ve hijyenin çürük/aşınmayla ilişkisi; sadece alışkanlıktan hastalık sonucu çıkarma.', '(diet OR sugar OR acidic beverages) AND (dental caries OR tooth erosion) AND prevention', ('şekerli içecek', 'atıştır', 'beslenme')),
 ('endo.general', 'Endodontik işlem değerlendirmesi', 'Kanal tedavisi, irrigasyon, çalışma boyu, obturasyon, retreatment ve alışılmadık komplikasyon.', '(endodontic treatment OR root canal treatment) AND (complications OR failure OR procedural errors)', ('endodont', 'kanal tedavi')),
 ('imaging.general', 'Görüntüleme seçimi ve yorum sınırları', 'Radyografi/CBCT gerekliliği, gerekçelendirme, radyasyon ve görüntünün klinikle ilişkilendirilmesi.', '(dental radiography OR cone beam computed tomography) AND (justification OR selection criteria OR radiation protection)', ('üç boyutlu çekim', 'cbct', 'tomografi')),
 ('anesthesia.general', 'Lokal anestezi değerlendirmesi', 'Enjeksiyon, lokal anestezik/vasokonstriktör, yetersiz anestezi ve advers olay; alerji/anksiyete ayrımını varsayma.', '(dental local anesthesia) AND (adverse effects OR complications OR vasoconstrictor)', ('uyuşturucu iğne', 'lokal anestezi', 'anestezik')),
 ('anesthesia.sedation', 'Sedasyon ve genel anestezi', 'Hasta seçimi, sedasyon/anestezi düzeyi, izlem, risk ve derlenme.', '(dental sedation OR dental general anesthesia) AND (patient selection OR monitoring OR safety)', ('sedasyon', 'genel anestezi')),
 ('emergencies.general', 'Dental ortamda acil durum', 'Aspirasyon/yabancı cisim, solunum sorunu, senkop, alerjik reaksiyon ve diğer tıbbi aciller; acil yardım kaynak aramasına ertelenmez.', '(medical emergency dentistry OR foreign body aspiration dentistry) AND management', ('aspirasyon', 'senkop', 'nefes alam', 'metal parça kaybol')),
 ('special_care.general', 'Sistemik risk ve özel bakım', 'Kanser/radyoterapi, böbrek/karaciğer/kalp hastalığı, immünsüpresyon, engellilik ve özel bakımın dental işlemle ilişkisi.', '(dental management) AND (medically compromised OR special health care needs OR radiotherapy OR renal disease)', ('ışın tedavi', 'radyoterapi', 'özel bakım', 'böbrek')),
 ('special_care.hypertension', 'Hipertansiyonda dental işlem', 'Kan basıncı, vazokonstriktör ve dental işlem bağlamı; tek ölçümle tanı koyma.', '(hypertension OR high blood pressure) AND dental treatment', ('hipertansiyon', 'tansiyon')),
 ('special_care.cardiac', 'Kardiyak risk ve profilaksi', 'Kapak hastalığı/protez kapak, endokardit öyküsü ve profilaksi endikasyonu; protez sözcüğünü tek başına kalp kapağı sayma.', '(infective endocarditis OR prosthetic heart valve) AND dental antibiotic prophylaxis', ('protez kapak', 'endokardit', 'profilaksi')),
 ('special_care.drug_interactions', 'Dental reçete ve ilaç etkileşimi', 'Mevcut/plandaki ilaçlar, makrolid-statin dahil etkileşim bağlamı; ilaç adını hastalık tanısı sayma.', '(dental prescribing) AND (drug interactions OR macrolide statin interaction)', ('statin', 'klaritromisin', 'ilaç etkileşim')),
 ('prevention.general', 'Koruyucu bakım', 'Çürük/periodontal risk, florür, fissür örtücü, diyet/hijyen ve risk temelli takip.', '(preventive dentistry OR fluoride OR dental sealant) AND (risk assessment OR prevention)', ('florür', 'fissür örtücü', 'koruyucu')),
 ('orofacial_pain.general', 'Orofasiyal ağrı değerlendirmesi', 'Eklem/çiğneme kası, nöropatik veya açıklanamayan yüz ağrısı; diş kaynaklı varsayılmaz.', '(orofacial pain OR temporomandibular disorder) AND (diagnosis OR management)', ('yüz ağrı', 'çene eklem')),
)
TOPIC_REGISTRY = {ident: {'id': ident, 'branch': ident.split('.')[0], 'label': label,
    'scope': scope, 'query': query, 'triggers': triggers}
    for ident, label, scope, query, triggers in _ROWS}


def semantic_catalogue():
    """Local model context only; no patient data and no model-editable queries."""
    return [{'id': t['id'], 'branch': BRANCH_LABELS[t['branch']], 'label': t['label'], 'scope': t['scope']}
            for t in TOPIC_REGISTRY.values()]


def discovery_terms(topic):
    """Discovery hints from server-owned clinical queries, never opaque ID tokens."""
    import re
    row = TOPIC_REGISTRY.get(topic)
    if not row:
        return ()
    excluded = {'or', 'and', 'general', 'dental', 'oral', 'dentistry', 'treatment',
        'management', 'assessment', 'diagnosis', 'care', 'selection', 'complications',
        'failure', 'risk', 'planning', 'patient', 'patients', 'children', 'medical',
        'special', 'health', 'needs', 'adverse', 'effects', 'effectiveness', 'local',
        'disease', 'safety', 'monitoring', 'early', 'indications', 'maintenance'}
    terms = tuple(dict.fromkeys(word for word in re.findall(r'[a-z]+', row['query'].casefold())
                               if len(word) >= 4 and word not in excluded))
    return terms + row['triggers']
