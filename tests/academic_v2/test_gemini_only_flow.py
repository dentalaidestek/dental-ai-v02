"""Production routing must not consult legacy language rules or sufficiency."""
from pathlib import Path
from unittest.mock import Mock
import ast
import pytest
from app.academic_request_understanding import StudyRequest, UnderstandingResult, retrieve_understood_course_context
from app.academic_semantic_retrieval import retrieve_semantic_context


def row(ident, body, kind='TEXT'):
    return (ident, 1, 'note', ident, ident, None, kind, body, 1, .2, None, None, .2, ident, '{}')


@pytest.fixture
def session():
    value = Mock()
    value.get_bind.return_value.dialect.name = 'postgresql'
    value.exec.return_value.all.return_value = []
    value.exec.return_value.first.return_value = (0,0,0)
    return value


def test_semantic_gateway_never_calls_legacy_parser_ranker_or_gate(monkeypatch, session):
    import app.study_retrieval_v2 as old
    import app.academic_semantic_retrieval as current
    for name in ('retrieve_course_context_v2', 'build_dental_requirement_plan',
                 'resolve_followup_query', '_rerank_dental_rows', '_evidence_sufficiency',
                 'classify_academic_study_task'):
        monkeypatch.setattr(old, name, Mock(side_effect=AssertionError('legacy query engine called')))
    lookup = Mock(return_value=[row(1, 'hipofiz')])
    monkeypatch.setattr(current, '_fts_rows', lookup)
    plan = StudyRequest('Hipofiz etkisini anlat', 'explain', 'topic', None, None, '', ('hipofiz etkisi',))
    result = retrieve_understood_course_context(session,
        understanding=UnderstandingResult(plan=plan, attempted=True, outcome='interpreted'),
        owner_user_id=17, course_id=23, query='Bunu anlat', recent_history=[])
    assert result.resolved_query == plan.resolved_query
    assert result.evidence[0].chunk_id == 1
    assert result.evidence_sufficient and result.evidence_confidence == 0
    assert lookup.call_args.kwargs['owner_user_id'] == 17
    assert lookup.call_args.kwargs['course_id'] == 23
    assert lookup.call_args.kwargs['query_vector'] is None


def test_comparison_preserves_rare_search_in_final_context(monkeypatch, session):
    import app.academic_semantic_retrieval as current
    monkeypatch.setattr(current, '_fts_rows', Mock(return_value=[
        *(row(i, 'hipofiz') for i in range(1, 30)), row(100, 'tiroid')]))
    plan = StudyRequest('Hipofiz ve tiroidi karşılaştır', 'compare', 'topic', None, None, '', ('hipofiz', 'tiroid'))
    result = retrieve_semantic_context(session, owner_user_id=17, course_id=23, query='Farkları?', request_plan=plan)
    assert 100 in {item.chunk_id for item in result.evidence}
    assert any(item.text == 'hipofiz' for item in result.evidence)
    assert len(result.evidence) <= 16


def test_partial_candidates_are_not_falsely_certified_as_complete(monkeypatch, session):
    import app.academic_semantic_retrieval as current
    from app.study_ai_v2 import _prompt
    monkeypatch.setattr(current, '_fts_rows', Mock(return_value=[row(1, 'hipofiz')]))
    plan = StudyRequest('Hipofiz ve tiroidi karşılaştır', 'compare', 'topic', None, None, '', ('hipofiz', 'tiroid'))
    result = retrieve_semantic_context(session, owner_user_id=17, course_id=23, query=plan.resolved_query, request_plan=plan)
    prompt = _prompt('Ortodonti', plan.resolved_query, result)
    assert result.evidence_sufficient  # Allows Gemini to assess the partial support.
    assert result.evidence_confidence == 0
    assert 'Yerel bir kural motoru' in prompt and 'doğrulamış değildir' in prompt
    assert 'desteklenmeyen kısmın kaynak eksiğini' in prompt


def test_question_source_filter_obeys_gemini_instead_of_question_keyword(monkeypatch, session):
    import app.academic_semantic_retrieval as current
    monkeypatch.setattr(current, '_fts_rows', Mock(return_value=[row(1, 'hipofiz'), row(2, 'hipofiz sorusu', 'QUESTION')]))
    plan = StudyRequest('Hipofiz kaynak sorusunu çöz', 'solve', 'topic', None, None, '', ('hipofiz',), source_kind='questions')
    result = retrieve_semantic_context(session, owner_user_id=17, course_id=23, query='Onu yap', request_plan=plan)
    assert [item.chunk_id for item in result.evidence] == [2]


