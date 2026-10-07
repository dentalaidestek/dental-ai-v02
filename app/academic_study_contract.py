"""Source-backed output requirements shared by buttons and natural requests."""
from app.academic_task_language import parse_study_operation, study_priority_request
from app.dental_query_intent import classify_dental_study_plan


def study_output_rules(question: str, headings: list[str]) -> str:
    operation = parse_study_operation(question)
    if not operation or operation.past:
        return ''
    rules = []
    from app.academic_request_slots import output_slot_rules
    slot_rules = output_slot_rules(question)
    if slot_rules:
        rules.append(slot_rules)
    priority = study_priority_request(question.split(' — ')[-1])
    if priority == 'source_emphasis':
        rules.append('Kaynak vurguları: hocanın işaretlediği, altını çizdiği veya özellikle '
                     'vurguladığı yerleri ancak getirilen sayfa görsellerinde veya açık '
                     'kaynak ifadesinde gerçekten görülüyorsa belirt. Kanıtlanan yerleri '
                     'sayfa ve başlıkla göster. Sırf bir bilgi önemli diye hocanın '
                     'vurgusu sayma. İşaret görülmezse yalnız incelenen sayfalarda '
                     'doğrulanamadığını söyle; tüm dosyada yok deme. İncelenmeyen '
                     'sayfalar için sayfa numarası iste; sınav önerisini gerçek kaynak '
                     'vurgusundan açıkça ayır.')
    elif priority == 'exam_points' or operation.task == 'exam_points':
        rules.append('Sınav öncelikleri: mevcut konu veya not kapsamındaki kanıtlardan '
                     'ayırt edici tanımları, karşılaştırmaları ve değerleri seç; her biri '
                     'için neden çalışılması gerektiğini ve nasıl sorulabileceğini '
                     'açıkla. Bunları çalışma önerisi olarak sun; hocanın kesin '
                     'soracağı veya vurguladığı bilgi olarak gösterme. Önceki seçime '
                     'itiraz varsa aynı noktaları tekrarlamak yerine kanıtlı alternatifleri incele.')
    if operation.task == 'summarize':
        rules.append('Özet: önce getirilen kanıtların ana başlıklarını listele; ardından '
                     'her başlığın sınav açısından önemli noktalarını ayrı ver. '
                     'Çok başlıklı kanıtı tek başlığa indirgeme; özeti tek bir kavramla bitirme.')
    elif operation.task == 'explain':
        rules.append('Öğretme: getirilen başlıkları ayrı ayrı işle. Her başlıkta kanıtın '
                     'desteklediği tanımı, neden-sonuç mantığını, ayırt edici ayrıntıları '
                     've varsa örneği açıkla. Yalnız kısa tanımlar sıralamakla yetinme. '
                     'Kaynakta olmayan örnek veya bağlantı uydurma.')
    if operation.generate:
        plan = classify_dental_study_plan(question)
        count = plan.count if plan else None
        rules.append('Yeni soru üretimi: not kanıtlarından sorular oluştur; kaynak sorularını '
                     'çözme veya cevaplarını açıklama. Soruları kanıtta bulunan başlıklara '
                     'dağıt, aynı bilgiyi tekrar tekrar sorma. Çeldiricileri kaynak '
                     'bağlamıyla tutarlı kur. Her soruyu Soru N başlığıyla başlat. '
                     + (f'İstenen toplam sayı {count}; tek tek çalışma istenmediyse bu turda '
                        'tamamını ver. ' if count else '')
                     + 'Cevap anahtarını kullanıcı açıkça istemeden gösterme; sonrasında '
                     'kullanıcının cevaplarını bekle.')
    if rules:
        rules.append('Yalnız seçilen kanıtın kapsamını temsil et. Görülmeyen başlıkların '
                     'işlendiğini veya bütün dosyanın tamamlandığını iddia etme. '
                     'Kanıtta yeterli bilgi yoksa eksikliği açıkça belirt.')
        rules.append('Getirilen kaynak başlıkları: ' + (', '.join(dict.fromkeys(headings)) or 'etiketlenmemiş'))
    return '\n'.join(rules)
