"""Regressions from the real 20-turn audit; provider output is controlled here."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.academic_quiz import parse_quiz,render_quiz,pack_evidence,restore_quizzes,grade_previous_quiz
from app.academic_request_understanding import StudyRequest,UnderstandingResult,parse_request,retrieve_understood_course_context


def quiz():
    return {'questions':[{'stem':'Frankfort düzlemi Porion dışında hangi noktadan geçer?',
        'options':['Basion','Orbitale','Sella','Gonion','Nasion'],'correct':'B',
        'rationale':'Kaynak Frankfort düzlemini Porion ve Orbitale ile tanımlar.',
        'fact':'Frankfort düzlemi Porion ve Orbitale noktalarından geçer.',
        'source':'Orto.pdf, sayfa 18','material_id':24,'page':18}]}


def evidence():
    return [SimpleNamespace(material_id=24,page_start=18,page_end=18,display_name='Orto.pdf')]


def history(data=None):
    data=data or quiz()
    return [{'role':'ASSISTANT','content':render_quiz(data),'quiz':data}]


def raw_plan(**kwargs):
    return json.dumps(dict(resolved_query='Son seti puanla',operation='solve',scope='topic',
        count=None,difficulty=None,clarification='',retrieval_queries=[],source_kind='notes',depth='standard',
        needs_visual=False,continue_source=False,grade_previous_set=True,
        quiz_answers=[{'number':1,'choice':'B'}],**kwargs))


@pytest.mark.parametrize('mutation',[
    lambda q:q['questions'].clear(),
    lambda q:q['questions'][0]['options'].pop(),
    lambda q:q['questions'][0]['options'].append('Ek'),
    lambda q:q['questions'][0]['options'].__setitem__(0,'Orbitale'),
    lambda q:q['questions'][0].__setitem__('correct','F'),
    lambda q:q['questions'][0].__setitem__('rationale',''),
    lambda q:q['questions'][0].__setitem__('fact',''),
    lambda q:q['questions'][0].__setitem__('material_id',99),
    lambda q:q['questions'][0].__setitem__('page',19),
    lambda q:q['questions'][0].__setitem__('page',True),
    lambda q:q['questions'][0].__setitem__('stem',''),
])
def test_rejects_malformed_or_unowned_questions(mutation):
    q=quiz();mutation(q)
    with pytest.raises(ValueError):parse_quiz(json.dumps(q),1,evidence=evidence())


def test_live_basion_answer_in_stem_is_rejected():
    q=quiz();q['questions'][0].update(stem="Foramen occipitale magnum'un ön kenarının en alt noktası olan sefalometrik nokta, hangi yapının tanımına aittir?",
        options=['Meatus acusticus externus','Orbita çukuru','Sella turcica','Mandibula ramusu','Foramen occipitale magnum'],correct='E')
    with pytest.raises(ValueError,match='exposed'):parse_quiz(json.dumps(q),1,evidence=evidence())


def test_same_fact_with_new_stem_and_choices_is_rejected():
    q=quiz();q['questions'][0]['stem']='Orbitale ile birlikte Frankfort düzleminde hangi nokta bulunur?'
    with pytest.raises(ValueError,match='repeated'):parse_quiz(json.dumps(q),1,history())


def test_key_hidden_but_can_be_explicitly_requested():
    text=render_quiz(quiz())
    assert 'Cevap anahtarı' not in text and 'Kaynak Frankfort' not in text
    assert '1. B — Kaynak Frankfort' in render_quiz(quiz(),True)


@pytest.mark.parametrize('changed', ['answer','version','malformed','legacy'])
def test_invalidated_persisted_keys_are_not_reused(changed):
    original=history();versions=[(24,'file',5,'v1',None)]
    packed=pack_evidence('[]',quiz(),original[0]['content'],versions)
    if changed=='answer': original[0]['content']+=' changed'
    if changed=='version': versions=[(24,'file',5,'v2',None)]
    if changed=='malformed': packed='broken json'
    if changed=='legacy':packed='[]'
    original[0].pop('quiz');restore_quizzes(original,[SimpleNamespace(source_evidence_json=packed)],versions)
    assert 'quiz' not in original[0]


def test_saved_key_roundtrip_and_local_totals():
    q=quiz()
    for i in range(2,6):
        item=copy.deepcopy(q['questions'][0]);item['fact']=str(i);item['stem']=f'Bağımsız soru {i}?';item['correct']='C';q['questions'].append(item)
    turns=history(q);text=turns[0]['content'];turns[0].pop('quiz')
    versions=[(24,'file',5,'v1',None)]
    packed=pack_evidence('[]',q,text,versions)
    restore_quizzes(turns,[SimpleNamespace(source_evidence_json=packed)],versions)
    assert turns[0]['quiz']==q
    answer=grade_previous_quiz(turns,((1,'A'),(2,'B'),(3,'C'),(4,'D'),(5,'E')))
    assert 'Toplam 5 soru: 1 doğru, 4 yanlış, 0 boş.' in answer


def test_grade_route_does_not_search_attach_or_call_generation(monkeypatch):
    plan=parse_request(raw_plan())
    never=Mock(side_effect=AssertionError('No source or provider work allowed'))
    monkeypatch.setattr('app.academic_semantic_retrieval.retrieve_semantic_context',never)
    monkeypatch.setattr('app.study_ai_v2.get_provider',never)
    from app.academic_dense_retrieval import prepare_query_embedding
    understood=UnderstandingResult(plan=plan,attempted=True)
    assert prepare_query_embedding(understood,session_factory=never,owner_user_id=1,course_id=2) is None
    result=retrieve_understood_course_context(None,understanding=understood,recent_history=history(),query='B')
    from app.study_ai_v2 import ask_rag_v2
    assert '1 doğru, 0 yanlış, 0 boş' in ask_rag_v2('Orto','B',history(),result)
    assert not result.evidence and not result.attachments and not result.source_batches
    never.assert_not_called()


def test_legacy_or_newer_unkeyed_set_does_not_fall_back_to_course_scan():
    turns=history()+[{'role':'ASSISTANT','content':'### Soru 1\nBaşka set?\nA) A\nB) B'}]
    assert 'kayıtlı değil' in grade_previous_quiz(turns,((1,'B'),))


def test_clarification_300_to_1200_chars_no_longer_discards_valid_request():
    data=json.loads(raw_plan());data.update(operation='clarify',grade_previous_set=False,quiz_answers=[],clarification='Eksik hasta verileri. '*25)
    assert parse_request(json.dumps(data)).operation=='clarify'
    data['clarification']='x'*1201
    with pytest.raises(ValueError,match='clarification'):parse_request(json.dumps(data))


def test_planner_never_receives_hidden_key(monkeypatch):
    from app.academic_request_understanding import interpret_request
    call=Mock(return_value=raw_plan())
    interpret_request('1B',history(),call=call)
    payload=json.loads(call.call_args.args[0])
    assert set(payload['recent_dialogue'][0])=={'role','content'}
    assert 'correct' not in payload['recent_dialogue'][0]


def test_single_text_batch_generates_and_keeps_key_in_one_provider_call(monkeypatch):
    import app.study_ai_v2 as module
    from app.study_retrieval_v2 import RetrievalResult
    model=Mock();model.generate_stream.return_value=iter([json.dumps(quiz())])
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'get_provider',lambda name:model)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    child=RetrievalResult(note_context=['Frankfort: Porion ve Orbitale.'],evidence=evidence(),evidence_sufficient=True)
    parent=RetrievalResult(source_batches=[child],study_task={'operation':'generate_questions','source_kind':'notes','count':1,'quiz_contract':True})
    output=module.ask_rag_v2('Orto','Bir soru',[],parent)
    assert '### Soru 1' in output and 'Cevap anahtarı' not in output
    assert parent.generated_quiz['questions'][0]['correct']=='B'
    model.generate_stream.assert_called_once()
    assert model.generate_stream.call_args.kwargs['response_schema']['required']==['questions']


def test_quiz_repair_is_once_and_invalid_draft_never_emitted(monkeypatch):
    import app.study_ai_v2 as module
    from app.study_retrieval_v2 import RetrievalResult
    bad=quiz();bad['questions'][0]['correct']='F'
    model=Mock();model.generate_stream.side_effect=[iter([json.dumps(bad)]),iter([json.dumps(quiz())])]
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'get_provider',lambda name:model)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    result=RetrievalResult(note_context=['Kaynak'],evidence=evidence(),evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':1,'quiz_contract':True})
    assert '### Soru 1' in module.ask_rag_v2('Orto','Bir soru',[],result)
    assert model.generate_stream.call_count==2
    assert result.generated_quiz['questions'][0]['correct']=='B'


def test_second_bad_quiz_fails_without_a_third_call(monkeypatch):
    import app.study_ai_v2 as module
    from app.study_retrieval_v2 import RetrievalResult
    bad=quiz();bad['questions'][0]['correct']='F'
    model=Mock();model.generate_stream.side_effect=[iter([json.dumps(bad)]),iter([json.dumps(bad)])]
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'get_provider',lambda name:model)
    result=RetrievalResult(note_context=['Kaynak'],evidence=evidence(),evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':1,'quiz_contract':True})
    with pytest.raises(module.StudyAIError): list(module.stream_rag_v2('Orto','Bir soru',[],result))
    assert model.generate_stream.call_count==2 and result.generated_quiz is None
