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
