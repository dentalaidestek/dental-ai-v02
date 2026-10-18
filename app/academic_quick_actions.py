"""Exact server-defined UI commands; free-form student language still uses the planner."""
PROMPTS = {
    'summarize': 'Bu ders notlarını sınav odaklı ve yüksek verimli şekilde özetle. Önce ana başlıkları, sonra kritik ayrıntıları ver.',
    'teach': 'Bu ders notlarıyla adım adım çalışalım. İlk konudan başla: kısa bir açıklama ve nottan bir örnek ver, sonra anlamamı kontrol eden tek bir soru sor ve yanıtımı bekle. Sonraki anlatımı cevabıma göre ayarla.',
    'generate_questions': 'Bu ders notlarından 20 zorlayıcı çoktan seçmeli soru hazırla. Cevap anahtarını şimdilik gösterme; cevaplarımı değerlendirmek için bekle.',
}


def is_quick_action(message):
    return message in PROMPTS.values()


def quick_action_plan(message):
    from app.academic_request_understanding import StudyRequest
    operation=next((key for key,value in PROMPTS.items() if value==message),None)
    if operation is None:
        return None
    return StudyRequest(message,operation,'course',20 if operation=='generate_questions' else None,
        'zorlayıcı' if operation=='generate_questions' else None,'',
        depth='detailed' if operation=='teach' else 'standard',complete_sections=False)

