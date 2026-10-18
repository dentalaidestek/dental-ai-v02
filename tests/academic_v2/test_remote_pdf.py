import json
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel,Session,create_engine,select

from app import academic_remote_pdf as remote
from app.study_anthropic_files import ClaudeFiles
from app.study_provider import StudyProviderError


def pdf():
    buffer=BytesIO();c=canvas.Canvas(buffer,invariant=1)
    c.setFillColorRGB(.8,.1,.1);c.drawString(30,750,'Colored original heading')
    c.setFillColorRGB(0,0,0);c.drawString(30,720,'ORIGINAL CONTENT - DO NOT REWRITE');c.save()
    return buffer.getvalue()


@pytest.fixture
def owned(tmp_path,monkeypatch):
    import app.main as main
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('STUDY_REMOTE_PDF_ENABLED','1')
    monkeypatch.setenv('STUDY_ACADEMIC_PROVIDER','anthropic')
    monkeypatch.setenv('R2_ENABLED','0')
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    factory=lambda:Session(engine,expire_on_commit=False)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    with factory() as s:
        s.add(main.User(id=1,username='owner',display_name='Owner',role='DOCTOR'))
        s.add(main.StudyCourse(id=6,owner_user_id=1,title='Perio didem'))
        for ident,owner,content in [(10,1,'# FIRST ORIGINAL PDF\nAll original text.'),
            (20,1,'# LATER PDF\nOther original text.'),(30,2,'FOREIGN SECRET')]:
            s.add(main.StudyChatMessage(id=ident,owner_user_id=owner,course_id=6,
                role='ASSISTANT',mode='RAG_V2_PDF',content=content))
        path=tmp_path/'note.pdf';path.write_bytes(pdf())
        s.add(main.StudyMaterial(id=40,owner_user_id=1,course_id=6,original_filename='notes.pdf',
            display_name='Notes',stored_filename='notes.pdf',file_path=str(path),
            mime_type='application/pdf',material_type='PDF',size_bytes=path.stat().st_size))
        s.commit()
    yield main,factory,path
    engine.dispose()


def fake_execute(monkeypatch,check=None):
    def execute(self,**kwargs):
        if check:assert check(kwargs) is not False
        return [{'name':'Renkli.pdf','data':pdf()}]
    monkeypatch.setattr(ClaudeFiles,'execute',execute)


def prepare_first(owned):
    main,factory,_=owned
    with factory() as s:
        catalog=remote.planner_catalog(s,main.StudyChatMessage,main.StudyMaterial,1,6,'Perio didem')
        return remote.prepare(s,message_model=main.StudyChatMessage,material_model=main.StudyMaterial,
            owner=1,course=6,title='Perio didem',query='İlk PDF başlıklarını renkli yap',
            plan={'sources':[catalog[0]['key']],'instructions':'Özgün ilk PDF üzerinde çalış'},session_factory=factory)


def test_catalog_has_first_original_and_never_foreign_or_internal_ids(owned):
    main,factory,_=owned
    with factory() as s:
        data=remote.planner_catalog(s,main.StudyChatMessage,main.StudyMaterial,1,6,'Perio didem')
    assert data[0]['name']=='Perio didem.pdf' and 'FIRST ORIGINAL' in data[0]['summary']
    assert data[1]['key']!=data[0]['key'] and len(data)==3
    assert 'FOREIGN' not in json.dumps(data) and all('_row' not in item and 'id' not in item for item in data)


def test_remote_edit_preserves_full_original_without_local_renderer(owned,monkeypatch):
    main,factory,_=owned
    result=prepare_first(owned)
    never=Mock(side_effect=AssertionError('No local rendering or note retrieval'))
    monkeypatch.setattr('app.academic_pdf.render_pdf',never)
    monkeypatch.setattr('app.study_ai_v2.get_provider',never)
    fake_execute(monkeypatch,lambda kw:kw['sources'][0]['data']==b'# FIRST ORIGINAL PDF\nAll original text.')
    from app.study_ai_v2 import ask_rag_v2
    content=ask_rag_v2('Perio','Renkli yap',[],result)
    assert remote.is_remote(content) and result.study_task['pdf_tool_validated']
    assert remote.read(content,owner=1,course=6)==pdf()
    never.assert_not_called()
    with pytest.raises(StudyProviderError):remote.read(content,owner=2,course=6)
    with factory() as s:
        s.delete(s.get(main.StudyChatMessage,10));s.commit()
    with factory() as s,pytest.raises(StudyProviderError):
        remote.check_dependencies(s,content,owner=1,course=6,
            message_model=main.StudyChatMessage,material_model=main.StudyMaterial)


