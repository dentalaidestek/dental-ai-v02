import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel,Session,create_engine,select
from app import academic_learning as learning
from app import academic_study_runs as runs
from app.academic_request_understanding import StudyRequest,UnderstandingResult


@pytest.fixture
def course_env(tmp_path,monkeypatch):
    import app.main as main
    monkeypatch.chdir(tmp_path)
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**k:True)
    monkeypatch.setattr(main,'classify_course_scope',lambda *a:'DENTAL')
    monkeypatch.setattr(runs,'wake',lambda *a:None)
    monkeypatch.setattr('app.academic_chunk_links.planner_source_outline',lambda *a,**k:{})
    monkeypatch.setattr('app.academic_dense_retrieval.prepare_query_embedding',lambda *a,**k:None)
    with Session(engine) as session:
        session.add(main.User(id=1,username='student',display_name='Student',role='DOCTOR',is_active=True))
        session.add(main.User(id=2,username='foreign',display_name='Other',role='DOCTOR',is_active=True))
        session.add(main.StudyCourse(id=6,owner_user_id=1,title='Perio'))
        session.add(main.StudyMaterial(id=40,owner_user_id=1,course_id=6,original_filename='Notes.pdf',
            display_name='Notes',stored_filename='notes.pdf',file_path='notes.pdf',mime_type='application/pdf',
            material_type='PDF',size_bytes=1,index_status='READY',active_index_version='v1'))
        session.commit()
    yield main,engine,TestClient(main.app)
    engine.dispose()


def quiz():
    return {'questions':[{'stem':'Risk kavramını tanımlayan ifade hangisidir?',
        'options':['Bir olayın olasılığı','Kesin hastalık','Tedavinin kendisi','Yaş grubu','Tanı yöntemi'],
        'correct':'A','rationale':'Kaynakta risk olasılık olarak tanımlanır.','fact':'Risk olasılık belirtir.',
        'source':'Notes.pdf, sayfa 1','material_id':40,'page':1}]}


def plan(**extra):
    return StudyRequest(resolved_query='Çalış',operation='answer',scope='topic',count=None,
        difficulty=None,clarification='',**extra)


def test_review_is_owned_idempotent_and_source_versioned(course_env):
    main,engine,_=course_env
    history=[{'role':'ASSISTANT','id':99,'content':'Saved set','quiz':quiz()}]
    versions=[(40,'notes.pdf',1,'v1',None)]
    wrong=plan(grade_previous_set=True,quiz_answers=((1,'B'),))
    with Session(engine) as session:
        for _ in range(2):
            learning.remember(session,owner=1,course=6,assistant_id=100,plan=wrong,quiz=None,history=history,versions=versions)
            session.flush()
        session.commit()
        summary=learning.context(session,1,6,versions)
        assert summary['wrong']==1 and summary['correct']==0 and summary['practiced_facts']==1
        row=session.exec(select(learning.StudyReview)).one()
        assert row.due_at>learning.now() and row.streak==0
        assert learning.context(session,2,6,versions)['practiced_facts']==0
        assert learning.context(session,1,6,[('new source',)])['practiced_facts']==0
        row.due_at=learning.now()-timedelta(seconds=1);session.add(row);session.commit()
        assert learning.context(session,1,6,versions)['due_count']==1


def test_quiz_anchor_survives_sliding_history_and_rejects_source_change(course_env):
    main,engine,_=course_env
    from app.academic_quiz import pack_evidence,previous_quiz_key
    versions=[(40,'notes.pdf',1,'v1',None)]
    with Session(engine) as session:
        row=main.StudyChatMessage(owner_user_id=1,course_id=6,role='ASSISTANT',content='Stored PDF',mode='RAG_V2_PDF')
        row.source_evidence_json=pack_evidence('[]',quiz(),row.content,versions)
        session.add(row);session.flush()
        learning.remember(session,owner=1,course=6,assistant_id=row.id,plan=plan(),quiz=quiz(),history=[],versions=versions)
        session.commit()
        history=[{'id':100+i,'role':'USER','content':'Unrelated'} for i in range(8)]
        result=main._study_learning_context(session,1,6,versions,history)
        assert result['active_quiz']==quiz() and len(history)==9
        assert '**1. A**' in previous_quiz_key(history)
        assert learning.quiz_anchor(session,1,6,[('changed',)]) is None
        assert learning.quiz_anchor(session,2,6,versions) is None


