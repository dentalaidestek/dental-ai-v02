import pytest
from app.academic_question_output import question_blocks, question_set_issues, limit_source_questions


def provider(monkeypatch,outputs):
    from unittest.mock import Mock
    import app.study_ai_v2 as module
    model=Mock()
    model.generate_stream.side_effect=[iter([value]) for value in outputs]
    monkeypatch.setattr(module,'target_available',lambda target:True)
    monkeypatch.setattr(module,'get_provider',lambda name:model)
    monkeypatch.setattr(module,'report_target_success',lambda target:None)
    return model


def question(number,stem):
    return f'### Soru {number}\n{stem}\nA) Birinci\nB) İkinci'


def test_numbered_source_ids_are_not_mistaken_for_output_count():
    text='\n\n'.join(question(n,f'Kök {n}') for n in (8,9,14,24))
    result=limit_source_questions(text,3)
    assert [n for n,_ in question_blocks(result)]==[8,9,14]
    assert 'Soru 24' not in result
    assert 'eksik' not in result
    incomplete=limit_source_questions(text,30)
    assert '4 soru verildi' in incomplete and '26 soru eksik' in incomplete


def test_reordered_options_and_minor_rewording_do_not_create_a_new_question():
    history=[{'role':'ASSISTANT','content':question(5,'Sella ve Gnathion noktalarını birleştirerek alt çene gelişim yönünün tayininde kullanılan doğru hangisidir?')}]
    answer=question(1,'Sella ve Gnathion noktalarını birleştirerek alt çene gelişim yönünün tayininde kullanılan doğru aşağıdakilerden hangisidir?')
    assert any('tekrarı' in issue for issue in question_set_issues(answer,1,history))
    assert question_set_issues(question(1,'Frankfort düzlemi hangi iki noktadan geçer?'),1,history)==[]


def test_count_gaps_and_internal_duplicates_are_detected():
    text=question(1,'ANB açısı nedir?')+'\n\n'+question(3,'ANB açısı nedir?')
    issues=question_set_issues(text,2,[])
    assert len(issues)==2


@pytest.mark.parametrize('bad',[
    question(1,'Kök 1'),
    question(1,'Kök 1')+'\n\n'+question(2,'Kök 1'),
])
def test_only_one_repair_is_used_and_rejected_draft_is_not_returned(monkeypatch,bad):
    from app.study_ai_v2 import ask_rag_v2
    from app.study_retrieval_v2 import RetrievalResult
    replacement=question(1,'Kök 3')
    good=question(1,'Kök 1')+'\n\n'+question(2,'Kök 3')
    model=provider(monkeypatch,[bad,replacement])
    retrieval=RetrievalResult(note_context=['Kaynak'],evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':2})
    assert ask_rag_v2('Orto','2 soru hazırla',[],retrieval)==good
    assert model.generate_stream.call_count==2


def test_second_invalid_set_is_not_saved_as_success(monkeypatch):
    from app.study_ai_v2 import ask_rag_v2
    from app.study_ai import StudyAIError
    from app.study_retrieval_v2 import RetrievalResult
    model=provider(monkeypatch,['Eksik set','Yine eksik'])
    retrieval=RetrievalResult(note_context=['Kaynak'],evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':2})
    with pytest.raises(StudyAIError,match='kontrolünü'):
        ask_rag_v2('Orto','2 soru hazırla',[],retrieval)
    assert model.generate_stream.call_count==2


def test_valid_new_questions_survive_repair_of_repeated_position(monkeypatch):
    from app.study_ai_v2 import ask_rag_v2
    from app.study_retrieval_v2 import RetrievalResult
    old=question(1,'Frankfort düzlemi hangi noktalardan geçer?')
    good=question(1,'ANB açısı nasıl hesaplanır?')
    bad=good+'\n\n'+question(2,'Frankfort düzlemi hangi noktalardan geçer?')
    model=provider(monkeypatch,[bad,question(1,'Y aksı hangi noktalardan geçer?')])
    retrieval=RetrievalResult(note_context=['Kaynak'],evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':2})
    answer=ask_rag_v2('Orto','2 soru hazırla',[{'role':'ASSISTANT','content':old}],retrieval)
    assert question_blocks(answer)[0][1]==good
    assert [n for n,_ in question_blocks(answer)]==[1,2]
    assert 'Frankfort' not in answer and 'Y aksı' in answer
    assert '"count": 1' in model.generate_stream.call_args.kwargs['prompt']


def test_extra_questions_can_be_trimmed_without_calling_model_again(monkeypatch):
    from app.study_ai_v2 import ask_rag_v2
    from app.study_retrieval_v2 import RetrievalResult
    draft='\n\n'.join(question(n,f'Kavram {n}') for n in range(1,4))
    model=provider(monkeypatch,[draft])
    retrieval=RetrievalResult(note_context=['Kaynak'],evidence_sufficient=True,
        study_task={'operation':'generate_questions','count':2})
    assert [n for n,_ in question_blocks(ask_rag_v2('Orto','2 soru hazırla',[],retrieval))]==[1,2]
    assert model.generate_stream.call_count==1
