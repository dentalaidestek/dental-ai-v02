import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine
from app.academic_pdf_tools import prepare_operations, render_owned_recipe, validate_tools, output_files, PREFIX, PDFToolError
from app.academic_request_understanding import parse_request, UnderstandingResult, retrieve_understood_course_context

def source(kind='generated', filename='', turn=None, part=0):
    return dict(kind=kind, filename=filename, turn=turn, part=part)

def segment(index=0, pages=None, exclude=None, rotation=0):
    return dict(source=index, pages=pages or [], exclude=exclude or [], rotation=rotation)

def output(name='Sonuç', segments=None, fields=None):
    return dict(name=name, segments=segments or [segment()], fields=fields or [])

def tool(action='transform', sources=None, outputs=None):
    return dict(action=action, sources=sources or [source()], outputs=outputs if outputs is not None else [output()])

def pdf_bytes(pages=4, form=False):
    buffer=BytesIO(); doc=canvas.Canvas(buffer, pagesize=(400,500))
    for n in range(1,pages+1):
        doc.drawString(30,450,f'ORIGINAL PAGE {n}')
        doc.circle(100,200,30,fill=1)
        if form and n==1:
            doc.acroForm.textfield(name='full_name',x=30,y=350,width=200,height=25)
        doc.showPage()
    doc.save(); return buffer.getvalue()

@pytest.fixture
def owned(tmp_path):
    import app.main as main
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    path=tmp_path/'original.pdf'; path.write_bytes(pdf_bytes())
    with Session(engine,expire_on_commit=False) as session:
        session.add(main.StudyChatMessage(id=10,owner_user_id=1,course_id=6,role='ASSISTANT',
            mode='RAG_V2_PDF',content='## Original\nSOURCE TEXT'))
        session.add(main.StudyChatMessage(id=11,owner_user_id=2,course_id=7,role='ASSISTANT',
            mode='RAG_V2_PDF',content='FOREIGN SECRET'))
        session.add(main.StudyMaterial(id=20,owner_user_id=1,course_id=6,
            original_filename='original.pdf',display_name='Original',stored_filename='original.pdf',
            file_path=str(path),material_type='PDF',mime_type='application/pdf',size_bytes=path.stat().st_size))
        session.commit()
        yield session,main,path
    engine.dispose()

def prepare(owned,value,query='PDF işlemi',history=()):
    session,main,_=owned
    return prepare_operations(session,message_model=main.StudyChatMessage,material_model=main.StudyMaterial,
        plan=SimpleNamespace(pdf_tools=value,resolved_query='PDF işlemi'),owner_user_id=1,course_id=6,
        history=history,query=query,title='Perio')

def download(owned,content,part=0):
    session,main,_=owned
    return render_owned_recipe(session,message_model=main.StudyChatMessage,material_model=main.StudyMaterial,
        owner_user_id=1,course_id=6,content=content,part=part,title='Perio')

def test_uploaded_reorder_rotate_duplicate_preserves_graphics(owned):
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')],
        outputs=[output(segments=[segment(pages=[-1,1,1],rotation=90)])]))
    assert result.retrieval_mode=='pdf_tool_document',result.clarification
    reader=PdfReader(BytesIO(download(owned,result.prepared_answer)))
    assert len(reader.pages)==3
    assert all(f'ORIGINAL PAGE {n}' in page.extract_text() for page,n in zip(reader.pages,[4,1,1]))
    assert all(page.rotation==90 for page in reader.pages)
    assert b' c' in reader.pages[0].get_contents().get_data()

def test_split_outputs_remove_pages_and_never_call_provider(owned,monkeypatch):
    never=Mock(side_effect=AssertionError('No provider for mechanical page tools'))
    monkeypatch.setattr('app.study_provider.get_provider',never)
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')],outputs=[
        output('İlk bölüm',[segment(pages=[1,2])]),output('Son bölüm',[segment(exclude=[1,2])])]))
    files=output_files(result.prepared_answer,6,99)
    assert len(files)==2 and files[1]['url'].endswith('/99/pdf?part=1')
    for part,first in [(0,1),(1,3)]:
        reader=PdfReader(BytesIO(download(owned,result.prepared_answer,part)))
        assert len(reader.pages)==2 and f'ORIGINAL PAGE {first}' in reader.pages[0].extract_text()
    with pytest.raises(PDFToolError): download(owned,result.prepared_answer,2)
    never.assert_not_called()

