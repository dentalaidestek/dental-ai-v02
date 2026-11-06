"""Source-informed history scope; recorded is not complete, normal or clinically verified.

ADA medical/dental history and SDCEP patient histories / acute assessment inform
these public prompts. Local identity/contact data and unrelated private life are
deliberately outside this voice checklist.
"""
SOURCES = (
    'https://izdo.org/img/userfiles/files/TDB_Hasta_Anamnez_Formu.pdf',
    'https://www.ada.org/resources/practice/practice-management/medical-dental-health-history',
    'https://psm.sdcep.org.uk/topics/record-keeping/records-required/patient-histories/',
    'https://www.acutedentalproblems.sdcep.org.uk/guidance/overarching-principles/patient-assessment-and-record-keeping/',
)
GROUPS = (
    ('chief_complaint', 'Başvuru ve yakınmanın öyküsü', 'Bölge, başlangıç/süre, seyir, tetikleyiciler, eşlik eden belirtiler ve yakınma için alınmış ilaç.'),
    ('medical_history', 'Hastanın sağlık öyküsü', 'Mevcut/geçmiş hastalık, ameliyat, hastane ve ilgili tetkik; kalp/kapak, diyabet, kanama, akciğer/astım, nöbet, böbrek/karaciğer, tiroid, baş-boyun radyoterapisi ve ilgiliyse gebelik/emzirme bağlamı. Önceki kayıttan beri değişiklik ve olumsuz beyan korunur; listeden hastalık veya gebelik varsayılmaz.'),
    ('medications', 'İlaçların kullanım öyküsü', 'Düzenli, kısa süreli, aralıklı/enjeksiyon, reçetesiz ilaç ve destek; adı, kullanımı ve işlemle ilgili doz/zaman ayrıntıları. Düzenli yok beyanı bütün kullanımları dışlamaz.'),
    ('allergies', 'Alerji ve önceki reaksiyonlar', 'İlgili madde ve bildirilen reaksiyon; ilaç/anestezi/materyal reaksiyonu ile tahammülsüzlük ayırt edilmeden kesin alerji üretilmez.'),
    ('dental_history', 'Önceki diş tedavileri ve deneyimler', 'İşlem/bölge/zaman, önceki sorunlar, anestezi deneyimi ve iyileşme/kanama öyküsü; mevcut şikâyet ve bugün planlanan işlemle karıştırılmaz.'),
    ('family_history', 'Aile sağlık öyküsü', 'Yakına ait ilgili hastalık ve yakınlık; hastanın kendi hastalığı veya yokluk beyanıyla birleştirilmez.'),
    ('oral_habits', 'Ağız bakımı ve alışkanlıklar', 'Bakım/ara yüz temizliği, tütün, beslenme/asit ve sıkma gibi muayeneyle ilgili beyanlar; söylenmeyen sıklık veya neden eklenmez.'),
)


def scope():
    return [{'field': key, 'label': label, 'focus': focus} for key, label, focus in GROUPS]


def review(fields):
    return [{'field': key, 'label': label,
             'state': 'recorded' if fields.get(key, {}).get('value', '').strip() else 'not_recorded'}
            for key, label, _ in GROUPS]
