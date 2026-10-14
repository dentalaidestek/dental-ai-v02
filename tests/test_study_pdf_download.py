from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
import pytest


@pytest.fixture
def pdf_client(monkeypatch):
    import app.main as main
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    with Session(engine) as session:
        session.add(main.User(id=1,username='owner',display_name='Synthetic',role='DOCTOR'))
        session.add(main.User(id=2,username='other',display_name='Synthetic Other',role='DOCTOR'))
        session.add(main.StudyCourse(id=1,owner_user_id=1,title='Orto'))
        session.add(main.StudyCourse(id=2,owner_user_id=2,title='Private'))
        for id,owner,course,role,mode in [
            (1,1,1,'ASSISTANT','RAG_V2_HYBRID_STREAM_PDF'),
            (2,2,2,'ASSISTANT','RAG_V2_HYBRID_STREAM_PDF'),
            (3,1,1,'ASSISTANT','RAG_V2_HYBRID_STREAM'),
            (4,1,1,'USER','RAG_V2_HYBRID_STREAM_PDF'),
        ]:
            session.add(main.StudyChatMessage(id=id,owner_user_id=owner,course_id=course,
                role=role,mode=mode,content='Pronasale: Burun ucu.'))
        session.commit()
    return main,TestClient(main.app)


def test_only_owned_requested_pdf_can_be_downloaded(pdf_client):
    main,client=pdf_client
    response=client.get('/notes/courses/1/ai/messages/1/pdf')
    assert response.status_code==200 and response.content.startswith(b'%PDF-')
    assert response.headers['content-type']=='application/pdf'
    assert 'attachment;' in response.headers['content-disposition']
    assert response.headers['cache-control']=='no-store'
    for path in ['/notes/courses/2/ai/messages/2/pdf',
                 '/notes/courses/1/ai/messages/2/pdf',
                 '/notes/courses/1/ai/messages/3/pdf',
                 '/notes/courses/1/ai/messages/4/pdf']:
        assert client.get(path).status_code==404


def test_cleared_history_invalidates_download_without_orphan_storage(pdf_client):
    main,client=pdf_client
    with Session(main.engine) as session:
        message=session.get(main.StudyChatMessage,1)
        session.delete(message);session.commit()
    assert client.get('/notes/courses/1/ai/messages/1/pdf').status_code==404


def test_no_session_has_no_pdf_access(pdf_client,monkeypatch):
    main,client=pdf_client
    monkeypatch.setattr(main,'get_current_user',lambda request:None)
    assert client.get('/notes/courses/1/ai/messages/1/pdf').status_code==401


def test_page_text_reads_published_ocr_with_owner_and_version_fences(pdf_client,monkeypatch):
    main,client=pdf_client
    with Session(main.engine) as session:
        session.add(main.StudyMaterial(id=71,course_id=1,owner_user_id=1,
            original_filename='exam.pdf',display_name='exam',stored_filename='exam.pdf',
            file_path='unused',material_type='PDF',mime_type='application/pdf',size_bytes=10,
            index_status='READY',active_index_version='v2'))
        session.add(main.StudyIndexPage(owner_user_id=1,course_id=1,material_id=71,
            index_version='v2',page_number=4,status='OCR_DONE',extraction_method='LOCAL_OCR',
            text_content='14. Kök\nc. Devam şıkkı\n15. Sonraki soru'))
        session.add(main.StudyIndexPage(owner_user_id=1,course_id=1,material_id=71,
            index_version='v1',page_number=4,text_content='STALE_PRIVATE'))
        for owner,version,body in [(1,'v2','PUBLISHED'),(1,'v1','STALE_PRIVATE'),(2,'v2','FOREIGN_PRIVATE')]:
            session.add(main.StudyIndexChunk(owner_user_id=owner,course_id=1,material_id=71,
                index_version=version,chunk_index=owner,page_start=4,page_end=4,
                text_content=body,text_sha256='synthetic'))
        session.commit()
    response=client.get('/notes/courses/1/materials/71/pages/4/text?format=json')
    assert response.status_code==200
    assert response.json()['ocr_text'].endswith('15. Sonraki soru')
    assert [c['text'] for c in response.json()['chunks']]==['PUBLISHED']
    assert 'private, no-store'==response.headers['cache-control']
    page=client.get('/notes/courses/1/materials/71/pages/4/text')
    assert page.status_code==200 and 'text/html' in page.headers['content-type']
    assert 'PUBLISHED' in page.text and 'STALE_PRIVATE' not in page.text and 'FOREIGN_PRIVATE' not in page.text
    assert client.get('/notes/courses/2/materials/71/pages/4/text').status_code==404
    assert client.get('/notes/courses/1/materials/71/pages/999/text').status_code==404
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=2,role='DOCTOR'))
    assert client.get('/notes/courses/1/materials/71/pages/4/text').status_code==404
    monkeypatch.setattr(main,'get_current_user',lambda request:None)
    assert client.get('/notes/courses/1/materials/71/pages/4/text').status_code==401


