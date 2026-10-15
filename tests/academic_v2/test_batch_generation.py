from unittest.mock import Mock
import pytest
from app.study_ai import StudyAIError
from app.study_retrieval_v2 import RetrievalResult
from app.study_ai_v2 import ask_rag_v2


def parent(operation, count=None):
    children = [RetrievalResult(note_context=[text], evidence_sufficient=True,
        study_task={'operation':operation,'scope':'course','count':count})
        for text in ('First source definition','Second source definition')]
    return RetrievalResult(source_batches=children, evidence_sufficient=True,
        study_task={'operation':operation,'scope':'course','count':count},
        resolved_query='Tüm ders notlarından 20 soru hazırla')


def provider(monkeypatch, outputs):
    import app.study_ai_v2 as module
    monkeypatch.setenv("STUDY_SOURCE_BATCH_WORKERS", "1")
    value = Mock()
    value.generate_stream.side_effect = [iter([output]) for output in outputs]
    monkeypatch.setattr(module,'target_available',lambda target: True)
    monkeypatch.setattr(module,'get_provider',lambda name: value)
    monkeypatch.setattr(module,'report_target_success',lambda target: None)
    return value


@pytest.mark.parametrize('operation',['summarize','teach'])
def test_summary_and_teaching_combine_all_sections_before_final_format(monkeypatch,operation):
    value=provider(monkeypatch,['First facts','Second facts','Complete two-group table'])
    result=ask_rag_v2('Course','Her konuyu iki grupta tabloya koy',[],parent(operation))
    assert result=='Complete two-group table'
    assert value.generate_stream.call_count==3
    assert 'First source definition' in value.generate_stream.call_args_list[0].kwargs['prompt']
    assert 'Second source definition' in value.generate_stream.call_args_list[1].kwargs['prompt']
    final=value.generate_stream.call_args_list[2].kwargs['prompt']
    assert 'First facts' in final and 'Second facts' in final
    assert 'Her konuyu iki grupta tabloya koy' in final


def test_question_count_applies_once_after_all_sections_are_read(monkeypatch):
    questions='\n\n'.join(f'### Soru {n}\nKavram {n} hangi tanıma karşılık gelir?\nA) Tanım' for n in range(1,21))
    value=provider(monkeypatch,['First grounded extraction','Second grounded extraction',questions])
    result=ask_rag_v2('Course','20 soru hazırla',[],parent('generate_questions',20))
    assert result==questions
    assert value.generate_stream.call_count==3
    first=value.generate_stream.call_args_list[0].kwargs['prompt']
    final=value.generate_stream.call_args_list[-1].kwargs['prompt']
    assert 'Henüz soru veya cevap anahtarı üretme' in first
    assert 'First grounded extraction' in final and 'Second grounded extraction' in final
    assert '"count": 20' in final and '"operation": "generate_questions"' in final


def test_missing_originals_stop_before_model_call(monkeypatch):
    value=provider(monkeypatch,['must not be generated'])
    result=parent('summarize')
    result.source_batches[0].visual_sources=[{'material_id':1,'page_number':2}]
    result.batch_materializer=lambda child: None
    with pytest.raises(StudyAIError):
        ask_rag_v2('Course','Her konuyu özetle',[],result)
    value.generate_stream.assert_not_called()


@pytest.mark.parametrize('outputs',[
    ['Supported answer','<!--ACADEMIC_BATCH_NO_SUPPORT-->'],
    ['<!--ACADEMIC_BATCH_NO_SUPPORT-->','Supported answer'],
])
def test_unsupported_batch_does_not_append_denial_to_supported_answer(monkeypatch,outputs):
    value=provider(monkeypatch,outputs + ['Supported answer'])
    assert ask_rag_v2('Course','Karşılaştır',[],parent('compare'))=='Supported answer'
    assert value.generate_stream.call_count==3
    assert 'BÖLÜM İŞLEME KURALI' in value.generate_stream.call_args_list[0].kwargs['prompt']
    assert 'ACADEMIC_BATCH_NO_SUPPORT' not in value.generate_stream.call_args.kwargs['prompt']