def test_generated_title_and_content_are_preserved(owned):
    result=prepare(owned,tool())
    text=PdfReader(BytesIO(download(owned,result.prepared_answer))).pages[0].extract_text()
    assert 'Perio' in text and 'SOURCE TEXT' in text

def test_interactive_form_inspection_fill_and_appearance(owned):
    session,main,path=owned; path.write_bytes(pdf_bytes(pages=1,form=True))
    row=session.get(main.StudyMaterial,20); row.size_bytes=path.stat().st_size
    session.add(row); session.commit()
    inspected=prepare(owned,tool('inspect',[source('uploaded','original.pdf')],[]))
    assert 'full_name' in inspected.prepared_answer and 'Sayfa sayısı: 1' in inspected.prepared_answer
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')],
        outputs=[output(fields=[{'name':'full_name','value':'Cihan'}])]),
        query='full_name alanına Cihan yaz')
    assert result.evidence_sufficient,result.clarification
    reader=PdfReader(BytesIO(download(owned,result.prepared_answer)))
    assert reader.get_fields()['full_name']['/V']=='Cihan'
    assert reader.pages[0]['/Annots'][0].get_object()['/AP']['/N']

def test_exact_selected_text_is_returned_without_rewriting(owned):
    result=prepare(owned,tool('extract_text',[source('uploaded','original.pdf')],
        [output(segments=[segment(pages=[3])])]))
    assert result.retrieval_mode=='pdf_tool_text'
    assert 'ORIGINAL PAGE 3' in result.prepared_answer and 'ORIGINAL PAGE 1' not in result.prepared_answer

def test_foreign_changed_and_deleted_sources_cannot_be_read(owned):
    result=prepare(owned,tool(sources=[source(turn=0)]),
        history=[{'id':11,'role':'ASSISTANT','mode':'RAG_V2_PDF'}])
    assert not result.evidence_sufficient and 'FOREIGN' not in result.clarification
    created=prepare(owned,tool(sources=[source('uploaded','original.pdf')]))
    owned[2].write_bytes(pdf_bytes(pages=2))
    with pytest.raises(PDFToolError): download(owned,created.prepared_answer)
    session,main,_=owned; session.delete(session.get(main.StudyMaterial,20)); session.commit()
    with pytest.raises(PDFToolError): download(owned,created.prepared_answer)

def test_nested_recipe_respects_page_order_and_parent_deletion(owned):
    first=prepare(owned,tool(sources=[source('uploaded','original.pdf')],
        outputs=[output(segments=[segment(pages=[2,4])])]))
    session,main,_=owned
    session.add(main.StudyChatMessage(id=30,owner_user_id=1,course_id=6,role='ASSISTANT',
        mode='RAG_V2_PDF',content=first.prepared_answer)); session.commit()
    second=prepare(owned,tool(outputs=[output(segments=[segment(pages=[2])])]))
    reader=PdfReader(BytesIO(download(owned,second.prepared_answer)))
    assert len(reader.pages)==1 and 'ORIGINAL PAGE 4' in reader.pages[0].extract_text()
    session.delete(session.get(main.StudyChatMessage,30)); session.commit()
    with pytest.raises(PDFToolError): download(owned,second.prepared_answer)

@pytest.mark.parametrize('pages,exclude',[([5],[]),([],[1,2,3,4]),([0],[]),([-5],[])])
def test_invalid_or_empty_page_selection_never_advertises_pdf(owned,pages,exclude):
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')],
        outputs=[output(segments=[segment(pages=pages,exclude=exclude)])]))
    assert not result.evidence_sufficient and not result.prepared_answer

def test_model_selected_tools_bypass_retrieval_and_generation(owned,monkeypatch):
    import app.study_ai_v2 as generation
    raw=dict(resolved_query='PDF sayfasını döndür',operation='answer',scope='topic',count=None,
        difficulty=None,clarification='',retrieval_queries=['unused'],source_subjects=['unused'],
        source_kind='notes',depth='standard',needs_visual=False,continue_source=False,output_format='pdf',
        pdf_tools=tool(outputs=[output(segments=[segment(rotation=90)])]))
    request=parse_request(json.dumps(raw))
    assert request.retrieval_queries==() and request.source_subjects==()
    session,main,_=owned
    never=Mock(side_effect=AssertionError('No retrieval or generation for tools'))
    monkeypatch.setattr(generation,'get_provider',never)
    monkeypatch.setattr('app.academic_semantic_retrieval._fts_rows',never)
    result=retrieve_understood_course_context(session,understanding=UnderstandingResult(plan=request),
        message_model=main.StudyChatMessage,material_model=main.StudyMaterial,pdf_title='Perio',
        owner_user_id=1,course_id=6,query='PDF sayfasını döndür',recent_history=[])
    assert generation.ask_rag_v2('Perio','PDF sayfasını döndür',[],result).startswith(PREFIX)
    never.assert_not_called()