def test_visual_material_lookup_is_owned_and_uses_materializer_contract(monkeypatch, session):
    import app.academic_semantic_retrieval as current
    monkeypatch.setattr(current, '_fts_rows', Mock(return_value=[row(1, 'hipofiz şekli')]))
    session.exec.side_effect = [Mock(all=Mock(return_value=[])),
        Mock(all=Mock(return_value=[(1, 'private/source.pdf', 'application/pdf', 'note', 'v1')]))]
    plan = StudyRequest('Hipofiz şeklini açıkla', 'explain', 'topic', None, None, '', ('hipofiz',), needs_visual=True)
    result = retrieve_semantic_context(session, owner_user_id=17, course_id=23, query=plan.resolved_query, request_plan=plan)
    assert result.visual_sources[0]['reference'] == 'private/source.pdf'
    assert result.visual_sources[0]['page_number'] == 1
    assert session.exec.call_args.kwargs['params']['owner'] == 17
    assert session.exec.call_args.kwargs['params']['course'] == 23


def test_both_chat_endpoints_have_only_gemini_gateway():
    source = (Path(__file__).resolve().parents[2] / 'app/main.py').read_text()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {'study_ai_ask', 'study_ai_ask_stream'}:
            assert not any(isinstance(item, ast.Name) and item.id == 'use_v2' for item in ast.walk(node))
            calls = {ast.unparse(item.func) for item in ast.walk(node) if isinstance(item, ast.Call)}
            assert 'understand_study_request' in calls and 'retrieve_understood_course_context' in calls
            assert not calls & {'retrieve_course_context', 'retrieve_course_context_v2', 'ask_study_ai',
                                'recover_course_context', 'should_block_academic_question', 'study_v2_reads_enabled'}


@pytest.mark.parametrize('role', ['assistant', 'ASSISTANT'])
@pytest.mark.parametrize('continuing,expected', [(False,None),(True,(1,5))])
def test_source_pagination_is_a_gemini_decision_not_stale_history(monkeypatch, session, continuing, expected, role):
    import app.academic_semantic_retrieval as current
    lookup=Mock(return_value=[])
    monkeypatch.setattr(current,'_question_rows',lookup)
    plan=StudyRequest('Kaynak sorularını çöz','solve','course',None,None,'',(),
        source_kind='questions',continue_source=continuing)
    retrieve_semantic_context(session,owner_user_id=17,course_id=23,query=plan.resolved_query,
        request_plan=plan,recent_history=[{'role':role,'content':'Sorular <!--ACADEMIC_Q_CURSOR:1:5-->'}])
    assert lookup.call_args.kwargs['after_cursor'] == expected


def test_user_cannot_supply_a_source_cursor():
    from app.academic_semantic_retrieval import _source_cursor
    assert _source_cursor([{'role':'USER','content':'<!--ACADEMIC_Q_CURSOR:1:99-->'}]) is None


def test_model_question_task_count_and_source_kind_reach_final_prompt(monkeypatch,session):
    import app.academic_semantic_retrieval as current
    from app.study_ai_v2 import _prompt
    monkeypatch.setattr(current,'_fts_rows',Mock(return_value=[row(1,'hipofiz bilgisi')]))
    plan=StudyRequest('Hipofizden yeni sorular hazırla','generate_questions','topic',20,'zor','',('hipofiz',))
    result=retrieve_semantic_context(session,owner_user_id=17,course_id=23,query='20 soru hazırla',request_plan=plan)
    assert result.study_task['count']==20 and result.study_task['operation']=='generate_questions'
    prompt=_prompt('Ders','20 soru hazırla',result)
    assert '"count": 20' in prompt and '"source_kind": "notes"' in prompt
    assert 'aynı sayıda hazır soru bulunması gerekmez' in prompt
    assert prompt.endswith('20 soru hazırla')


