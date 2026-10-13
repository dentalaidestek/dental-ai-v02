"""Contract/transport/routing tests, not a substitute for model accuracy evaluation."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.academic_request_understanding import interpret_request, parse_request, understand_study_request


def raw(**overrides):
    data = dict(resolved_query='Downs analizindeki yüz tiplerini açıkla', operation='explain',
                scope='topic', count=None, difficulty=None, clarification='', retrieval_queries=['Downs analiz yüz tipleri'], source_kind='notes', depth='standard', needs_visual=False, continue_source=False)
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
    assert list(payload)[-1] == 'request'
    call.assert_called_once()


def test_planner_metadata_trace_never_contains_request_history_or_search_text(caplog):
    import logging
    with caplog.at_level(logging.INFO):
        result = interpret_request('PRIVATE-QUESTION',
            [{'role':'ASSISTANT', 'content':'PRIVATE-HISTORY'}],
            call=Mock(return_value=raw(resolved_query='PRIVATE-RESTATEMENT', retrieval_queries=['PRIVATE-SEARCH'])))
    assert result.trace_id
    assert f'trace={result.trace_id} stage=plan provider=gemini operation=explain scope=topic' in caplog.text
    assert all(text not in caplog.text for text in ['PRIVATE-QUESTION','PRIVATE-HISTORY','PRIVATE-RESTATEMENT','PRIVATE-SEARCH'])


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
    out = interpret_request('Soru', [{'role':'assistant','content':'ğ'*256000}], call=call)
    assert not out.attempted and out.outcome == 'input_budget'
    call.assert_not_called()


def test_old_disable_flag_cannot_switch_back_to_language_rules(monkeypatch):
    import app.study_provider as provider_module
    provider = Mock(api_key='test-only')
    provider.generate.return_value = raw()
    monkeypatch.setattr(provider_module, 'GeminiStudyProvider', lambda: provider)
    monkeypatch.setattr(provider_module, 'target_available', lambda target: True)
    monkeypatch.setenv('STUDY_ACADEMIC_SEMANTIC_PLANNER', '0')
    result = understand_study_request('Bunu anlat', [])
    assert result.outcome == 'interpreted' and result.attempted
    provider.generate.assert_called_once()


def test_planner_defaults_to_current_answer_model(monkeypatch):
    import app.study_provider as provider_module
    from app.study_ai_v2 import ACADEMIC_V2_MODEL
    provider = Mock(api_key='test-only')
    provider.generate.return_value = raw()
    monkeypatch.setattr(provider_module, 'GeminiStudyProvider', lambda: provider)
    monkeypatch.setattr(provider_module, 'target_available', lambda target: True)
    monkeypatch.delenv('STUDY_ACADEMIC_PLANNER_MODEL', raising=False)
    assert understand_study_request('Bunu anlat', []).outcome == 'interpreted'
    assert provider.generate.call_args.kwargs['model'] == ACADEMIC_V2_MODEL


def test_unvalidated_local_routing_is_not_enabled_by_default(monkeypatch):
    import app.study_provider as provider_module
    provider=Mock(api_key='test-only')
    provider.generate.return_value=raw()
    monkeypatch.setattr(provider_module,'GeminiStudyProvider',lambda:provider)
    monkeypatch.setattr(provider_module,'target_available',lambda target:True)
    monkeypatch.delenv('STUDY_ACADEMIC_LOCAL_ROUTING',raising=False)
    assert understand_study_request('ANB nedir?',[]).attempted
    provider.generate.assert_called_once()


def test_planner_receives_source_outline_as_data_before_active_request():
    outline={'sections':['Deri Noktaları > Tek Noktalar'],'complete':True}
    call=Mock(return_value=raw())
    interpret_request('O noktaları anlat',[],call=call,source_outline=outline)
    payload=json.loads(call.call_args.args[0])
    assert payload['source_outline']==outline
    assert list(payload)[-1]=='request'


def test_safe_rejection_reason_does_not_log_source_or_model_output(caplog):
    payload = raw(count=201, retrieval_queries=['SECRET-PATIENT-TEXT'])
    result = interpret_request('PRIVATE-QUESTION', [], call=Mock(return_value=payload))
    assert result.outcome == 'failed'
    assert 'reason=invalid requested count' in caplog.text
    assert 'SECRET-PATIENT-TEXT' not in caplog.text
    assert 'PRIVATE-QUESTION' not in caplog.text


@pytest.mark.parametrize('overrides', [
    {'scope':'course','operation':'generate_questions','count':20,
     'resolved_query':'Tüm ders notlarından 20 soru hazırla'},
    {'operation':'clarify','clarification':'Hangi konuyu kastediyorsun?'},
])
def test_valid_unused_search_field_cannot_block_course_or_clarification(overrides):
    call = Mock(return_value=raw(**overrides,retrieval_queries=['unused subject']))
    result = interpret_request('Current request', [], call=call)
    assert result.outcome == 'interpreted'
    assert result.plan.retrieval_queries == ()
    for key,value in overrides.items():
        assert getattr(result.plan,key) == value
    call.assert_called_once()


def test_unused_search_normalization_does_not_accept_invalid_data_or_invent_topic():
    with pytest.raises(ValueError):
        parse_request(raw(scope='course',retrieval_queries=[{'owner_user_id':99}]))
    with pytest.raises(ValueError):
        parse_request(raw(scope='topic',retrieval_queries=[]))


def test_incomplete_json_logs_only_constant_reason(caplog):
    result = interpret_request('PRIVATE-QUESTION', [], call=Mock(return_value='{"SECRET-PATIENT-TEXT":'))
    assert result.outcome == 'failed'
    assert 'reason=invalid_json' in caplog.text
    assert 'SECRET-PATIENT-TEXT' not in caplog.text


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


@pytest.mark.parametrize('searches', [[], [''], ['---'], ['x'*161], ['A']*17, [123]])
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


@pytest.mark.parametrize('outcome', ['unavailable', 'failed', 'input_budget'])
def test_enabled_interpreter_failure_never_uses_legacy_retrieval(monkeypatch, outcome):
    from app.academic_request_understanding import UnderstandingResult, retrieve_understood_course_context
    import app.study_retrieval_v2 as retrieval
    lookup = Mock(side_effect=AssertionError('legacy retrieval used'))
    monkeypatch.setattr(retrieval, 'retrieve_course_context_v2', lookup)
    result = retrieve_understood_course_context(Mock(), understanding=UnderstandingResult(outcome=outcome),
        owner_user_id=17, course_id=23, query='İkisinin farkı?', recent_history=[])
    assert result.clarification and result.semantic_planner_attempted
    assert not result.evidence_sufficient
    lookup.assert_not_called()


def test_gemini_resolved_query_is_not_reinterpreted_by_followup_rules(monkeypatch):
    import app.study_retrieval_v2 as retrieval
    session = Mock(); session.get_bind.return_value.dialect.name = 'postgresql'
    monkeypatch.setattr(retrieval, 'resolve_followup_query', Mock(side_effect=AssertionError('reference reinterpreted')))
    monkeypatch.setattr(retrieval, '_fts_rows', Mock(return_value=[]))
    plan = parse_request(raw())
    result = retrieval.retrieve_course_context_v2(session, owner_user_id=17, course_id=23,
        query='Onları anlat', request_plan=plan)
    assert result.resolved_query == plan.resolved_query


def test_final_prompt_keeps_interpreted_request_without_legacy_output_rules(monkeypatch):
    from app.study_ai_v2 import _prompt
    from app.study_retrieval_v2 import RetrievalResult
    for name in ('app.academic_study_contract.study_output_rules',
                 'app.academic_dialogue.dialogue_rules'):
        monkeypatch.setattr(name, Mock(side_effect=AssertionError('legacy output rule used')))
    request = 'Hipofiz ve tiroidi karşılaştır; önce farklar, sonra 5 zor soru, cevapları en sona koy'
    result = RetrievalResult(resolved_query=request, note_context=['Kaynak kanıtı'],
        semantic_planner_attempted=True, evidence_sufficient=True)
    prompt = _prompt('Ortodonti', 'İkisini karşılaştır', result, [])
    assert request in prompt and 'Kaynak kanıtı' in prompt and 'İkisini karşılaştır' in prompt


def test_long_teaching_history_under_budget_is_retained_intact():
    history=[{'role':'ASSISTANT','content':'a'*50000}]
    call=Mock(return_value=raw())
    result=interpret_request('Bunları kolay ezberlemem için kodla',history,call=call)
    assert result.attempted and result.plan is not None
    assert json.loads(call.call_args.args[0])['recent_dialogue']==history


def test_multiple_comparison_sources_are_not_rejected_at_four_queries():
    searches=['ANB','SNA','SNB','Wits','FMA','Y ekseni']
    plan=parse_request(raw(operation='compare',retrieval_queries=searches))
    assert plan.retrieval_queries==tuple(searches)


def test_planner_can_select_owned_section_without_guessing_member_names():
    heading='deri noktaları > tek noktalar'
    call=Mock(return_value=raw(retrieval_queries=[],source_sections=[heading]))
    result=interpret_request('Hepsini anlat',[],call=call,
                             source_outline={'sections':[heading],'complete':True})
    assert result.plan.source_sections==(heading,)
    assert result.plan.retrieval_queries==()
    call.assert_called_once()


def test_planner_cannot_select_section_outside_supplied_owned_outline():
    call=Mock(return_value=raw(retrieval_queries=[],source_sections=['foreign heading']))
    result=interpret_request('Hepsini anlat',[],call=call,
                             source_outline={'sections':['owned heading'],'complete':True})
    assert result.plan is None and result.outcome=='failed'
    call.assert_called_once()


@pytest.mark.parametrize('configured,expected', [(None,45),('bad',45),('1',10),('999',75),('30',30)])
def test_planner_wait_budget_is_bounded_without_adding_retries(monkeypatch,configured,expected):
    from app.academic_request_understanding import understand_study_request
    import app.study_provider as providers
    monkeypatch.delenv('STUDY_ACADEMIC_LOCAL_ROUTING',raising=False)
    if configured is None:
        monkeypatch.delenv('STUDY_ACADEMIC_PLANNER_TIMEOUT_SECONDS',raising=False)
    else:
        monkeypatch.setenv('STUDY_ACADEMIC_PLANNER_TIMEOUT_SECONDS',configured)
    provider=Mock(api_key='test-only')
    provider.generate.return_value=raw()
    monkeypatch.setattr(providers,'GeminiStudyProvider',lambda:provider)
    monkeypatch.setattr(providers,'target_available',lambda target:True)
    result=understand_study_request('Bir konuyu anlat',[])
    assert result.plan is not None
    assert provider.timeout==expected and provider.max_attempts==1
    provider.generate.assert_called_once()
