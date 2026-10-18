"""Generated-set follow-ups reuse verified metadata, never rescan the notes."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.academic_quiz import render_quiz, previous_quiz_key, restore_quizzes, pack_evidence
from app.academic_request_understanding import (
    parse_request, interpret_request, retrieve_understood_course_context, UnderstandingResult,
)
from app.study_retrieval_v2 import RetrievalResult


def plan_json(**changes):
    data = dict(resolved_query='Son oluşturulan soruların cevap anahtarını açıkla',
        operation='answer', scope='topic', count=None, difficulty=None, clarification='',
        retrieval_queries=[], source_kind='notes', depth='standard', needs_visual=False,
        continue_source=False, reveal_previous_key=True)
    data.update(changes)
    return json.dumps(data)


def quiz():
    return {'questions': [dict(stem='Risk ilişkisi hakkında hangileri doğrudur?\nI. Birinci öncül\nII. İkinci öncül\nIII. Üçüncü öncül',
        options=['Yalnız I', 'Yalnız II', 'I ve II', 'II ve III', 'I, II ve III'],
        correct='C', rationale='Kaynakla doğrulanan gerekçe', fact='Risk ilişkisi',
        source='Not.pdf, sayfa 2', material_id=1, page=2)]}


def test_restored_model_key_is_returned_without_sql_or_generation(monkeypatch):
    import app.study_ai_v2 as generation
    saved=quiz(); answer=render_quiz(saved)
    versions={'1': 2}
    row=SimpleNamespace(content=answer, source_evidence_json=pack_evidence('[]',saved,answer,versions))
    history=[{'role':'ASSISTANT','content':answer}]
    restore_quizzes(history,[row],versions)
    assert history[0]['quiz']['questions'][0]['correct']=='C'
    session=Mock()
    never=Mock(side_effect=AssertionError('No source scan or paid generation for a saved key'))
    monkeypatch.setattr('app.academic_semantic_retrieval._fts_rows',never)
    monkeypatch.setattr(generation,'get_provider',never)
    result=retrieve_understood_course_context(session,
        understanding=UnderstandingResult(plan=parse_request(plan_json())),
        recent_history=history, owner_user_id=1, course_id=6)
    output=generation.ask_rag_v2('Perio','Cevapları ne peki',history,result)
    assert '**1. C**' in output and 'Kaynakla doğrulanan gerekçe' in output
    assert 'Not.pdf, sayfa 2' in output and 'Birinci öncül' not in output
    session.exec.assert_not_called(); never.assert_not_called()


@pytest.mark.parametrize('mutation',['content','versions'])
def test_modified_answer_or_index_never_reuses_an_unverified_key(mutation):
    saved=quiz(); answer=render_quiz(saved); versions={'1':2}
    row=SimpleNamespace(source_evidence_json=pack_evidence('[]',saved,answer,versions))
    history=[{'role':'ASSISTANT','content':answer+(' changed' if mutation=='content' else '')}]
    restore_quizzes(history,[row],{'1':3} if mutation=='versions' else versions)
    assert 'kayıtlı değil' in previous_quiz_key(history)


def test_never_answers_an_older_set_when_the_latest_has_no_verified_metadata():
    old=quiz(); content=render_quiz(old)
    history=[{'role':'ASSISTANT','content':content,'quiz':old},
        {'role':'USER','content':'Yeni sorular'},
        {'role':'ASSISTANT','content':content.replace('Risk ilişkisi','Başka konu')}]
    assert 'kayıtlı değil' in previous_quiz_key(history)


def test_key_route_discards_unused_searches_and_cannot_be_used_for_grading():
    plan=parse_request(plan_json(retrieval_queries=['unused search'],source_subjects=['unused subject']))
    assert not plan.retrieval_queries and not plan.source_subjects
    with pytest.raises(ValueError):
        parse_request(plan_json(operation='solve',grade_previous_set=True,
            quiz_answers=[{'number':1,'choice':'B'}]))


def test_current_message_and_original_conditions_reach_model_without_rewriting():
    from app.study_ai_v2 import _prompt, V2_SYSTEM_PROMPT
    original='10 öncüllü soru; her biri farklı ana başlıktan, alt başlıklar öncüllerde olsun.'
    correction='Bu soruların hiçbiri öncüllü değil ama'
    history=[{'role':'USER','content':original}, {'role':'ASSISTANT','content':'Hatalı set'}]
    call=Mock(return_value=plan_json(reveal_previous_key=False,operation='generate_questions',
        scope='course',count=10,resolved_query=original))
    understanding=interpret_request(correction,history,call=call,provider_name='anthropic')
    sent=json.loads(call.call_args.args[0])
    assert sent['request']==correction and sent['recent_dialogue'][0]['content']==original
    result=RetrievalResult(resolved_query=understanding.plan.resolved_query,
        note_context=['Kaynak bilgileri'],evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':10,'quiz_contract':True})
    prompt=_prompt('Perio',correction,result,history)
    assert f'KULLANICININ ÖZGÜN MESAJI:\n{correction}' in prompt
    assert original in prompt
    assert 'I., II., III.' in V2_SYSTEM_PROMPT


def test_subjects_and_searches_can_share_one_bounded_owned_query():
    from app.study_retrieval_v2 import _fts_rows
    from app.academic_request_understanding import MAX_SOURCE_SEARCHES
    session=Mock()
    session.get_bind.return_value.dialect.name='postgresql'
    session.exec.return_value.all.return_value=[]
    groups=tuple(f'"subject{i}"' for i in range(2*MAX_SOURCE_SEARCHES))
    kwargs=dict(owner_user_id=17,course_id=23,lexical_query=' OR '.join(groups),
        query_vector=None,embedding_provider='',embedding_model='',limit=48)
    _fts_rows(session,**kwargs,lexical_groups=groups)
    session.exec.assert_called_once()
    params=session.exec.call_args.kwargs['params']
    assert params['lexical_groups']==list(groups)
    assert 17 in params.values() and 23 in params.values()
    with pytest.raises(ValueError,match='invalid lexical search groups'):
        _fts_rows(session,**kwargs,lexical_groups=groups+('"overflow"',))


def test_statement_set_keeps_original_request_and_uses_one_generation_call(monkeypatch):
    import app.study_ai_v2 as generation
    from app.study_provider import ProviderTarget
    provider=Mock()
    provider.generate_stream.return_value=iter([json.dumps(quiz())])
    monkeypatch.setattr(generation,'_generation_targets',lambda:[ProviderTarget('anthropic','test-model')])
    monkeypatch.setattr(generation,'get_provider',lambda _:provider)
    monkeypatch.setattr(generation,'target_available',lambda _:True)
    monkeypatch.setattr(generation,'report_target_success',lambda _:None)
    question='Öncüllü bir soru hazırla; alt başlıkları öncüllere dağıt, cevapları gizle.'
    result=RetrievalResult(resolved_query=question,note_context=['Risk ilişkisi kaynak bilgileri'],
        evidence=[SimpleNamespace(material_id=1,page_start=2,page_end=2,display_name='Not.pdf')],
        evidence_sufficient=True,study_task={'operation':'generate_questions','count':1,
            'quiz_contract':True,'show_quiz_answers':False})
    output=generation.ask_rag_v2('Perio',question,[],result)
    provider.generate_stream.assert_called_once()
    sent=provider.generate_stream.call_args.kwargs
    assert question in sent['prompt'] and 'I., II., III.' in sent['system_prompt']
    assert all(label in output for label in ['I. Birinci','II. İkinci','III. Üçüncü'])
    assert 'Cevap anahtarı' not in output
    assert result.generated_quiz['questions'][0]['correct']=='C'


def test_planner_reviews_actual_options_and_saved_rationale_in_its_existing_call():
    saved=quiz()
    saved['questions'][0]['correct']='B'  # Letter disagrees with the I+II rationale.
    history=[{'role':'ASSISTANT','content':render_quiz(saved),'quiz':saved}]
    correction={'number':1,'choice':'C','rationale':'I ve II doğrudur; bu birleşim C şıkkındadır.'}
    call=Mock(return_value=plan_json(quiz_key_corrections=[correction]))
    result=interpret_request('Cevapları ne peki?',history,call=call,provider_name='anthropic')
    call.assert_called_once()
    sent=json.loads(call.call_args.args[0])
    assert sent['recent_quiz']==saved
    assert sent['recent_dialogue'][0]['content'].startswith('[Son soru setinin tam içeriği')
    answer=previous_quiz_key(history,result.plan.quiz_key_corrections)
    assert '**1. C**' in answer and '**1. B**' not in answer
    assert 'Not.pdf, sayfa 2' in answer
    assert saved['questions'][0]['correct']=='B'  # No silent mutation of history.


@pytest.mark.parametrize('corrections',[
    [{'number':1,'choice':'Z','rationale':'No'}],
    [{'number':1,'choice':'C','rationale':''}],
    [{'number':1,'choice':'C','rationale':'x'},{'number':1,'choice':'D','rationale':'y'}],
])
def test_invalid_key_review_cannot_change_the_saved_set(corrections):
    with pytest.raises(ValueError):
        parse_request(plan_json(quiz_key_corrections=corrections))


def test_key_review_cannot_address_a_question_outside_the_latest_set():
    saved=quiz();history=[{'role':'ASSISTANT','content':render_quiz(saved),'quiz':saved}]
    answer=previous_quiz_key(history,[{'number':2,'choice':'A','rationale':'Wrong set'}])
    assert 'eşleşmedi' in answer and '**1.' not in answer


def test_grading_uses_the_same_model_reviewed_key_as_key_display():
    saved=quiz();saved['questions'][0]['correct']='B'
    history=[{'role':'ASSISTANT','content':render_quiz(saved),'quiz':saved}]
    correction={'number':1,'choice':'C','rationale':'I ve II doğru; seçenek C.'}
    plan=parse_request(plan_json(reveal_previous_key=False,grade_previous_set=True,
        operation='solve',quiz_answers=[{'number':1,'choice':'C'}],
        quiz_key_corrections=[correction]))
    result=retrieve_understood_course_context(Mock(),understanding=UnderstandingResult(plan=plan),
        recent_history=history,owner_user_id=1,course_id=6)
    assert '1 doğru, 0 yanlış' in result.prepared_answer
    assert saved['questions'][0]['correct']=='B'

