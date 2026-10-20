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


def test_numbered_truth_metadata_does_not_duplicate_statement_prose():
    q=question()
    q['statements']=[{'number':i,'true':s['true']} for i,s in enumerate(q['statements'],1)]
    assert validate(q)['questions'][0]['correct']=='D'


@pytest.mark.parametrize('damage',['order','missing_stem','duplicate_stem','wrong_truth','empty_statement'])
def test_numbered_truth_metadata_still_enforces_display_and_key(damage):
    q=question()
    q['statements']=[{'number':i,'true':s['true']} for i,s in enumerate(q['statements'],1)]
    if damage=='order':q['statements'][1]['number']=1
    elif damage=='missing_stem':q['stem']=q['stem'].replace('II. Risk kesin sonuçtur.\n','')
    elif damage=='duplicate_stem':q['stem']=q['stem'].replace('III.','II.')
    elif damage=='wrong_truth':q['statements'][1]['true']=True
    else:q['stem']=q['stem'].replace('Risk kesin sonuçtur.','')
    with pytest.raises(ValueError):validate(q)


def test_bare_answers_get_results_without_unsolicited_explanations():
    from app.academic_quiz import grade_previous_quiz
    quiz={'questions':[question(),question()]}
    history=[{'role':'ASSISTANT','content':'Saved questions','quiz':quiz}]
    result=grade_previous_quiz(history,((1,'D'),(2,'B')))
    assert '| 1 | D | D | Doğru |' in result
    assert '| 2 | B | D | Yanlış |' in result
    assert '1 doğru, 1 yanlış, 0 boş' in result
    assert '**Soru ' not in result and question()['rationale'] not in result
    explained=grade_previous_quiz(history,((1,'D'),(2,'B')),explain=True)
    assert question()['rationale'] in explained and question()['source'] in explained


def test_previous_detailed_feedback_does_not_hide_active_quiz():
    from app.academic_quiz import grade_previous_quiz,previous_quiz_key
    history=[{'role':'ASSISTANT','content':'Original set','quiz':{'questions':[question()]}}]
    receipt=grade_previous_quiz(history,((1,'B'),),explain=True)
    history.append({'role':'ASSISTANT','content':receipt})
    assert '| 1 | D | D | Doğru |' in grade_previous_quiz(history,((1,'D'),))
    assert '**1. D**' in previous_quiz_key(history)
    history.append({'role':'ASSISTANT','content':'### Soru 1\nYeni soru hangisidir?\nA) Bir\nB) İki'})
    assert 'kayıtlı değil' in grade_previous_quiz(history,((1,'A'),))