def test_all_unsupported_batches_produce_one_honest_reply(monkeypatch):
    value=provider(monkeypatch,['<!--ACADEMIC_BATCH_NO_SUPPORT-->']*2)
    result=ask_rag_v2('Course','Soru hazırla',[],parent('generate_questions',20))
    assert result.count('bilgi bulamadım')==1
    assert 'ACADEMIC_BATCH' not in result
    assert value.generate_stream.call_count==2


def test_question_transcription_is_not_forced_to_solve_or_create_questions(monkeypatch):
    from app.study_ai_v2 import _prompt
    result=RetrievalResult(note_context=['1. Kaynak sorusu A) Yanlış şık'],evidence_sufficient=True,
        study_task={'operation':'answer','scope':'course','source_kind':'questions'})
    prompt=_prompt('Course','Mevcut soruları aynen düzenle, çözme',result)
    assert 'MEVCUT KAYNAK SORULARI' in prompt
    assert 'Yanlış seçenekleri de metnin parçası olarak aktar' in prompt
    assert 'YENİ SORU ÜRETİMİ' not in prompt


def test_token_limited_answer_is_never_reported_as_complete(monkeypatch):
    value=provider(monkeypatch,['Soru 10: yarım'])
    value.last_finish_reason='MAX_TOKENS'
    result=RetrievalResult(note_context=['Source'],evidence_sufficient=True)
    with pytest.raises(StudyAIError,match='uzunluk sınırına'):
        ask_rag_v2('Course','Hepsini anlat',[],result)


@pytest.mark.parametrize('outcome', ['failed', 'unavailable', 'input_budget'])
def test_failed_planner_is_an_error_before_output_not_a_completed_reply(monkeypatch, outcome):
    from app.academic_request_understanding import UnderstandingResult, retrieve_understood_course_context
    from app.study_ai_v2 import stream_rag_v2
    value = provider(monkeypatch, ['must not be called'])
    retrieval = retrieve_understood_course_context(Mock(),
        understanding=UnderstandingResult(outcome=outcome),
        owner_user_id=17, course_id=23, query='Mevcut soruları aktar', recent_history=[])
    stream = stream_rag_v2('Course', 'Mevcut soruları aktar', [], retrieval)
    with pytest.raises(StudyAIError) as error:
        next(stream)
    assert str(error.value) == retrieval.clarification
    with pytest.raises(StudyAIError):
        ask_rag_v2('Course', 'Mevcut soruları aktar', [], retrieval)
    value.generate_stream.assert_not_called()


def test_valid_clarification_remains_a_completed_reply(monkeypatch):
    value = provider(monkeypatch, ['must not be called'])
    retrieval = RetrievalResult(clarification='Hangi konuyu çalışalım?',
                               retrieval_mode='clarify')
    assert ask_rag_v2('Course', 'Onu anlat', [], retrieval) == retrieval.clarification
    value.generate_stream.assert_not_called()


def test_comparison_synthesis_sees_both_files_and_preserves_original_request(monkeypatch):
    value=provider(monkeypatch,['Alpha evidence (file A page 1)',
                                'Beta evidence (file B page 9)',
                                'One supported comparison'])
    result=parent('compare')
    result.resolved_query='Compare alpha and beta in a table; exclude gamma.'
    result.semantic_trace_id='comparison-trace'
    assert ask_rag_v2('Course',result.resolved_query,[],result)=='One supported comparison'
    assert value.generate_stream.call_count==3
    final=value.generate_stream.call_args.kwargs['prompt']
    assert 'Alpha evidence (file A page 1)' in final and 'Beta evidence (file B page 9)' in final
    assert result.resolved_query in final and '"operation": "compare"' in final
    assert all('İstenen bilgi bu bölümde yoksa' in item.kwargs['prompt']
               for item in value.generate_stream.call_args_list[:2])


def test_failed_comparison_extraction_does_not_emit_a_misleading_partial_result(monkeypatch):
    from app.study_ai_v2 import stream_rag_v2
    value=provider(monkeypatch,['Alpha evidence'])
    value.generate_stream.side_effect=[iter(['Alpha evidence']), StudyAIError('unavailable')]
    stream=stream_rag_v2('Course','Compare alpha with beta',[],parent('compare'))
    with pytest.raises(StudyAIError,match='unavailable'):
        next(stream)
    assert value.generate_stream.call_count==2