@pytest.mark.parametrize('stream',[True,False])
def test_endpoints_save_private_remote_pdf_and_download_without_generation(owned,monkeypatch,stream):
    from fastapi.testclient import TestClient
    from app.academic_request_understanding import StudyRequest,UnderstandingResult
    main,factory,_=owned
    monkeypatch.setattr(main,'study_v2_streaming_enabled',lambda:True)
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**k:True)
    monkeypatch.setattr(main,'classify_course_scope',lambda *a:'DENTAL')
    monkeypatch.setattr('app.academic_chunk_links.planner_source_outline',lambda *a,**k:{})
    def understand(query,history,source_outline):
        assert source_outline['remote_pdf_enabled']
        return UnderstandingResult(plan=StudyRequest(resolved_query=query,operation='answer',scope='topic',
            count=None,difficulty=None,clarification='',output_format='pdf',pdf_document={
                'sources':[source_outline['pdf_catalog'][0]['key']],'instructions':'Başlıkları renkli yap'}))
    monkeypatch.setattr('app.academic_request_understanding.understand_study_request',understand)
    fake_execute(monkeypatch)
    never=Mock(side_effect=AssertionError('No local provider/renderer'))
    monkeypatch.setattr('app.study_ai_v2.get_provider',never)
    monkeypatch.setattr('app.academic_pdf.render_pdf',never)
    client=TestClient(main.app)
    response=client.post('/notes/courses/6/ai/ask'+('-stream' if stream else ''),data={'message':'İlk PDF renkli olsun'})
    assert response.status_code==200,response.text
    data=[json.loads(line) for line in response.text.splitlines()][-1] if stream else response.json()
    assert data.get('type','done')=='done',data
    assert 'ACADEMIC_REMOTE' not in response.text
    download=client.get(data['artifact']['url']);assert download.status_code==200
    assert download.content==pdf() and 'no-store' in download.headers['cache-control']
    monkeypatch.setattr(ClaudeFiles,'execute',never)
    assert client.get(data['artifact']['url']).content==pdf()
    assert client.get(data['artifact']['url'].split('?')[0]+'?part=99').status_code==404
    never.assert_not_called()
    with factory() as s:
        saved=s.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.id>30,
            main.StudyChatMessage.role=='ASSISTANT')).one()
        assert remote.manifest(saved.content,1,6)['sources'][0]['id']==10


def test_automatic_new_pdf_uses_remote_files_and_keeps_long_notice(owned,monkeypatch):
    from app.study_retrieval_v2 import RetrievalResult
    from app.academic_long_answer import automatic_pdf
    main,factory,_=owned;fake_execute(monkeypatch)
    never=Mock(side_effect=AssertionError('No local PDF rendering'))
    monkeypatch.setattr('app.academic_pdf.render_pdf',never)
    result=RetrievalResult(evidence_sufficient=True,study_task={'remote_context':{
        'owner':1,'course':6,'title':'Perio'},'remote_session_factory':factory})
    understanding=SimpleNamespace(plan=SimpleNamespace(output_format='text',resolved_query='Özetle'))
    assert main._prepare_study_pdf('Perio','All original words. '*1000,understanding,result)
    assert automatic_pdf(result.study_task['remote_pdf_manifest'],result)
    never.assert_not_called()


