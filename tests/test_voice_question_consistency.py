"""Narrow, explicit denial checks; not medication reconciliation or clinical rules."""
import pytest
from app import voice_exam_core as core, voice_exam_final as final
from test_voice_exam_final import provider

NEGATIVE = 'Düzenli ilacım ve bildiğim alerjim yok.'

def test_extractor_cannot_ask_name_of_explicitly_denied_regular_medication():
    result = core.normalize({'transcript': NEGATIVE, 'follow_up_questions': [
        {'quote': 'Düzenli ilacım', 'question': 'Düzenli kullanılan ilaçların adı nedir?',
         'reason': 'İlaç adları belirtilmedi.', 'priority': 'REVIEW_AT_END'}]}, evidence=NEGATIVE)
    assert result['follow_up_questions'] == []

def test_final_cannot_truncate_negative_anchor_into_a_positive_regular_medication_question(monkeypatch):
    provider(monkeypatch, {'questions': [{'field': 'medications', 'quote': 'Düzenli ilacım',
        'text': 'Düzenli kullandığınız ilacın adı ve dozu nedir?'}], 'contradictions': [], 'clinical_items': []})
    assert final.finalize({'fields': {'medications': {'value': NEGATIVE, 'quote': NEGATIVE}}}, [])['questions'] == []

def test_live_full_negative_clause_with_punctuation_and_box_check_is_not_ambiguous(monkeypatch):
    provider(monkeypatch, {'questions': [{'field':'medications','quote':NEGATIVE,
        'text':'Düzenli ilaç kullanımı olup olmadığı tek cümlede belirsiz; kullanılan ilaç varsa adı ve dozu kayıtta yok. Kutu veya reçete ile netleştirin.'}],
        'contradictions':[],'clinical_items':[]})
    assert final.finalize({'fields':{'medications':{'value':NEGATIVE,'quote':NEGATIVE}}},[])['questions']==[]

@pytest.mark.parametrize('prefix',['Geçmiş: ','Önceden: ','Belirsiz: ','Planlanan: '])
def test_noncurrent_denial_does_not_answer_a_current_regular_use_question(monkeypatch,prefix):
    value=prefix+'Düzenli ilacım yok.'
    item={'field':'medications','quote':'Düzenli ilacım yok.', 'text':'Düzenli kullandığınız ilaçların adı nedir?'}
    provider(monkeypatch,{'questions':[item],'contradictions':[],'clinical_items':[]})
    assert final.finalize({'fields':{'medications':{'value':value,'quote':'Düzenli ilacım yok.'}}},[])['questions']==[item]

@pytest.mark.parametrize('statement,anchor,question', [
    (NEGATIVE, 'Düzenli ilacım', 'Ara sıra ağrı kesici veya haftalık iğne kullanıyor musunuz?'),
    ('Warfarin kullanıyorum, başka ilacım yok.', 'Warfarin kullanıyorum', 'Warfarinin dozu nedir?'),
    ('Düzenli bir ilaç kullanıyorum ama adını bilmiyorum.', 'Düzenli bir ilaç', 'İlacın adı nedir?'),
    ('Düzenli ilacım yok ama haftada bir iğnem var.', 'haftada bir iğnem var', 'İğnenin adı ve dozu nedir?'),
    ('Düzenli ilacım var, alerjim yok.', 'Düzenli ilacım', 'İlacın adı nedir?'),
    ('Düzenli ilacım yok. Amoksisilin başlayacağız.', 'Düzenli ilacım', 'Planlanan amoksisilinin dozu nedir?'),
    ('Düzenli ilacım yok. Yeni ilaç yazıldı.', 'Düzenli ilacım', 'Yeni reçete edilen ağrı kesicinin adı ve dozu nedir?'),
    ('Düzenli ilacım yok.', 'Düzenli ilacım', 'Düzenli başlanacak ilacın dozu nedir?'),
    ('Düzenli ilacım yok.', 'Düzenli ilacım', 'Önerilen düzenli ilacın adı nedir?'),
    ('Düzenli ilacım yok.', 'Düzenli ilacım', 'İlacın adı nedir?'),
    ('Düzenli ilacım yok. Diş için amoksisilin kullanıyorum.', 'Düzenli ilacım', 'Kullandığınız amoksisilinin dozu nedir?'),
    (NEGATIVE, 'Düzenli ilacım', 'Kullandığınız ilacın adı ve dozu nedir?'),
])
def test_distinct_or_actually_unknown_medication_questions_survive(statement,anchor,question):
    output=core.normalize({'transcript': statement,'follow_up_questions': [
        {'quote':anchor,'question':question,'reason':'Netleştirilmeli','priority':'REVIEW_AT_END'}]},evidence=statement)
    assert len(output['follow_up_questions']) == 1