def fake_generation(main,monkeypatch,*,fail=False):
    from app.study_retrieval_v2 import RetrievalResult
    monkeypatch.setattr('app.academic_request_understanding.understand_study_request',
        lambda *a,**k:UnderstandingResult(plan=plan()))
    monkeypatch.setattr('app.academic_request_understanding.retrieve_understood_course_context',
        lambda *a,**k:RetrievalResult(evidence_sufficient=True,note_context=['Indexed evidence']))
    calls=[]
    def stream(*args):
        calls.append(1)
        if fail:raise main.StudyAIError('Synthetic failure')
        yield 'Tamamlanan çalışma.'
    monkeypatch.setattr(main,'stream_study_ai_v2',stream)
    return calls


def test_durable_work_finishes_after_client_closes_and_deduplicates(course_env,monkeypatch):
    main,engine,client=course_env;calls=fake_generation(main,monkeypatch)
    data={'message':'Risk nedir?','request_key':'a'*32}
    response=client.post('/notes/courses/6/ai/runs',data=data)
    assert response.status_code==202,response.text
    ident=response.json()['run']['id']
    assert client.post('/notes/courses/6/ai/runs',data=data).json()['run']['id']==ident
    client.close()
    runs._drain(engine)
    reopened=TestClient(main.app)
    result=reopened.get(f'/notes/courses/6/ai/runs/{ident}').json()['run']
    assert result['status']=='DONE' and result['answer']=='Tamamlanan çalışma.' and len(calls)==1
    assert reopened.post('/notes/courses/6/ai/runs',data=data).json()['run']['id']==ident
    with Session(engine) as session:
        assert len(session.exec(select(main.StudyChatMessage)).all())==2
        assert session.exec(select(runs.StudyRun)).one().assistant_message_id is not None


def test_run_access_and_admission_are_owned(course_env,monkeypatch):
    main,engine,client=course_env
    response=client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'a'*32})
    ident=response.json()['run']['id']
    assert client.post('/notes/courses/6/ai/runs',data={'message':'Other','request_key':'b'*32}).status_code==409
    assert client.post('/notes/courses/6/ai/runs',data={'message':'Other','request_key':'a'*32}).status_code==409
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=2,role='DOCTOR'))
    assert client.get(f'/notes/courses/6/ai/runs/{ident}').status_code==404
    assert client.get('/notes/courses/6/ai/learning').status_code==404
    assert client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'c'*32}).status_code==404


def test_failed_work_is_not_automatically_rebilled(course_env,monkeypatch):
    main,engine,client=course_env;calls=fake_generation(main,monkeypatch,fail=True)
    ident=client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'a'*32}).json()['run']['id']
    runs._drain(engine);runs._drain(engine)
    assert len(calls)==1
    assert client.get(f'/notes/courses/6/ai/runs/{ident}').json()['run']['status']=='FAILED'
    with Session(engine) as session:assert not session.exec(select(main.StudyChatMessage)).all()


def test_chat_clear_prevents_inflight_work_from_resurrecting_messages(course_env,monkeypatch):
    main,engine,client=course_env
    ident=client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'a'*32}).json()['run']['id']
    run=runs.claim(engine)
    with Session(engine) as session:
        learning.erase(session,1,6,keep_reviews=True);runs.erase(session,1,6);session.commit()
    with Session(engine) as session,pytest.raises(ValueError):
        runs.complete_in_transaction(session,run_id=ident,owner=1,course=6,message_id=999)
    with Session(engine) as session:
        assert session.get(runs.StudyRun,ident).status=='CANCELLED'
        assert not session.exec(select(main.StudyChatMessage)).all()