def test_clear_queues_owned_pdf_storage_erasure(owned,monkeypatch):
    from app.study_index_jobs import StudyDeletionJob
    from fastapi.testclient import TestClient
    main,factory,_=owned;fake_execute(monkeypatch)
    content=remote.generate(owner=1,course=6,title='Perio',instructions='PDF',session_factory=factory,markdown='Original')
    path=remote.reference(remote.manifest(content),remote.manifest(content)['files'][0])
    with factory() as s:
        s.add(main.StudyChatMessage(owner_user_id=1,course_id=6,role='ASSISTANT',mode='RAG_V2_PDF',content=content));s.commit()
    response=TestClient(main.app).post('/notes/courses/6/ai/clear',follow_redirects=False)
    assert response.status_code==303
    with factory() as s:
        jobs=list(s.exec(select(StudyDeletionJob)).all())
        assert any(job.storage_reference==path and job.owner_user_id==1 for job in jobs)


def test_durable_provider_file_cleanup_registration(owned):
    from app.study_index_jobs import StudyDeletionJob
    _,factory,_=owned
    register,done=remote._queue_cleanup(factory,1)
    register('file_uploaded')
    with factory() as s:
        job=s.exec(select(StudyDeletionJob)).one()
        assert job.provider_file_name=='anthropic-file:file_uploaded' and job.next_retry_at>job.created_at
    done('file_uploaded')
    with factory() as s:assert s.exec(select(StudyDeletionJob)).one().status=='DONE'


@pytest.fixture
def transport(monkeypatch):
    import app.study_anthropic_files as module
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-key')
    monkeypatch.setattr(module,'provider_reservation',lambda *a:nullcontext())
    monkeypatch.setattr(module,'record_api_result',lambda **kw:{})
    module._capabilities.clear()
    client=ClaudeFiles();calls=[];uploads=[];raw=pdf();turns=[]
    def request(path,**kwargs):
        calls.append((path,kwargs))
        if path.startswith('/models/'):
            return json.dumps({'capabilities':{'server_tools':{'code_execution':{'supported':True}}}}).encode()
        if path=='/files':
            assert b'expires_in_seconds' in kwargs['body'] and b'3600' in kwargs['body']
            ident='file_input'+str(len(uploads));uploads.append(ident);return json.dumps({'id':ident}).encode()
        if kwargs.get('method')=='DELETE':return b'{}'
        if path=='/messages':
            payload=json.loads(kwargs['body']);turns.append(payload)
            assert payload['container']['skills'][0]['skill_id']=='pdf'
            assert payload['tools']==[{'type':'code_execution_20260521','name':'code_execution'}]
            return json.dumps({'stop_reason':'end_turn','usage':{'input_tokens':10,'output_tokens':20},
                'content':[{'type':'bash_code_execution_tool_result','content':{
                    'type':'bash_code_execution_result','content':[{'type':'bash_code_execution_output','file_id':'file_output'}]}}]}).encode()
        if path=='/files/file_output':
            return json.dumps({'filename':'ready.pdf','mime_type':'application/pdf','downloadable':True,'size_bytes':len(raw)}).encode()
        if path=='/files/file_output/content':return raw
        raise AssertionError(path)
    monkeypatch.setattr(client,'request',request)
    return client,calls,turns,raw


def test_native_files_api_tool_skill_and_download_cleanup(transport):
    client,calls,turns,raw=transport
    outputs=client.execute(model='claude-haiku-5-5',instructions='Color headings',title='Perio',sources=[
        {'name':'Original','data':b'Complete original text','mime':'text/markdown'}])
    assert outputs==[{'name':'ready.pdf','data':raw}] and len(turns)==1
    assert turns[0]['messages'][0]['content'][1]=={'type':'container_upload','file_id':'file_input0'}
    assert {path for path,kw in calls if kw.get('method')=='DELETE'}=={'/files/file_input0','/files/file_output'}


def test_untrusted_file_citation_never_downloaded(transport):
    client,calls,_,_=transport;original=client.json_request
    def response(path,**kwargs):
        result=original(path,**kwargs)
        if path=='/messages':result['content'].append({'type':'text','citations':[{
            'type':'container_file_citation','file_id':'file_foreign'}]})
        return result
    client.json_request=response
    client.execute(model='claude-haiku-5-5',instructions='PDF',title='Perio',sources=[])
    assert not any('file_foreign' in path for path,_ in calls)