def test_anthropic_compact_tool_transport_retains_full_validation():
    from app.academic_request_understanding import SCHEMA, PlannerContractError
    from app.study_anthropic import _output_schema
    from copy import deepcopy
    original=deepcopy(SCHEMA)
    transport=_output_schema(SCHEMA)
    assert transport['properties']['pdf_tools']['type']=='string'
    assert 'segments' in transport['properties']['pdf_tools']['description']
    assert SCHEMA==original
    raw=dict(resolved_query='PDF böl',operation='answer',scope='topic',count=None,
        difficulty=None,clarification='',retrieval_queries=[],source_subjects=[],
        source_kind='notes',depth='standard',needs_visual=False,continue_source=False,output_format='pdf',
        pdf_tools=json.dumps(tool()))
    assert parse_request(json.dumps(raw)).pdf_tools==tool()
    for value in ['not JSON','[]',json.dumps({'action':'unsafe'})]:
        raw['pdf_tools']=value
        with pytest.raises(PlannerContractError):parse_request(json.dumps(raw))
    raw.update(pdf_tools='',retrieval_queries=['risk'],output_format='text')
    assert parse_request(json.dumps(raw)).pdf_tools is None

def test_unbounded_arbitrary_sources_and_paths_are_rejected():
    for mutate in [lambda x:x['sources'][0].update(kind='url',filename='https://bad.invalid'),
                   lambda x:x['outputs'][0]['segments'][0].update(source=-1),
                   lambda x:x['sources'][0].update(turn=True),
                   lambda x:x['outputs'][0].update(name='../private.pdf')]:
        value=tool(); mutate(value)
        with pytest.raises(PDFToolError): validate_tools(value)


def test_merge_uploaded_and_generated_pdfs(owned):
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf'),source()],
        outputs=[output(segments=[segment(pages=[4]),segment(index=1)])]))
    reader=PdfReader(BytesIO(download(owned,result.prepared_answer)))
    assert len(reader.pages)==2
    assert 'ORIGINAL PAGE 4' in reader.pages[0].extract_text()
    assert 'SOURCE TEXT' in reader.pages[1].extract_text()


def test_bad_pdf_returns_safe_error_without_artifact(owned):
    owned[2].write_bytes(b'private internal invalid document')
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')]))
    assert not result.evidence_sufficient and not result.prepared_answer
    assert 'private internal' not in result.clarification


def test_form_values_must_be_explicit_and_fields_must_exist(owned):
    value=tool(sources=[source('uploaded','original.pdf')],
        outputs=[output(fields=[{'name':'missing','value':'Cihan'}])])
    for query in ['PDF düzenle','Cihan yaz']:
        result=prepare(owned,value,query=query)
        assert not result.evidence_sufficient and not result.prepared_answer
    with pytest.raises(PDFToolError):
        validate_tools(tool('extract_text',outputs=[output(fields=[{'name':'a','value':'b'}])]))


def test_tools_end_read_transaction_before_file_io(owned,monkeypatch):
    import app.object_storage as storage
    original=storage.ensure_local
    def checked(path):
        assert not owned[0].in_transaction()
        return original(path)
    monkeypatch.setattr(storage,'ensure_local',checked)
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')]))
    assert result.evidence_sufficient
    assert download(owned,result.prepared_answer).startswith(b'%PDF-')


def test_busy_tool_does_no_file_work(owned,monkeypatch):
    import app.academic_pdf_tools as module
    gate=Mock(); gate.acquire.return_value=False
    monkeypatch.setattr(module,'_slots',gate)
    never=Mock(side_effect=AssertionError('capacity exceeded'))
    monkeypatch.setattr('app.object_storage.ensure_local',never)
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')]))
    assert not result.evidence_sufficient
    never.assert_not_called(); gate.release.assert_not_called()


def test_tool_recipe_is_not_a_long_prose_answer(owned):
    from app.academic_long_answer import automatic_pdf
    from app.study_retrieval_v2 import RetrievalResult
    assert not automatic_pdf('x'*20000,RetrievalResult(evidence_sufficient=True,
        study_task={'pdf_tool_validated':True}))