def test_parallel_question_sections_overlap_but_synthesize_in_source_order(monkeypatch):
    import threading
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','2')
    monkeypatch.setenv('DENTAL_PROVIDER_MAX_INFLIGHT','4')
    result=parent('generate_questions',20)
    result.source_batches += [RetrievalResult(note_context=['Third source'],evidence_sufficient=True,
        study_task={'operation':'generate_questions'})]
    rendezvous=threading.Barrier(2)
    lock=threading.Lock(); active=0; peak=0; calls=[]
    def generate(course,question,history,child):
        nonlocal active,peak
        if not child.study_task.get('batch_partial'):
            assert child.study_task['count']==20
            assert len(child.note_context)==3
            assert 'First source' in child.note_context[0]
            assert 'Second source' in child.note_context[1]
            assert 'Third source' in child.note_context[2]
            yield '20 balanced questions'
            return
        name=child.note_context[0]
        with lock:
            active+=1; peak=max(peak,active); calls.append(name)
        try:
            if name!='Third source':
                rendezvous.wait(timeout=3)
            yield name
        finally:
            with lock:active-=1
    monkeypatch.setattr(module,'stream_rag_v2',generate)
    assert ''.join(module._stream_source_batches('Course','20 questions',[],result))=='20 balanced questions'
    assert peak==2 and sorted(calls)==sorted(['First source definition','Second source definition','Third source'])
    assert all(not child.attachments for child in result.source_batches)


def test_parallel_failure_never_synthesizes_or_schedules_remaining_sections(monkeypatch):
    import threading
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','2')
    result=parent('generate_questions',20)
    result.source_batches += [RetrievalResult(note_context=['Never schedule'],evidence_sufficient=True)]
    ready=threading.Event(); release=threading.Event(); finished=threading.Event(); calls=[]
    def generate(course,question,history,child):
        name=child.note_context[0];calls.append(name)
        if name.startswith('First'):
            assert ready.wait(3)
            raise StudyAIError('Synthetic failed section')
        if name.startswith('Second'):
            ready.set()
            try:
                assert release.wait(3)
                yield name
            finally:finished.set()
        else:
            raise AssertionError('Failed extraction scheduled another section or synthesis')
    monkeypatch.setattr(module,'stream_rag_v2',generate)
    try:
        with pytest.raises(StudyAIError,match='failed section'):
            list(module._stream_source_batches('Course','20 questions',[],result))
    finally:
        release.set();assert finished.wait(3)
    assert len(calls)==2


def test_cached_gemini_finish_reason_is_isolated_between_threads():
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from app.study_provider import GeminiStudyProvider
    provider=GeminiStudyProvider(); barrier=threading.Barrier(2)
    def read_own_finish(reason):
        provider.last_finish_reason=reason
        barrier.wait(timeout=3)
        return provider.last_finish_reason
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(read_own_finish,'MAX_TOKENS');b=pool.submit(read_own_finish,'STOP')
        assert a.result()=='MAX_TOKENS' and b.result()=='STOP'
    assert provider.last_finish_reason=='UNKNOWN'


def test_question_parallelism_respects_single_provider_slot(monkeypatch):
    from app.study_ai_v2 import _batch_workers
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','20')
    monkeypatch.setenv('DENTAL_PROVIDER_MAX_INFLIGHT','1')
    assert _batch_workers()==1
    monkeypatch.setenv('DENTAL_PROVIDER_MAX_INFLIGHT','4')
    assert _batch_workers()==2


