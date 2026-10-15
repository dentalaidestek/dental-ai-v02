from types import SimpleNamespace
from unittest.mock import Mock
from app.academic_native_evidence import selected_native_pages, apply_native_pages
from app.study_retrieval_v2 import RetrievalResult


def evidence(material=1, page=68):
    return SimpleNamespace(chunk_id=page,material_id=material,page_start=page,page_end=page)


def test_native_checkpoint_restores_missing_numeric_sentence_only_on_selected_pairs():
    session=Mock()
    session.get_bind.return_value.dialect.name='postgresql'
    session.exec.return_value.all.return_value=[
        (1,68,'Notes.pdf','Yüz Açısı\nİdeal değer Downs’a göre\n87.8 derece, Türk çocukları\niçin ise 84 derece olarak\nbulunmuştur.'),
        (2,68,'Other.pdf','Not selected'),(1,90,'Notes.pdf','Not selected')]
    native=selected_native_pages(session,owner_user_id=17,course_id=23,evidence=[evidence()])
    assert set(native)=={(1,68)}
    assert '87.8 derece' in native[1,68] and '84 derece' in native[1,68]
    sql=session.exec.call_args.args[0].text
    assert "m.active_index_version=p.index_version" in sql
    assert "p.owner_user_id=:owner AND p.course_id=:course" in sql
    assert "m.deleted_at IS NULL" in sql and "q.content_kind='QUESTION'" in sql
    assert session.exec.call_args.kwargs['params']=={'owner':17,'course':23,'chunk_ids':[68],'ids':[1],'pages':[68]}
    result=RetrievalResult(evidence=[evidence()],note_context=['[KANIT material_id=1 sayfa=68 tür=TEXT] Truncated old fragment'])
    apply_native_pages(result,native)
    assert len(result.note_context)==1 and '87.8 derece' in result.note_context[0]
    assert result.evidence[0].page_start==68


def test_native_page_containing_mcq_is_not_promoted_to_factual_evidence():
    session=Mock();session.get_bind.return_value.dialect.name='postgresql'
    session.exec.return_value.all.return_value=[(1,68,'Exam.pdf','1. Hangi ifade yanlıştır?\nA) Yanlış bilgi\nB) Başka bilgi')]
    assert not selected_native_pages(session,owner_user_id=17,course_id=23,evidence=[evidence()])


def test_native_replacement_preserves_scan_notices_and_uncovered_pages():
    a,b=evidence(),evidence(page=69)
    result=RetrievalResult(evidence=[a,b],note_context=['SCAN warning','[KANIT material_id=1 sayfa=68 tür=TEXT] Old native fragment','Original scan notice'])
    apply_native_pages(result,{(1,68):'[KANIT_NATIVE complete] Full text'})
    assert result.note_context==['SCAN warning','Original scan notice','[KANIT_NATIVE complete] Full text']