def test_unapproved_chat_upload_never_wakes_or_indexes(pdf_client,monkeypatch):
    main,client=pdf_client
    monkeypatch.delenv('STUDY_CHAT_ATTACHMENTS_ENABLED',raising=False)
    def forbidden(*args,**kwargs):
        raise AssertionError('Unapproved upload performed work')
    monkeypatch.setattr(main,'_wake_academic_modal_indexer',forbidden)
    response=client.post('/notes/courses/1/materials',data={'chat_upload':'true'},
        files=[('files',('test.pdf',b'%PDF-1.4','application/pdf'))])
    assert response.status_code==403
    assert 'açık değil' in response.json()['error']


def test_enabled_chat_upload_queues_each_file_and_wakes_once(pdf_client,monkeypatch,tmp_path):
    from app.academic_pdf import render_pdf
    main,client=pdf_client
    monkeypatch.setenv('STUDY_CHAT_ATTACHMENTS_ENABLED','1')
    monkeypatch.setattr(main,'UPLOAD_DIR',tmp_path)
    queued=[];wakes=[]
    monkeypatch.setattr(main,'enqueue_material_v2',lambda session,material:queued.append(material.id))
    monkeypatch.setattr(main,'legacy_indexing_required',lambda:False)
    monkeypatch.setattr(main,'_wake_academic_modal_indexer',lambda:wakes.append(True))
    monkeypatch.setattr(main,'storage_persist_file',lambda *args,**kwargs:None)
    data=render_pdf('Orto','Pronasale: Burun ucu.')
    response=client.post('/notes/courses/1/materials',data={'chat_upload':'true'},
        files=[('files',('note-a.pdf',data,'application/pdf')),
               ('files',('note-b.pdf',data,'application/pdf'))])
    assert response.status_code==200 and response.json()['added']==2
    assert len(queued)==2 and len(set(queued))==2 and wakes==[True]


