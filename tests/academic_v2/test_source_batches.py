import pytest
from app.academic_source_batches import partition_source_rows, load_owned_source_rows


def row(cid, page, heading='Deri noktalar > Tek noktalar', material=1, text='definition'):
    return (cid,material,'note',page,page,heading,'TEXT',text,None,None,None,None,1,cid,'{}')


def test_long_section_keeps_every_middle_and_end_page_in_source_order():
    rows = [row(i,i) for i in range(1,1001)]
    batches = partition_source_rows(reversed(rows), max_pages=16)
    assert [cid for batch in batches for cid in batch.chunk_ids] == list(range(1,1001))
    assert len(batches) == 63
    assert all(len(batch.chunk_ids) <= 16 for batch in batches)


def test_heading_and_document_boundaries_are_preserved_and_duplicates_removed():
    rows = [row(1,1),row(1,1),row(2,2,'Deri noktalar > Çift noktalar'),
            row(3,1,material=2)]
    batches = partition_source_rows(rows)
    assert [batch.chunk_ids for batch in batches] == [(1,2),(3,)]
    assert 'Tek' in batches[0].title and 'Çift' in batches[0].title


def test_character_budget_splits_without_discarding_remainder():
    batches = partition_source_rows([row(i,i,text='a'*300) for i in range(1,9)],max_chars=1200)
    assert [cid for batch in batches for cid in batch.chunk_ids] == list(range(1,9))
    assert len(batches) > 1
    with pytest.raises(ValueError, match='exceeds'):
        partition_source_rows([row(1,1,text='a'*2000)],max_chars=1200)


def test_reader_paginates_beyond_old_limit_with_owner_course_fences(monkeypatch):
    import app.study_retrieval_v2 as module
    rows = [row(i,i) for i in range(1,301)]
    calls=[]
    def metadata(session, **kw):
        calls.append(kw)
        return [r for r in rows if r[0]>kw['after_id']][:kw['limit']]
    def hydrate(session, **kw):
        assert kw['owner_user_id']==17 and kw['course_id']==23
        return [r for r in rows if r[0] in kw['chunk_ids']]
    monkeypatch.setattr(module,'_coverage_metadata_page',metadata)
    monkeypatch.setattr(module,'_coverage_evidence_rows',hydrate)
    assert len(list(load_owned_source_rows(None,owner_user_id=17,course_id=23)))==300
    assert [kw['after_id'] for kw in calls]==[0,128,256,300]
    assert all(kw['owner_user_id']==17 and kw['course_id']==23 for kw in calls)
