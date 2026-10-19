import json
from copy import deepcopy
import pytest
from app.academic_quiz import parse_quiz


def question():
    return {'stem':'Hangileri doğrudur?\nI. Risk olasılıktır.\nII. Risk kesin sonuçtur.\nIII. İlişki nedensellik değildir.',
        'options':['Yalnız I','Yalnız II','I ve II','I ve III','I, II ve III'],
        'correct':'D','rationale':'I ve III doğrudur.','fact':'Risk, ilişki ve nedensellik ayrımları.',
        'source':'Not.pdf, sayfa 1','material_id':1,'page':1,'topic':'Risk kavramları','asked_truth':True,
        'statements':[{'text':'Risk olasılıktır.','true':True},{'text':'Risk kesin sonuçtur.','true':False},
            {'text':'İlişki nedensellik değildir.','true':True}],
        'option_combinations':[[1],[2],[1,2],[1,3],[1,2,3]]}


def validate(q):return parse_quiz(json.dumps({'questions':[q]},ensure_ascii=False),1,require_quality=True)


def test_valid_multi_statement_key_matches_actual_displayed_option():
    assert validate(question())['questions'][0]['correct']=='D'


@pytest.mark.parametrize('damage',['key','displayed_option','truth','missing','bool_coercion','stem'])
def test_statement_errors_are_rejected_before_publishing(damage):
    q=question()
    if damage=='key':q['correct']='C'
    elif damage=='displayed_option':q['options'][3]='II ve III'
    elif damage=='truth':q['statements'][1]['true']=True
    elif damage=='missing':q['statements']=[];q['option_combinations']=[]
    elif damage=='bool_coercion':q['statements'][0]['true']='true'
    else:q['statements'][0]['text']='Not present in the question'
    with pytest.raises(ValueError):validate(q)


def test_false_statement_question_uses_requested_polarity():
    q=question();q['asked_truth']=False;q['correct']='B'
    q['stem']=q['stem'].replace('doğrudur','yanlıştır')
    assert validate(q)['questions'][0]['correct']=='B'


def test_requested_distinct_topics_cannot_be_cosmetic_duplicates():
    first=question();second=deepcopy(first)
    second['fact']='Başka bir bilginin sınanması.'
    second['stem']=second['stem'].replace('Risk','RİSK')
    with pytest.raises(ValueError,match='repeated main topic'):
        parse_quiz(json.dumps({'questions':[first,second]}),2,require_quality=True,distinct_topics=True)


def test_old_saved_quizzes_remain_readable_but_new_generation_requires_metadata():
    old=question()
    for key in ('topic','asked_truth','statements','option_combinations'):old.pop(key)
    assert parse_quiz(json.dumps({'questions':[old]}),1)
    with pytest.raises(ValueError):parse_quiz(json.dumps({'questions':[old]}),1,require_quality=True)


def test_repair_receives_exact_validation_failure_and_never_emits_bad_set(monkeypatch):
    from types import SimpleNamespace
    from app import study_ai_v2 as ai
    from app.study_retrieval_v2 import RetrievalResult
    invalid=question();invalid['correct']='C'
    replies=iter([json.dumps({'questions':[invalid]}),json.dumps({'questions':[question()]})])
    calls=[]
    class Provider:
        last_finish_reason='STOP'
        def generate_stream(self,**options):
            calls.append(options)
            yield next(replies)
    target=SimpleNamespace(provider='test',model='test')
    monkeypatch.setattr(ai,'_generation_targets',lambda:[target])
    monkeypatch.setattr(ai,'target_available',lambda t:True)
    monkeypatch.setattr(ai,'get_provider',lambda p:Provider())
    monkeypatch.setattr(ai,'report_target_success',lambda t:None)
    monkeypatch.setattr(ai,'_prompt',lambda *a:'Source-backed question request')
    result=RetrievalResult(note_context=['Risk olasılıktır.'],evidence_sufficient=True,
        evidence=[SimpleNamespace(material_id=1,page_start=1,page_end=1,display_name='Not.pdf')],
        study_task={'operation':'generate_questions','quiz_contract':True,'count':1})
    answer=''.join(ai.stream_rag_v2('Perio','Bir soru',[],result))
    assert len(calls)==2
    assert 'Kesin denetim nedeni: statement key mismatch' in calls[1]['prompt']
    assert result.generated_quiz['questions'][0]['correct']=='D'
    assert '"correct"' not in answer and 'Cevap anahtarı' not in answer


def test_unexpected_error_text_is_not_disclosed_as_repair_diagnostic():
    from app.academic_quiz import quiz_failure_reason
    assert quiz_failure_reason(ValueError('private model text'))=='invalid quiz structure'