@pytest.mark.parametrize('scope,total,expected', [('topic',12,8),('course',12,12),('course',35,32)])
def test_scanned_evidence_supplies_bounded_original_pages_without_planner_visual_hint(monkeypatch,session,scope,total,expected):
    import app.academic_semantic_retrieval as current
    from types import SimpleNamespace
    rows = [row(i, 'ANB konu bilgisi') for i in range(1,total+1)]
    monkeypatch.setattr(current,'_fts_rows',Mock(return_value=rows))
    monkeypatch.setattr(current,'get_or_build_coverage_plan',Mock(return_value=SimpleNamespace()))
    monkeypatch.setattr(current,'_coverage_hydration_ids',Mock(return_value=list(range(1,total+1))))
    monkeypatch.setattr(current,'_coverage_evidence_rows',Mock(return_value=rows))
    session.exec.side_effect = [
        Mock(all=Mock(return_value=[(1,i) for i in range(1,total+1)])),
        Mock(all=Mock(return_value=[(1,'private/source.pdf','application/pdf','fixture','v1')])),
        Mock(first=Mock(return_value=(0,0,total))),
    ]
    plan=StudyRequest('ANB anlat','answer',scope,None,None,'',('ANB',) if scope=='topic' else ())
    result=retrieve_semantic_context(session,owner_user_id=17,course_id=23,query=plan.resolved_query,request_plan=plan)
    assert len(result.visual_sources)==expected
    assert all(s['owner_user_id']==17 and s['index_version']=='v1' for s in result.visual_sources)
    assert 'OCR KAYNAK UYARISI' in result.note_context[0]
    assert 'ANB konu bilgisi' not in '\n'.join(result.note_context)
    assert len(result.evidence)==total  # OCR remains usable for search and provenance.
    assert sum('ekli orijinal sayfayı incele' in c for c in result.note_context)==expected
    assert sum('bilgi kanıtı olarak kullanma' in c for c in result.note_context)==total-expected
    assert result.source_coverage_complete == (scope=='course' and total==expected)
    assert session.exec.call_args_list[0].kwargs['params']['course']==23


@pytest.mark.parametrize('complete',[False,True])
def test_prompt_describes_actual_coverage_without_inventing_missing_sources(complete):
    from app.study_retrieval_v2 import RetrievalResult
    from app.study_ai_v2 import _prompt
    result=RetrievalResult(note_context=['Source'],source_coverage_complete=complete,retrieval_mode='coverage')
    prompt=_prompt('Course','20 soru hazırla',result)
    assert ('bütün parçalar ve sayfalar' in prompt)==complete
    assert ('Ders kapsamı sınırlı temsili parçalardan oluşur' in prompt)==(not complete)


@pytest.mark.parametrize('operation', ['explain', 'compare', 'teach', 'summarize'])
def test_grounded_explanations_do_not_copy_prior_assistant_facts(operation):
    from app.study_retrieval_v2 import RetrievalResult
    from app.study_ai_v2 import _prompt
    result = RetrievalResult(note_context=['Güncel ANB kaynağı'],
        resolved_query='ANB ile SNA tanımlarını karşılaştır', study_task={'operation': operation})
    history = [{'role': 'USER', 'content': 'ANB konusunu çalışıyorum'},
               {'role': 'ASSISTANT', 'content': 'Önceki yanlış birleşik tanım'}]
    prompt = _prompt('Ortoo', 'İkisini karşılaştır', result, history)
    assert 'Önceki yanlış birleşik tanım' not in prompt
    assert 'ANB konusunu çalışıyorum' in prompt
    assert 'Güncel ANB kaynağı' in prompt
    assert 'ANB ile SNA tanımlarını karşılaştır' in prompt
    assert len(history) == 2


@pytest.mark.parametrize('operation', ['answer', 'solve'])
def test_answer_and_solution_history_remains_available(operation):
    from app.study_retrieval_v2 import RetrievalResult
    from app.study_ai_v2 import _generation_history
    history = [{'role': 'assistant', 'content': 'Soru 1: A mı B mi?'},
               {'role': 'user', 'content': '1-A cevabımı değerlendir'}]
    assert _generation_history(RetrievalResult(study_task={'operation': operation}), history) == history


