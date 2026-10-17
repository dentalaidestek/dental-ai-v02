import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from app.academic_quick_actions import PROMPTS,quick_action_plan,is_quick_action
from app.academic_request_understanding import understand_study_request,UnderstandingResult,retrieve_understood_course_context
from app.study_retrieval_v2 import RetrievalResult


@pytest.mark.parametrize('operation',PROMPTS)
def test_exact_ui_command_needs_no_interpretation_provider(monkeypatch,operation):
    never=Mock(side_effect=AssertionError('A fixed command must not call the planner'))
    monkeypatch.setattr('app.study_provider.get_provider',never)
    result=understand_study_request(PROMPTS[operation],[{'role':'user','content':'Önceki konuyu PDF yap'}])
    assert result.outcome=='quick_action' and not result.attempted
    assert result.plan.scope=='course' and result.plan.operation==operation
    assert result.plan.source_kind=='notes' and not result.plan.needs_visual
    assert result.plan.output_format=='text' and result.plan.source_subjects==()
    assert result.plan.count==(20 if operation=='generate_questions' else None)
    never.assert_not_called()


@pytest.mark.parametrize('operation',PROMPTS)
def test_editing_the_preset_never_silently_changes_its_meaning(operation):
    edited=PROMPTS[operation]+' Yalnız Basion için ve PDF olarak.'
    assert not is_quick_action(edited) and quick_action_plan(edited) is None


def test_template_and_server_command_contract_match():
    template=(Path(__file__).resolve().parents[2]/'app/templates/notes_ai.html').read_text()
    for value in PROMPTS.values():assert f'data-prompt="{value}"' in template


def test_complete_text_packs_are_sent_once_without_extracting_or_dropping_sources(monkeypatch):
    import app.study_ai_v2 as module
    provider=Mock();provider.generate_stream.return_value=iter(['Whole course answer'])
    monkeypatch.setattr(module,'get_provider',lambda name:provider)
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    children=[RetrievalResult(note_context=[s],evidence_sufficient=True) for s in ['first source facts','second source facts']]
    result=RetrievalResult(source_batches=children,evidence_sufficient=True,
        study_task={'operation':'teach','scope':'course','quick_action':True})
    assert module.ask_rag_v2('Course',PROMPTS['teach'],[{'role':'assistant','content':'OLD UNRELATED TASK'}],result)=='Whole course answer'
    provider.generate_stream.assert_called_once()
    prompt=provider.generate_stream.call_args.kwargs['prompt']
    assert 'first source facts' in prompt and 'second source facts' in prompt
    assert 'OLD UNRELATED TASK' not in prompt


def test_packing_budget_does_not_clip_large_inputs(monkeypatch):
    import app.study_ai_v2 as module
    batches=Mock(return_value=iter(['Handled all large sections']))
    monkeypatch.setattr(module,'_source_batch_outputs',batches)
    children=[RetrievalResult(note_context=['ş'*100000],evidence_sufficient=True) for _ in range(2)]
    result=RetrievalResult(source_batches=children,evidence_sufficient=True,
        study_task={'operation':'teach','scope':'course','quick_action':True})
    provider=Mock();provider.generate_stream.return_value=iter(['Final'])
    monkeypatch.setattr(module,'get_provider',lambda name:provider)
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    # Different contexts prevent safe exact-duplicate compaction.
    children[1].note_context=['ü'*100000]
    assert module.ask_rag_v2('Course',PROMPTS['teach'],[],result)=='Final'
    batches.assert_called_once()
    assert [len(c.note_context[0]) for c in result.source_batches]==[100000,100000]


def test_even_five_structured_questions_have_room_for_thinking_and_json(monkeypatch):
    import app.study_ai_v2 as module
    from app.study_provider import ProviderTarget
    from app.academic_quiz import render_quiz
    monkeypatch.setattr(module,'_generation_targets',lambda:[ProviderTarget('anthropic','claude-haiku-5-5')])
    questions=[dict(stem=f'Farklı kavram {n} için hangi etiket geçerlidir?',options=['a','b','c','d','e'],correct='A',rationale='Kaynak açıklaması',fact=f'Olgu {n}',source='Note.pdf sayfa 1',material_id=1,page=1) for n in range(5)]
    from types import SimpleNamespace
    provider=Mock();provider.generate_stream.return_value=iter([json.dumps({'questions':questions})])
    monkeypatch.setattr(module,'get_provider',lambda name:provider)
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    result=RetrievalResult(note_context=['facts'],evidence=[SimpleNamespace(material_id=1,page_start=1,page_end=1,display_name='Note.pdf')],evidence_sufficient=True,study_task={'operation':'generate_questions','count':5,'quiz_contract':True})
    assert 'Soru 5' in module.ask_rag_v2('Course','Beş soru',[],result)
    assert provider.generate_stream.call_args.kwargs['max_output_tokens']==16000