def test_erasure_removes_learning_and_request_content(course_env):
    main,engine,_=course_env
    with Session(engine) as session:
        runs.enqueue(session,owner=1,course=6,question='Private question',key='a'*32)
        learning.erase(session,1,6);runs.erase(session,1,6,purge=True);session.commit()
        assert not session.exec(select(runs.StudyRun)).all()
        assert not session.exec(select(learning.StudyLearningState)).all()


def test_interrupted_work_is_reported_without_retry(course_env):
    main,engine,client=course_env
    ident=client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'a'*32}).json()['run']['id']
    runs.claim(engine)
    with Session(engine) as session:
        row=session.get(runs.StudyRun,ident);row.updated_at=learning.now()-timedelta(minutes=20)
        session.add(row);session.commit()
    assert client.get(f'/notes/courses/6/ai/runs/{ident}').json()['run']['status']=='INTERRUPTED'


def test_stepwise_teaching_only_uses_first_lesson_batch(monkeypatch):
    from app import study_ai_v2 as ai
    from app.study_retrieval_v2 import RetrievalResult
    first=RetrievalResult(note_context=['FIRST LESSON'],evidence_sufficient=True)
    second=RetrievalResult(note_context=['LATER LESSON'],evidence_sufficient=True)
    parent=RetrievalResult(source_batches=[first,second],evidence_sufficient=True,
        study_task={'operation':'teach','quick_action':True})
    calls=[]
    def stream(course,question,history,result):
        calls.append(result)
        assert result.note_context==['FIRST LESSON'] and not result.source_coverage_complete
        assert result.study_task['stepwise_teaching']
        yield 'Short explanation, then one check question.'
    monkeypatch.setattr(ai,'stream_rag_v2',stream)
    assert 'one check' in ''.join(ai._stream_source_batches('Perio','Başla',[],parent))
    assert len(calls)==1


def test_persistent_quiz_is_not_duplicated_in_planner_input():
    from app.academic_request_understanding import interpret_request
    captured=[]
    def call(prompt):captured.append(json.loads(prompt));return '{}'
    interpret_request('Cevaplarım 1 A',[],source_outline={'learning':{'active_quiz':quiz(),'active_request':{}}},call=call)
    assert captured[0]['recent_quiz']==quiz()
    assert 'active_quiz' not in captured[0]['source_outline']['learning']


def test_real_clear_endpoint_cancels_queued_work(course_env):
    main,engine,client=course_env
    ident=client.post('/notes/courses/6/ai/runs',data={'message':'Risk','request_key':'a'*32}).json()['run']['id']
    response=client.post('/notes/courses/6/ai/clear',follow_redirects=False)
    assert response.status_code==303
    with Session(engine) as session:
        row=session.get(runs.StudyRun,ident)
        assert row.status=='CANCELLED' and row.question==''


def test_learning_bootstraps_legacy_pdf_quiz_before_state_exists(course_env):
    main,engine,_=course_env
    from app.academic_quiz import pack_evidence
    versions=[(40,'notes.pdf',1,'v1',None)]
    with Session(engine) as session:
        row=main.StudyChatMessage(owner_user_id=1,course_id=6,role='ASSISTANT',content='Old PDF',mode='RAG_V2_PDF')
        row.source_evidence_json=pack_evidence('[]',quiz(),row.content,versions)
        session.add(row);session.commit()
        anchor=learning.quiz_anchor(session,1,6,versions)
        assert anchor['quiz']==quiz()


def test_additive_study_table_creation_is_idempotent():
    from app.migrate import _create_study_tables
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        _create_study_tables(connection);_create_study_tables(connection)
    from sqlalchemy import inspect
    assert {'studyrun','studylearningstate','studyreview','studyattempt'}<=set(inspect(engine).get_table_names())
    engine.dispose()