def test_source_pool_bounds_parallel_work_across_users(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','2')
    monkeypatch.setenv('DENTAL_PROVIDER_MAX_INFLIGHT','4')
    lock=threading.Lock(); two_active=threading.Event(); release=threading.Event()
    active=0;peak=0;calls=0
    def extract(*args):
        nonlocal active,peak,calls
        with lock:
            active+=1;calls+=1;peak=max(peak,active)
            if active==2:two_active.set()
        try:
            assert release.wait(3)
            return 'Grounded section'
        finally:
            with lock:active-=1
    monkeypatch.setattr(module,'_extract_source_batch',extract)
    with ThreadPoolExecutor(max_workers=2) as requests:
        a=requests.submit(lambda:list(module._source_batch_outputs('A','20',[],parent('generate_questions',20),True)))
        b=requests.submit(lambda:list(module._source_batch_outputs('B','20',[],parent('generate_questions',20),True)))
        try:
            assert two_active.wait(3)
            with lock:assert peak==2
        finally:release.set()
        assert len(a.result())==len(b.result())==2
    assert calls==4 and peak==2


def test_slow_first_section_does_not_stop_later_section_work(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','2')
    result=parent('generate_questions',20)
    result.source_batches.append(RetrievalResult(note_context=['Third source'],evidence_sufficient=True))
    third_started=threading.Event()
    def extract(course,question,history,parent,child,*args):
        name=child.note_context[0]
        if name.startswith('First'):
            assert third_started.wait(3), 'A finished second worker was left idle behind the first section'
        if name=='Third source':third_started.set()
        return name
    monkeypatch.setattr(module,'_extract_source_batch',extract)
    assert list(module._source_batch_outputs('Course','20',[],result,True))==[
        'First source definition','Second source definition','Third source']


def transport_failure(code=None):
    from app.study_provider import StudyProviderError
    provider_error=StudyProviderError('Synthetic transport failure',code=code,retryable=True)
    provider_error.__cause__=TimeoutError('Synthetic timeout')
    error=StudyAIError('Synthetic source error',retryable=True)
    error.__cause__=provider_error
    return error


def test_question_request_recovers_only_failed_section_once(monkeypatch):
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','1')
    monkeypatch.setattr(module,'_wait_source_recovery',lambda stopped:True)
    result=parent('generate_questions',20)
    counts={}
    def generate(course,question,history,child):
        if not child.study_task.get('batch_partial'):
            assert 'Recovered first source' in child.note_context[0]
            assert 'Second source definition' in child.note_context[1]
            yield '20 complete questions'
            return
        name=child.note_context[0];counts[name]=counts.get(name,0)+1
        if name.startswith('First') and counts[name]==1:
            raise transport_failure()
        yield 'Recovered first source' if name.startswith('First') else name
    monkeypatch.setattr(module,'stream_rag_v2',generate)
    assert ''.join(module._stream_source_batches('Course','20 questions',[],result))=='20 complete questions'
    assert counts=={'First source definition':2,'Second source definition':1}


def test_transient_recovery_waits_before_reentering_real_generation_gate(monkeypatch):
    import app.study_ai_v2 as module
    from app.study_provider import StudyProviderError
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','1')
    available=[True]
    calls=[]
    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:
            available[0]=False
            raise StudyProviderError('Synthetic 503',code=503,retryable=True,tracked=True)
        yield 'Recovered source' if len(calls)==2 else 'Second source'
    model=Mock(generate_stream=generate)
    monkeypatch.setattr(module,'get_provider',lambda name:model)
    monkeypatch.setattr(module,'target_available',lambda target:available[0])
    def wait(stopped):
        assert available[0] is False
        available[0]=True
        return True
    waited=Mock(side_effect=wait)
    monkeypatch.setattr(module,'_wait_source_recovery',waited)
    result=parent('answer')
    result.study_task['source_kind']='questions'
    assert ask_rag_v2('Course','Kaynak sorularını aktar',[],result)=='Recovered source\n\nSecond source'
    assert len(calls)==3
    waited.assert_called_once()


@pytest.mark.parametrize('cancelled', [False,True])
def test_recovery_wait_respects_circuit_timeout_and_cancellation(monkeypatch,cancelled):
    from types import SimpleNamespace
    import app.study_ai_v2 as module
    clock=[0.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(module,'target_available',lambda target:False)
    def pause(delay):
        clock[0]+=delay
        return cancelled
    stopped=SimpleNamespace(is_set=lambda:False,wait=pause)
    assert module._wait_source_recovery(stopped,timeout=.6) is False
    assert clock[0] <= .6


def test_recovery_wait_proceeds_only_after_router_becomes_available(monkeypatch):
    from types import SimpleNamespace
    import app.study_ai_v2 as module
    clock=[0.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(module,'target_available',lambda target:clock[0]>=.5)
    def pause(delay):
        clock[0]+=delay
        return False
    assert module._wait_source_recovery(SimpleNamespace(is_set=lambda:False,wait=pause),timeout=1)
    assert clock[0]==.5


@pytest.mark.parametrize('mode',['quota','partial','second_failed_section','retry_failed'])
def test_recovery_is_bounded_and_never_synthesizes_incomplete_sources(monkeypatch,mode):
    import app.study_ai_v2 as module
    monkeypatch.setenv('STUDY_SOURCE_BATCH_WORKERS','1')
    monkeypatch.setattr(module,'_wait_source_recovery',lambda stopped:True)
    counts={}
    def generate(course,question,history,child):
        assert child.study_task.get('batch_partial'), 'Incomplete source extraction reached synthesis'
        name=child.note_context[0];counts[name]=counts.get(name,0)+1
        if mode=='quota':raise transport_failure(429)
        if mode=='partial':
            yield 'Partial source facts'
            raise transport_failure()
        if mode=='retry_failed' or counts[name]==1:
            raise transport_failure()
        yield 'Recovered facts'
    monkeypatch.setattr(module,'stream_rag_v2',generate)
    with pytest.raises(StudyAIError):
        list(module._stream_source_batches('Course','20',[],parent('generate_questions',20)))
    assert sum(counts.values())==({'quota':1,'partial':1,'second_failed_section':3,'retry_failed':2}[mode])


def test_timeout_is_reported_as_timeout_instead_of_generic_failure():
    from app.study_ai import study_provider_error_for_user
    source=transport_failure().__cause__
    assert 'zaman aşımına' in str(study_provider_error_for_user(source))
    source.code=429
    assert 'yoğun' in str(study_provider_error_for_user(source))


def test_multi_section_answer_is_synthesized_once_instead_of_joining_denials(monkeypatch):
    value = provider(monkeypatch, ['No measurement in section A',
                                 'Definition in section B, no measurement',
                                 'Notlarda bu ölçü verilmemiştir.'])
    result = parent('answer')
    assert ask_rag_v2('Course', 'Ölçü kaç mm?', [], result) == 'Notlarda bu ölçü verilmemiştir.'
    assert value.generate_stream.call_count == 3
    final = value.generate_stream.call_args.kwargs['prompt']
    assert 'section A' in final and 'section B' in final


def test_single_section_answer_does_not_add_a_synthesis_call(monkeypatch):
    value = provider(monkeypatch, ['One-row table'])
    result = parent('answer')
    result.source_batches = result.source_batches[:1]
    assert ask_rag_v2('Course', 'Tanımı tabloya çevir', [], result) == 'One-row table'
    value.generate_stream.assert_called_once()


def test_final_synthesis_retains_native_values_even_if_extraction_omits_them(monkeypatch):
    value=provider(monkeypatch,['Partial extraction','Another partial extraction','All ten measurements'])
    result=parent('compare')
    result.source_batches[0].note_context=['[KANIT_NATIVE material_id=1 sayfa=68] Ideal value 87.8']
    assert ask_rag_v2('Course','Bütün ölçümler',[],result)=='All ten measurements'
    final=value.generate_stream.call_args.kwargs['prompt']
    assert 'Ideal value 87.8' in final and 'Partial extraction' in final


def test_pattern_counts_use_validated_records_and_no_final_model_call(monkeypatch):
    import json
    from types import SimpleNamespace
    first=dict(material_id=1,page=4,number='21',topic='Sefalometri',
        text='Sefalometrik ölçümler ile yüz yüksekliği arasında hangi ilişki vardır? A) Birinci ifade B) İkinci ifade')
    second={**first,'page':9}
    value=provider(monkeypatch,[json.dumps({'questions':[first]}),json.dumps({'questions':[second]})])
    result=parent('answer',3)
    result.study_task['source_kind']='question_patterns'
    for child,page in zip(result.source_batches,[4,9]):
        child.study_task['source_kind']='question_patterns'
        child.evidence=[SimpleNamespace(material_id=1,page_start=page,page_end=page,display_name='Notes.pdf')]
    answer=ask_rag_v2('Course','Çıkmış sorulara göre hangi konular sık?',[],result)
    assert '1 benzersiz' in answer and '1 kopya' in answer
    assert 'sayfa 9' not in answer
    assert value.generate_stream.call_count==2
