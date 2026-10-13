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
    value = Mock()
    value.generate_stream.side_effect = [iter([output]) for output in outputs]
    monkeypatch.setattr(module,'target_available',lambda target: True)
    monkeypatch.setattr(module,'get_provider',lambda name: value)
    monkeypatch.setattr(module,'report_target_success',lambda target: None)
    return value


def test_summary_processes_each_section_once_and_combines_without_extra_call(monkeypatch):
    value=provider(monkeypatch,['First summary','Second summary'])
    result=ask_rag_v2('Course','Her konuyu özetle',[],parent('summarize'))
    assert result=='First summary\n\nSecond summary'
    assert value.generate_stream.call_count==2
    assert 'First source definition' in value.generate_stream.call_args_list[0].kwargs['prompt']
    assert 'Second source definition' in value.generate_stream.call_args_list[1].kwargs['prompt']


def test_question_count_applies_once_after_all_sections_are_read(monkeypatch):
    value=provider(monkeypatch,['First grounded extraction','Second grounded extraction','20 questions'])
    result=ask_rag_v2('Course','20 soru hazırla',[],parent('generate_questions',20))
    assert result=='20 questions'
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
    assert all('Diğer taraf bu bölümde yoksa' in item.kwargs['prompt']
               for item in value.generate_stream.call_args_list[:2])


def test_failed_comparison_extraction_does_not_emit_a_misleading_partial_result(monkeypatch):
    from app.study_ai_v2 import stream_rag_v2
    value=provider(monkeypatch,['Alpha evidence'])
    value.generate_stream.side_effect=[iter(['Alpha evidence']), StudyAIError('unavailable')]
    stream=stream_rag_v2('Course','Compare alpha with beta',[],parent('compare'))
    with pytest.raises(StudyAIError,match='unavailable'):
        next(stream)
    assert value.generate_stream.call_count==2