def test_version_twelve_upgrade_does_not_replay_historical_migrations(monkeypatch):
    from contextlib import contextmanager
    import app.migrate as migration
    statements=[];created=[]
    class Connection:
        def execute(self,query,params=None):
            statements.append(str(query))
            return SimpleNamespace(scalar=lambda:12)
    @contextmanager
    def begin():yield Connection()
    engine=SimpleNamespace(dialect=SimpleNamespace(name='postgresql'),begin=begin)
    monkeypatch.setattr(migration,'inspect',lambda connection:SimpleNamespace(has_table=lambda name:True))
    monkeypatch.setattr(migration,'_create_study_tables',lambda conn:created.append(True))
    assert migration._upgrade_learning_schema(SimpleNamespace(engine=engine))
    assert created==[True] and not any('ALTER TABLE' in sql or 'retention' in sql for sql in statements)
    assert not any('UPDATE dental_schema_revision' in sql for sql in statements)


def test_worker_pins_stored_pdf_without_http_scope_and_releases_each_job(course_env,monkeypatch,tmp_path):
    main,engine,client=course_env
    fake_generation(main,monkeypatch)
    from app import object_cache
    monkeypatch.setenv('R2_CACHE_DIR',str(tmp_path/'cache'))
    readers=[];handles=[]
    def stream(*args):
        def download(path,size):path.write_bytes(b'%PDF-test')
        path=object_cache.materialize('source.pdf',metadata=lambda:{'ContentLength':9},download=download)
        reader=object_cache._scope.get()
        readers.append(reader);handles.extend(reader.values())
        assert path.read_bytes()==b'%PDF-test'
        yield 'PDF okundu.'
    monkeypatch.setattr(main,'stream_study_ai_v2',stream)
    assert object_cache._scope.get() is None
    for key in ('a','b'):
        ident=client.post('/notes/courses/6/ai/runs',data={'message':'PDF incele','request_key':key*32}).json()['run']['id']
        runs._drain(engine)
        assert client.get(f'/notes/courses/6/ai/runs/{ident}').json()['run']['status']=='DONE'
        assert object_cache._scope.get() is None
        assert all(handle.closed for handle in handles)
    assert len(readers)==2 and readers[0] is not readers[1]


def test_saved_quiz_pdf_export_keeps_questions_and_key_outside_recent_window(monkeypatch):
    from app.academic_request_understanding import retrieve_understood_course_context
    from app.academic_quiz import render_quiz
    from app import study_ai_v2 as ai
    saved=quiz()
    history=[{'role':'ASSISTANT','content':'Stored PDF','quiz':saved}]+[
        {'role':'ASSISTANT','content':'Unrelated explanation'} for _ in range(10)]
    export=plan(export_previous_quiz=True,show_quiz_answers=True,output_format='pdf')
    result=retrieve_understood_course_context(None,understanding=UnderstandingResult(plan=export),
        owner_user_id=1,course_id=6,query='Sorular ve anahtar PDF olsun',recent_history=history)
    assert result.retrieval_mode=='generated_quiz_export'
    assert result.prepared_answer==render_quiz(saved,True)
    assert result.generated_quiz==saved
    monkeypatch.setattr(ai,'get_provider',lambda *a:pytest.fail('No new answer generation for exact export'))
    assert ''.join(ai.stream_rag_v2('Perio','PDF',history,result))==result.prepared_answer


def test_saved_quiz_export_cannot_grade_or_reveal_only_key():
    from dataclasses import asdict
    from app.academic_request_understanding import parse_request,PlannerContractError
    export=plan(export_previous_quiz=True,show_quiz_answers=True,output_format='pdf')
    assert parse_request(json.dumps(asdict(export))).export_previous_quiz
    invalid={**asdict(export),'reveal_previous_key':True}
    with pytest.raises(PlannerContractError):parse_request(json.dumps(invalid))