def test_download_parts_have_own_names_and_require_owner(owned,monkeypatch):
    from fastapi.testclient import TestClient
    session,main,_=owned
    result=prepare(owned,tool(sources=[source('uploaded','original.pdf')],outputs=[
        output('first.pdf',[segment(pages=[1])]),output('last.pdf',[segment(pages=[4])])]))
    session.add(main.User(id=1,username='owner',display_name='Owner',role='DOCTOR'))
    session.add(main.StudyCourse(id=6,owner_user_id=1,title='Perio'))
    session.add(main.StudyChatMessage(id=40,owner_user_id=1,course_id=6,
        role='ASSISTANT',mode='RAG_V2_PDF',content=result.prepared_answer))
    session.commit()
    monkeypatch.setattr(main,'engine',session.get_bind())
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    client=TestClient(main.app)
    url='/notes/courses/6/ai/messages/40/pdf'
    for part,name,page in [(0,'first.pdf',1),(1,'last.pdf',4)]:
        response=client.get(url+f'?part={part}')
        assert response.status_code==200
        assert name in response.headers['content-disposition']
        assert 'no-store' in response.headers['cache-control']
        assert f'ORIGINAL PAGE {page}' in PdfReader(BytesIO(response.content)).pages[0].extract_text()
    assert client.get(url+'?part=2').status_code==404
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=2,role='DOCTOR'))
    assert client.get(url).status_code==404
    monkeypatch.setattr(main,'get_current_user',lambda request:None)
    assert client.get(url).status_code==401


def test_persisted_split_links_survive_reload_and_escape_names():
    from pathlib import Path
    from jinja2 import Environment
    template=Path('app/templates/notes_ai.html').read_text()
    start=template.index("{% if msg.role == 'ASSISTANT' and msg.mode")
    block=template[start:template.index('{% endif %}',start)+len('{% endif %}')]
    files={40:[{'url':f'/notes/courses/6/ai/messages/40/pdf?part={part}',
        'name':'<script>unsafe</script>.pdf'} for part in range(2)]}
    html=Environment(autoescape=True).from_string(block).render(
        msg=SimpleNamespace(id=40,role='ASSISTANT',mode='RAG_V2_PDF'),
        course=SimpleNamespace(id=6,title='Perio'),pdf_files=files)
    assert html.count('class="study-pdf-file"')==2
    assert 'part=0' in html and 'part=1' in html
    assert '<script>' not in html and '&lt;script&gt;' in html


@pytest.mark.parametrize('stream',[True,False])
def test_request_saves_recipe_and_all_downloads_without_retrieval(owned,monkeypatch,stream):
    from fastapi.testclient import TestClient
    from app.academic_request_understanding import StudyRequest
    session,main,_=owned
    session.add(main.User(id=1,username='owner',display_name='Owner',role='DOCTOR'))
    session.add(main.StudyCourse(id=6,owner_user_id=1,title='Perio'))
    session.commit()
    monkeypatch.setattr(main,'engine',session.get_bind())
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    monkeypatch.setattr(main,'study_v2_streaming_enabled',lambda:True)
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**kw:True)
    monkeypatch.setattr(main,'classify_course_scope',lambda *a:'DENTAL')
    monkeypatch.setattr('app.academic_chunk_links.planner_source_outline',lambda *a,**kw:{})
    plan=StudyRequest(resolved_query='PDF iki parçaya böl',operation='answer',scope='topic',
        count=None,difficulty=None,clarification='',output_format='pdf',pdf_tools=tool(
            sources=[source('uploaded','original.pdf')],outputs=[
                output('First',[segment(pages=[1,2])]),output('Last',[segment(pages=[3,4])])]))
    def understand(*a,**kw):
        assert kw['source_outline']['pdf_files']==['original.pdf']
        return UnderstandingResult(plan=plan)
    monkeypatch.setattr('app.academic_request_understanding.understand_study_request',understand)
    never=Mock(side_effect=AssertionError('No search/provider for file operations'))
    monkeypatch.setattr('app.study_ai_v2.get_provider',never)
    monkeypatch.setattr('app.academic_semantic_retrieval.retrieve_semantic_context',never)
    client=TestClient(main.app)
    route='/notes/courses/6/ai/ask'+('-stream' if stream else '')
    response=client.post(route,data={'message':'PDF iki parçaya böl'})
    assert response.status_code==200,response.text
    data=[json.loads(line) for line in response.text.splitlines()][-1] if stream else response.json()
    assert len(data['artifact']['files'])==2
    for artifact in data['artifact']['files']:
        assert client.get(artifact['url']).content.startswith(b'%PDF-')
    assert 'ACADEMIC_PDF_TOOL_V1' not in response.text
    never.assert_not_called()