def test_pause_turn_reuses_only_current_container_and_is_bounded(transport):
    client,calls,turns,_=transport;original=client.json_request;count=0
    def response(path,**kwargs):
        nonlocal count
        result=original(path,**kwargs)
        if path=='/messages':
            count+=1
            if count==1:result.update(stop_reason='pause_turn',container={'id':'cntr_current'})
        return result
    client.json_request=response
    client.execute(model='claude-haiku-5-5',instructions='PDF',title='Perio',sources=[])
    assert len(turns)==2 and 'id' not in turns[0]['container'] and turns[1]['container']['id']=='cntr_current'


def test_missing_or_incomplete_generated_files_never_claim_success(transport):
    client,_,_,_=transport;original=client.json_request
    def response(path,**kwargs):
        result=original(path,**kwargs)
        if path=='/messages':result.update(stop_reason='max_tokens')
        return result
    client.json_request=response
    with pytest.raises(StudyProviderError):
        client.execute(model='claude-haiku-5-5',instructions='PDF',title='Perio',sources=[])


def test_internal_file_context_is_never_sent_in_generation_prompt(owned):
    from app.study_ai_v2 import _prompt
    from app.study_retrieval_v2 import RetrievalResult
    _,factory,_=owned
    result=RetrievalResult(evidence_sufficient=True,note_context=['Original source facts'],study_task={
        'remote_session_factory':factory,'remote_context':{'owner':'SECRET_INTERNAL_OWNER'},'operation':'answer'})
    prompt=_prompt('Perio','Explain',result,[])
    assert 'SECRET_INTERNAL_OWNER' not in prompt and 'remote_session_factory' not in prompt
    assert 'Original source facts' in prompt


def test_stale_catalog_key_is_rejected_before_remote_call(owned):
    main,factory,_=owned
    with factory() as s:
        key=remote.planner_catalog(s,main.StudyChatMessage,main.StudyMaterial,1,6,'Perio')[0]['key']
        row=s.get(main.StudyChatMessage,10);row.content='Changed source';s.add(row);s.commit()
        with pytest.raises(StudyProviderError):remote.prepare(s,message_model=main.StudyChatMessage,
            material_model=main.StudyMaterial,owner=1,course=6,title='Perio',query='PDF',
            plan={'sources':[key],'instructions':'PDF'},session_factory=factory)


def test_deletion_worker_processes_anthropic_files_without_gemini(owned,monkeypatch):
    from app.study_deletion_worker import run_deletion_slice
    from app.study_index_jobs import StudyDeletionJob
    _,factory,_=owned;deleted=[]
    monkeypatch.setattr(ClaudeFiles,'delete',lambda self,ident:deleted.append(ident))
    never=Mock(side_effect=AssertionError('Not a Gemini file'))
    monkeypatch.setattr('app.study_deletion_worker.delete_provider_file',never)
    with factory() as s:
        s.add(StudyDeletionJob(owner_user_id=1,material_id=-1,provider_file_name='anthropic-file:file_owned'))
        s.commit();assert run_deletion_slice(s)=='DONE'
    assert deleted==['file_owned'];never.assert_not_called()


def test_changed_quiz_output_is_rejected_and_stored_files_are_removed(owned,monkeypatch):
    _,factory,_=owned;fake_execute(monkeypatch)
    with pytest.raises(StudyProviderError):remote.generate(owner=1,course=6,title='Perio',instructions='PDF',
        session_factory=factory,markdown='Full original questions',preserve_quiz={'questions':[
            {'stem':'The missing question stem','options':['A','B','C','D','E']} ]})
    assert not list(Path('uploads/academic-pdf').rglob('*.pdf'))


def test_active_pdf_content_is_rejected(owned,monkeypatch):
    from pypdf import PdfWriter
    _,factory,_=owned
    writer=PdfWriter();writer.add_blank_page(width=400,height=500);writer.add_js('app.alert("untrusted")')
    buffer=BytesIO();writer.write(buffer)
    monkeypatch.setattr(ClaudeFiles,'execute',lambda *a,**kw:[{'name':'unsafe.pdf','data':buffer.getvalue()}])
    with pytest.raises(StudyProviderError):remote.generate(owner=1,course=6,title='Perio',instructions='PDF',
        session_factory=factory,markdown='Original')