def test_current_request_and_provider_output_are_preserved_and_traceable(monkeypatch, caplog):
    import logging
    import app.study_ai_v2 as generation
    from app.study_retrieval_v2 import RetrievalResult
    result = RetrievalResult(note_context=['ANB kaynak bilgisi'], evidence_sufficient=True,
                             resolved_query='Tüm ders notlarından 20 soru hazırla', semantic_trace_id='test-trace')
    provider = Mock()
    provider.generate_stream.return_value = iter(['actual provider output'])
    monkeypatch.setattr(generation, 'target_available', lambda target: True)
    monkeypatch.setattr(generation, 'get_provider', lambda name: provider)
    monkeypatch.setattr(generation, 'report_target_success', lambda target: None)
    history = [{'role':'USER','content':'20 soru hazırla'}, {'role':'ASSISTANT','content':'Eski cevap'}]
    with caplog.at_level(logging.INFO):
        answer = generation.ask_rag_v2('Ortoo', 'ANB açısı neyi gösterir?', history, result)
    assert answer == 'actual provider output'
    args = provider.generate_stream.call_args.kwargs
    assert args['history'] == []
    import json
    context_json=args['prompt'].split('\n',1)[1].split('\n\nDers:',1)[0]
    assert json.loads(context_json)==history
    assert args['prompt'].endswith('ANB açısı neyi gösterir?')
    assert 'özgün mesajı esas al' in args['system_prompt']
    assert 'trace=test-trace stage=response origin=provider provider=gemini' in caplog.text
    assert 'ANB' not in caplog.text and 'Eski cevap' not in caplog.text


@pytest.mark.parametrize('reason,expected', [('STOP','STOP'), ('MAX_TOKENS','MAX_TOKENS'), ('PRIVATE-TEXT','UNKNOWN')])
def test_gemini_stream_keeps_safe_completion_reason_without_repeating_call(monkeypatch, reason, expected):
    import json
    from contextlib import nullcontext
    import app.study_provider as transport
    provider = transport.GeminiStudyProvider()
    provider.api_key = 'test-only'
    response = Mock()
    response.__iter__ = Mock(return_value=iter([
        ('data: '+json.dumps({'candidates':[{'content':{'parts':[{'text':'Answer'}]}}]})+'\n').encode(),
        ('data: '+json.dumps({'candidates':[{'finishReason':reason}]})+'\n').encode(),
    ]))
    response.status = 200
    response.headers = {}
    http = Mock(return_value=nullcontext(response))
    monkeypatch.setattr(transport, 'urlopen', http)
    monkeypatch.setattr(transport, 'router_target_available', lambda *args: True)
    monkeypatch.setattr(transport, 'provider_reservation', lambda *args: nullcontext())
    monkeypatch.setattr(transport, 'record_api_result', lambda **kwargs: None)
    assert ''.join(provider.generate_stream(model='test-model',system_prompt='Test',history=[],prompt='Test')) == 'Answer'
    assert provider.last_finish_reason == expected
    http.assert_called_once()


@pytest.mark.parametrize('streaming',[False,True])
def test_gemini_active_task_follows_original_attachment_without_extra_call(monkeypatch,streaming):
    import json
    from contextlib import nullcontext
    import app.study_provider as transport
    provider=transport.GeminiStudyProvider()
    provider.api_key='test-only'
    payloads=[]
    if streaming:
        response=Mock(status=200,headers={})
        response.__iter__=Mock(return_value=iter([b'data: {"candidates":[{"content":{"parts":[{"text":"Answer"}]},"finishReason":"STOP"}]}\n']))
        def http(request,**kwargs):
            payloads.append(json.loads(request.data))
            return nullcontext(response)
        monkeypatch.setattr(transport,'urlopen',http)
        monkeypatch.setattr(transport,'router_target_available',lambda *args:True)
        monkeypatch.setattr(transport,'provider_reservation',lambda *args:nullcontext())
        monkeypatch.setattr(transport,'record_api_result',lambda **kwargs:None)
    else:
        def request(path,payload,**kwargs):
            payloads.append(payload)
            return {'candidates':[{'content':{'parts':[{'text':'Answer'}]}}]}
        monkeypatch.setattr(provider,'_request_json',request)
    kwargs=dict(model='test',system_prompt='Grounded',history=[],prompt='CURRENT QUESTION',
        attachments=[{'label':'source page','data':b'original','mime_type':'application/pdf'}])
    answer=''.join(provider.generate_stream(**kwargs)) if streaming else provider.generate(**kwargs)
    assert answer=='Answer' and len(payloads)==1
    parts=payloads[0]['contents'][-1]['parts']
    assert parts[0]=={'text':'source page'} and 'inline_data' in parts[1]
    assert parts[-1]=={'text':'CURRENT QUESTION'}