@pytest.mark.parametrize('output_format,fail', [('text',False),('pdf',False),('pdf',True)])
def test_stream_advertises_only_completed_requested_pdf(pdf_client,monkeypatch,output_format,fail):
    import json
    from sqlmodel import select
    import app.academic_chunk_links as links
    import app.academic_request_understanding as understanding_module
    import app.academic_dense_retrieval as dense
    import app.academic_pdf as pdf
    main,client=pdf_client
    with Session(main.engine) as session:
        session.add(main.StudyMaterial(course_id=1,owner_user_id=1,
            original_filename='ortodonti.pdf',display_name='Orto',stored_filename='ortodonti.pdf',
            file_path='/synthetic/ortodonti.pdf',material_type='PDF',mime_type='application/pdf',size_bytes=100))
        session.commit()
    plan=SimpleNamespace(output_format=output_format,operation='answer')
    retrieval=SimpleNamespace(evidence_sufficient=True,source_material_ids=[],evidence=[],
        visual_sources=[],source_batches=[],attachments=[])
    monkeypatch.setattr(main,'study_v2_streaming_enabled',lambda:True)
    monkeypatch.setattr(main,'course_v2_ready',lambda *args,**kwargs:True)
    monkeypatch.setattr(main,'classify_course_scope',lambda *args:'DENTAL')
    monkeypatch.setattr(links,'planner_source_outline',lambda *args,**kwargs:[])
    monkeypatch.setattr(understanding_module,'understand_study_request',lambda *args,**kwargs:SimpleNamespace(plan=plan))
    monkeypatch.setattr(understanding_module,'retrieve_understood_course_context',lambda *args,**kwargs:retrieval)
    monkeypatch.setattr(dense,'prepare_query_embedding',lambda *args,**kwargs:None)
    monkeypatch.setattr(main,'stream_study_ai_v2',lambda *args:iter(['Pronasale: ','Burun ucu.']))
    if fail:
        def unavailable(*args):
            raise pdf.AcademicPDFError('Synthetic renderer failure')
        monkeypatch.setattr(pdf,'render_pdf',unavailable)
    response=client.post('/notes/courses/1/ai/ask-stream',data={'message':'Pronasale nedir?'})
    assert response.status_code==200
    events=[json.loads(line) for line in response.text.splitlines()]
    with Session(main.engine) as session:
        saved=list(session.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.id>4)))
    if fail:
        assert events[-1]['type']=='error' and saved==[]
        assert all('artifact' not in event for event in events)
    else:
        assert events[-1]['type']=='done' and len(saved)==2
        if output_format=='pdf':
            artifact=events[-1]['artifact']
            assert artifact['type']=='pdf'
            assert client.get(artifact['url']).content.startswith(b'%PDF-')
            assert saved[-1].mode.endswith('_PDF')
        else:
            assert 'artifact' not in events[-1] and not saved[-1].mode.endswith('_PDF')


@pytest.mark.parametrize('byte_budget,expected_pages',[(1024,16),(25,2)])
def test_visual_hydration_uses_one_owned_bounded_read(pdf_client,monkeypatch,byte_budget,expected_pages):
    import app.study_retrieval_v2 as retrieval
    from app.study_index_jobs import StudyIndexPage
    from sqlalchemy import event
    main,client=pdf_client
    monkeypatch.setattr(retrieval,'_VISUAL_REQUEST_MAX_BYTES',byte_budget)
    with retrieval._PAGE_PDF_CACHE_LOCK:retrieval._PAGE_PDF_CACHE.clear()
    with Session(main.engine) as session:
        for id,owner,course in [(41,1,1),(42,2,2)]:
            session.add(main.StudyMaterial(id=id,course_id=course,owner_user_id=owner,
                original_filename='source.pdf',display_name='Source',stored_filename='source.pdf',
                file_path='/synthetic/source.pdf',material_type='PDF',mime_type='application/pdf',size_bytes=100,
                active_index_version='v2',index_status='READY'))
            for page in range(1,17):
                session.add(StudyIndexPage(owner_user_id=owner,course_id=course,material_id=id,
                    index_version='v2',page_number=page,visual_pdf_bytes=b'%PDF-12345'))
        session.commit()
    sources=[dict(owner_user_id=1,material_id=41,index_version='v2',reference='ref',
        page_number=page,mime_type='application/pdf',display_name='Source') for page in range(1,17)]
    sources += [dict(sources[0],material_id=42),dict(sources[0],index_version='obsolete')]
    queries=[]
    def capture(connection,cursor,statement,params,context,executemany):
        if statement.startswith('WITH page_data'):queries.append(statement)
    event.listen(main.engine,'before_cursor_execute',capture)
    try:
        result=retrieval.RetrievalResult(visual_sources=sources,evidence_sufficient=True,source_coverage_complete=True)
        retrieval.materialize_visual_sources(lambda:Session(main.engine),result)
        assert len(queries)==1 and len(result.attachments)==expected_pages
        assert all(item['material_id']==41 for item in result.attachments)
        assert len({item['page_number'] for item in result.attachments})==expected_pages
        assert sum(len(item['data']) for item in result.attachments)<=byte_budget
        assert not result.source_coverage_complete
    finally:
        event.remove(main.engine,'before_cursor_execute',capture)
        with retrieval._PAGE_PDF_CACHE_LOCK:retrieval._PAGE_PDF_CACHE.clear()