def test_deleted_remote_file_cleanup_is_idempotent(monkeypatch):
    client=ClaudeFiles()
    monkeypatch.setattr(client,'request',Mock(side_effect=StudyProviderError('Missing',code=404)))
    client.delete('file_deleted')


def test_uncommitted_output_is_removed_on_discard(owned,monkeypatch):
    _,factory,_=owned;fake_execute(monkeypatch)
    content=remote.generate(owner=1,course=6,title='Perio',instructions='PDF',session_factory=factory,markdown='Original')
    data=remote.manifest(content);path=Path(remote.reference(data,data['files'][0]));assert path.exists()
    remote.discard({'remote_pdf_manifest':content,'remote_session_factory':factory})
    assert not path.exists()


def test_encoded_remote_plan_and_null_legacy_tool_are_compatible():
    from app.academic_request_understanding import parse_request,PlannerContractError
    from app.study_anthropic import _output_schema
    raw=dict(resolved_query='İlk PDF renkli olsun',operation='answer',scope='topic',count=None,
        difficulty=None,clarification='',retrieval_queries=[],source_subjects=[],source_kind='notes',
        depth='standard',needs_visual=False,continue_source=False,output_format='pdf',pdf_tools='null',
        pdf_document=json.dumps({'sources':['p_'+'a'*24],'instructions':'Başlıkları renkli yap'}))
    plan=parse_request(json.dumps(raw));assert plan.pdf_document['sources']==['p_'+'a'*24] and plan.pdf_tools is None
    for value in [{'sources':['file_foreign'],'instructions':'PDF'},
                  {'sources':['p_'+'a'*24],'instructions':'PDF','file_id':'file_foreign'}]:
        raw['pdf_document']=json.dumps(value)
        with pytest.raises(PlannerContractError):parse_request(json.dumps(raw))


def test_legacy_page_recipe_is_reconstructed_in_claude_not_locally(owned,monkeypatch):
    from app.academic_pdf_tools import PREFIX as PAGE_PREFIX
    from app.study_ai_v2 import ask_rag_v2
    main,factory,path=owned
    recipe={'sources':[{'kind':'material','id':40,'part':0,'digest':remote.digest(path.read_bytes())}],
        'outputs':[{'name':'Selected','segments':[{'source':0,'pages':[1],'exclude':[],'rotation':90}],'fields':[]}]}
    with factory() as s:
        s.add(main.StudyChatMessage(id=50,owner_user_id=1,course_id=6,role='ASSISTANT',
            mode='RAG_V2_PDF',content=PAGE_PREFIX+json.dumps(recipe)));s.commit()
        key=next(item['key'] for item in remote.planner_catalog(s,main.StudyChatMessage,main.StudyMaterial,1,6,'Perio')
            if item['name']=='Selected.pdf')
        result=remote.prepare(s,message_model=main.StudyChatMessage,material_model=main.StudyMaterial,
            owner=1,course=6,title='Perio',query='PDF renkli olsun',plan={'sources':[key],'instructions':'Renkli'},
            session_factory=factory)
    never=Mock(side_effect=AssertionError('Never render/rebuild legacy PDF on the web server'))
    monkeypatch.setattr('app.academic_pdf.render_pdf',never)
    monkeypatch.setattr('app.academic_pdf_tools._transform',never)
    def check(kw):
        assert kw['documents'][0]['document']['output']['segments'][0]['rotation']==90
        assert kw['documents'][0]['document']['inputs']==[{'file':'source_0.pdf'}]
        assert '"id"' not in json.dumps(kw['documents'])
        assert kw['sources'][0]['data']==path.read_bytes()
    fake_execute(monkeypatch,check)
    assert remote.is_remote(ask_rag_v2('Perio','PDF renkli olsun',[],result))
    never.assert_not_called()
