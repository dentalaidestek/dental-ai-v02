"""Contract/transport/routing tests, not a substitute for model accuracy evaluation."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.academic_request_understanding import interpret_request, parse_request, understand_study_request


def raw(**overrides):
    data = dict(resolved_query='Downs analizindeki yüz tiplerini açıkla', operation='explain',
                scope='topic', count=None, difficulty=None, clarification='', retrieval_queries=['Downs analiz yüz tipleri'])
    data.update(overrides)
    if data['scope'] == 'course' or data['operation'] == 'clarify':
        data['retrieval_queries'] = overrides.get('retrieval_queries', [])
    return json.dumps(data, ensure_ascii=False)


def test_interpreter_passes_full_original_dialogue_and_calls_once():
    history = [{'role':'user','content':'Kaynakta A ve B var'},
               {'role':'assistant','content':'A veya B; A değil, B. Önce neden, sonra önlem.'}]
    call = Mock(return_value=raw())
    out = interpret_request('Onlardan birini anlat ama ikinciye girme', history, call=call)
    assert out.attempted and out.plan.operation == 'explain'
    payload = json.loads(call.call_args.args[0])
    assert payload['recent_dialogue'] == history
    assert payload['request'] == 'Onlardan birini anlat ama ikinciye girme'
    call.assert_called_once()


@pytest.mark.parametrize('overrides', [
    {'count':True}, {'count':201}, {'count':0}, {'operation':['answer']},
    {'scope':'all_users'}, {'operation':'execute'}, {'resolved_query':''},
    {'clarification':'Different topic'}, {'difficulty':123}, {'count':1.5},
])
def test_invalid_contract_is_rejected(overrides):
    with pytest.raises(ValueError): parse_request(raw(**overrides))


def test_owner_and_chunk_identifiers_cannot_enter_contract():
    data = json.loads(raw()); data['owner_user_id'] = 99
    with pytest.raises(ValueError): parse_request(json.dumps(data))


def test_failure_has_one_attempt_and_no_exception_content_in_logs(caplog):
    call = Mock(side_effect=RuntimeError('SECRET-PATIENT-CONTENT'))
    out = interpret_request('Soru', [], call=call)
    assert out.attempted and out.plan is None and out.outcome == 'failed'
    call.assert_called_once()
    assert 'SECRET-PATIENT-CONTENT' not in caplog.text


def test_large_context_is_not_silently_truncated_or_sent(call=None):
    call = Mock(return_value=raw())
    out = interpret_request('Soru', [{'role':'assistant','content':'ğ'*32000}], call=call)
    assert not out.attempted and out.outcome == 'input_budget'
    call.assert_not_called()


def test_default_off_does_not_import_or_call_provider(monkeypatch):
    monkeypatch.delenv('STUDY_ACADEMIC_SEMANTIC_PLANNER', raising=False)
    assert understand_study_request('Yeni cümle', []).outcome == 'disabled'


def test_semantic_attempt_prevents_second_paid_recovery_call():
    from app.academic_recovery import recover_once
    initial = SimpleNamespace(clarification='', evidence_sufficient=False, semantic_planner_attempted=True)
    call = Mock()
    assert recover_once(question='Soru', history=[], initial=initial,
                        load_catalog=call, plan_call=call, retrieve=call, record=call) is initial
    call.assert_not_called()


def test_ambiguous_request_returns_clarification_before_any_source_query():
    from app.study_retrieval_v2 import retrieve_course_context_v2
    session = Mock()
    session.get_bind.return_value.dialect.name = 'postgresql'
    plan = parse_request(raw(operation='clarify', resolved_query='İkincisi', clarification='Hangi ikinci konu?'))
    out = retrieve_course_context_v2(session, owner_user_id=1, course_id=2,
                                   query='ikincisi', request_plan=plan)
    assert out.clarification == 'Hangi ikinci konu?'
    session.exec.assert_not_called()


def test_provider_structured_schema_is_request_local(monkeypatch):
    from app.study_provider import GeminiStudyProvider
    monkeypatch.setattr('app.study_provider.router_target_available', lambda *a: True)
    provider = GeminiStudyProvider()
    provider.response_schema = {'type':'object'}
    request = Mock(return_value={'candidates':[{'content':{'parts':[{'text':raw()}]}}]})
    monkeypatch.setattr(provider, '_request_json', request)
    provider.generate(model='gemini-2.5-flash-lite', system_prompt='Interpret',history=[],prompt='Input')
    payload = request.call_args.args[1]
    assert payload['generationConfig']['responseJsonSchema'] == {'type':'object'}
    assert payload['generationConfig']['responseMimeType'] == 'application/json'
    other = GeminiStudyProvider()
    monkeypatch.setattr(other,'_request_json',request)
    other.generate(model='model',system_prompt='Answer',history=[],prompt='Input')
    assert 'responseJsonSchema' not in request.call_args.args[1]['generationConfig']


def test_topic_plan_reaches_owned_lookup_and_does_not_expand_to_course(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    session = Mock(); session.get_bind.return_value.dialect.name = 'postgresql'
    lookup = Mock(return_value=[])
    monkeypatch.setattr(retrieval,'_fts_rows',lookup)
    plan = parse_request(raw(resolved_query='Florun kullanımını ayrıntılı açıkla', operation='explain', retrieval_queries=['Flor kullanım']))
    out = retrieval.retrieve_course_context_v2(session, owner_user_id=17, course_id=23,
        query='Bunu ayrıntılı öğret', recent_history=[{'role':'user','content':'Pulpitis tedavisi'}],
        request_plan=plan)
    assert out.resolved_query == plan.resolved_query
    assert out.retrieval_mode == 'fts'
    assert not out.evidence_sufficient
    assert lookup.call_args.kwargs['owner_user_id'] == 17
    assert lookup.call_args.kwargs['course_id'] == 23
    assert 'flor' in lookup.call_args.kwargs['lexical_query'].lower()
    assert 'pulpitis' not in lookup.call_args.kwargs['lexical_query'].lower()


def test_comparison_planned_phrases_get_independent_owned_candidate_groups(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    session = Mock(); session.get_bind.return_value.dialect.name = 'postgresql'
    lookup = Mock(return_value=[])
    monkeypatch.setattr(retrieval, '_fts_rows', lookup)
    plan = parse_request(raw(resolved_query='Hipofiz ile tiroid etkisini karşılaştır',
        operation='compare', retrieval_queries=['hipofiz', 'tiroid']))
    retrieval.retrieve_course_context_v2(session, owner_user_id=17, course_id=23,
        query='İkisinin farkı ne?', request_plan=plan)
    assert lookup.call_args_list[0].kwargs['lexical_groups'] == ('"hipofiz"', '"tiroid"')
    assert lookup.call_args_list[0].kwargs['owner_user_id'] == 17
    assert lookup.call_args_list[0].kwargs['course_id'] == 23


def test_course_plan_selects_coverage_with_owned_scope_and_count(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    from app.academic_coverage import build_coverage_plan
    session=Mock(); session.get_bind.return_value.dialect.name='postgresql'
    catalog=Mock(return_value=build_coverage_plan([],20))
    monkeypatch.setattr(retrieval,'get_or_build_coverage_plan',catalog)
    monkeypatch.setattr(retrieval,'_coverage_evidence_rows',Mock(return_value=[]))
    lookup=Mock(side_effect=AssertionError('Course plan must not become a topic FTS query'))
    monkeypatch.setattr(retrieval,'_fts_rows',lookup)
    plan=parse_request(raw(resolved_query='Tüm ders notlarından 20 zor soru üret',
                           operation='generate_questions',scope='course',count=20,difficulty='zor'))
    out=retrieval.retrieve_course_context_v2(session,owner_user_id=17,course_id=23,
        query='Her başlıktan dengeli olsun, yirmi zor test istiyorum',request_plan=plan)
    assert out.retrieval_mode=='coverage'
    assert not out.evidence_sufficient
    assert catalog.call_args.kwargs['owner_user_id']==17
    assert catalog.call_args.kwargs['course_id']==23
    assert catalog.call_args.kwargs['requested_count']==20


@pytest.mark.parametrize('searches', [[], [''], ['---'], ['x'*161], ['A']*5, [123]])
def test_topic_search_contract_rejects_unbounded_or_empty_search(searches):
    with pytest.raises(ValueError):
        parse_request(raw(retrieval_queries=searches))


def test_semantic_search_keeps_independent_comparison_subjects_and_quotes_operators():
    from app.study_retrieval_v2 import _semantic_fts_query
    assert _semantic_fts_query(('Süt dişi', 'Kalıcı dişi')) == '"Süt" "dişi" OR "Kalıcı" "dişi"'
    assert _semantic_fts_query(('A OR B -C',)) == '"A" "OR" "B" "C"'


def test_planned_search_bypasses_old_subject_parser(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    session = Mock(); session.get_bind.return_value.dialect.name = 'postgresql'
    lookup = Mock(return_value=[])
    monkeypatch.setattr(retrieval, '_fts_rows', lookup)
    monkeypatch.setattr(retrieval, '_fts_query', Mock(side_effect=AssertionError('old parser called')))
    plan = parse_request(raw(resolved_query='Downs analizinden 15 zor soru üret',
                            operation='generate_questions', count=15,
                            retrieval_queries=['Downs analiz']))
    retrieval.retrieve_course_context_v2(session, owner_user_id=17, course_id=23,
                                        query='15 zor soru', request_plan=plan)
    assert lookup.call_args.kwargs['lexical_query'] == '"Downs" "analiz"'
    assert lookup.call_args.kwargs['owner_user_id'] == 17
    assert lookup.call_args.kwargs['course_id'] == 23
