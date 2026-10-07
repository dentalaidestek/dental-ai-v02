"""Source-backed output requirements shared by buttons and natural requests."""
from app.academic_task_language import parse_study_operation
from app.dental_query_intent import classify_dental_study_plan


def study_output_rules(question: str, headings: list[str]) -> str:
    operation = parse_study_operation(question)
    if not operation or operation.past:
        return ''
    rules = []
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
