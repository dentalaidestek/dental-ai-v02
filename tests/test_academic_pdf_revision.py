"""Document edits preserve untouched bytes and use at most one patch-generation call."""
import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pypdf import PdfReader
from sqlmodel import Session
from test_study_pdf_download import pdf_client, _append_plan
from app.academic_pdf_revision import (target_span, apply_pdf_edits, generated_patch_content,
    prepare_pdf_revision, planner_pdf_outline)
from app.academic_request_understanding import UnderstandingResult, interpret_request, parse_request


BODY = '# Başlangıç\nKorunacak giriş.\n\n## Risk\nEski açıklama.\n\n### Alt başlık\nAlt bölüm.\n\n## Sonuç\nKorunacak sonuç.\n'


def edit(action='replace', target='Eski açıklama.', *, extent='match', source='literal', content='Yeni açıklama.', turns=None):
    return dict(action=action, target=target, extent=extent, source=source, content=content, turns=turns or [])


def plan(*edits, **kwargs):
    return replace(_append_plan(), append_previous_pdf=False, pdf_edits=tuple(edits), **kwargs)


def state(*edits, body=BODY):
    prepared=[]
    for i, e in enumerate(edits):
        start,end=target_span(body,e)
        prepared.append({**e,'id':i,'start':start,'end':end,'original':body[start:end]})
    return {'body':body,'edits':prepared}


@pytest.mark.parametrize('action,target,expected',[
    ('replace','Eski açıklama.',BODY.replace('Eski açıklama.','Yeni açıklama.')),
    ('delete','Eski açıklama.',BODY.replace('Eski açıklama.','')),
    ('insert_before','## Risk',BODY.replace('## Risk','\n\nYeni açıklama.\n\n## Risk')),
    ('insert_after','Eski açıklama.',BODY.replace('Eski açıklama.','Eski açıklama.\n\nYeni açıklama.\n\n')),
    ('append','',BODY+'\n\nYeni açıklama.'),
    ('prepend','','Yeni açıklama.\n\n'+BODY),
])
def test_every_position_preserves_other_text(action,target,expected):
    e=edit(action,target,source='none' if action=='delete' else 'literal',content='' if action=='delete' else 'Yeni açıklama.')
    assert apply_pdf_edits(state(e))==expected


def test_section_replacement_includes_children_but_preserves_next_section():
    e=edit(target='## Risk',extent='section',content='## Risk\nYeni risk bölümü.\n\n')
    result=apply_pdf_edits(state(e))
    assert result=='# Başlangıç\nKorunacak giriş.\n\n## Risk\nYeni risk bölümü.\n\n## Sonuç\nKorunacak sonuç.\n'


def test_table_cell_replacement_keeps_all_other_rows_and_columns():
    body='## Tablo\n| Risk | Düzey |\n| --- | --- |\n| Diyabet | düşük |\n| Sigara | yüksek |\n\n## Son\nBitiş.'
    result=apply_pdf_edits(state(edit(target='| Diyabet | düşük |',content='| Diyabet | orta |'),body=body))
    assert result==body.replace('| Diyabet | düşük |','| Diyabet | orta |')
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(__import__('app.academic_pdf',fromlist=['render_pdf']).render_pdf('Not',result))).pages)
    assert 'Diyabet' in text and 'orta' in text and 'Sigara' in text and 'Bitiş' in text


@pytest.mark.parametrize('target',['Eksik başlık','a'])
def test_missing_or_ambiguous_target_does_not_guess(target):
    with pytest.raises(ValueError):target_span(BODY,edit(target=target))


def test_multiple_changes_use_original_offsets():
    result=apply_pdf_edits(state(edit(target='Eski açıklama.',content='Kısa.'),
        edit(target='Korunacak sonuç.',content='Düzenlenmiş sonuç.')))
    assert result==BODY.replace('Eski açıklama.','Kısa.').replace('Korunacak sonuç.','Düzenlenmiş sonuç.')


@pytest.mark.parametrize('patches',[
    [], [{'id':0,'content':'Yeni','supported':False}],
    [{'id':0,'content':'Yeni','supported':True},{'id':0,'content':'İkinci','supported':True}],
    [{'id':1,'content':'Yanlış hedef','supported':True}],
    [{'id':True,'content':'Yanlış tür','supported':True}],
])
def test_generated_patch_must_cover_exact_supported_targets(patches):
    with pytest.raises(ValueError):
        generated_patch_content(json.dumps({'patches':patches}),state(edit(source='generate',content='')))


def test_pdf_outline_is_owned_and_latest(pdf_client):
    main,_=pdf_client
    with Session(main.engine) as session:
        assert planner_pdf_outline(session,main.StudyChatMessage,1,1,{})['editable_pdf']['content']=='Pronasale: Burun ucu.'
        assert 'editable_pdf' not in planner_pdf_outline(session,main.StudyChatMessage,2,1,{})


def test_concurrent_new_pdf_does_not_receive_an_edit_for_old_snapshot(pdf_client):
    main,_=pdf_client
    with Session(main.engine) as session:
        snapshot=planner_pdf_outline(session,main.StudyChatMessage,1,1,{})['editable_pdf']['revision']
        session.add(main.StudyChatMessage(id=5,owner_user_id=1,course_id=1,role='ASSISTANT',
            mode='RAG_V2_HYBRID_STREAM_PDF',content='Pronasale: Burun ucu. Yeni bölüm.'))
        session.commit()
        result=prepare_pdf_revision(session,message_model=main.StudyChatMessage,
            plan=plan(edit(target='Burun ucu.',content='Yeni')),owner_user_id=1,course_id=1,
            history=[],query='Yeni',snapshot=snapshot)
        assert not result.prepared_answer and not result.evidence_sufficient
        assert 'güncellenmiş' in result.clarification


@pytest.mark.parametrize('problem',['foreign_base','foreign_chat','overlap','literal_not_in_request','empty_pdf'])
def test_invalid_edit_keeps_original_pdf(pdf_client,problem):
    main,_=pdf_client
    edits=[edit(target='Pronasale: Burun ucu.',content='Yeni')]
    history=[]
    kwargs={}
    if problem=='foreign_base':
        history=[{'id':2,'role':'ASSISTANT','mode':'RAG_V2_HYBRID_STREAM_PDF'}]
        kwargs['pdf_base_turn']=0
    elif problem=='foreign_chat':
        edits=[edit(target='Pronasale: Burun ucu.',source='chat',content='',turns=[0])]
        history=[{'id':2,'role':'ASSISTANT','mode':'RAG_V2_HYBRID_STREAM'}]
    elif problem=='overlap':
        edits.append(edit(target='Burun ucu.',content='Yeni'))
    elif problem=='empty_pdf':
        edits=[edit('delete','Pronasale: Burun ucu.',source='none',content='')]
    with Session(main.engine) as session:
        result=prepare_pdf_revision(session,message_model=main.StudyChatMessage,plan=plan(*edits,**kwargs),
            owner_user_id=1,course_id=1,history=history,query='farklı' if problem=='literal_not_in_request' else 'Yeni')
        assert result.clarification and not result.evidence_sufficient and not result.prepared_answer
        assert session.get(main.StudyChatMessage,1).content=='Pronasale: Burun ucu.'


def test_existing_chat_table_can_be_inserted_before_a_section(pdf_client):
    main,_=pdf_client
    with Session(main.engine) as session:
        base=session.get(main.StudyChatMessage,1);base.content=BODY;session.add(base)
        session.add(main.StudyChatMessage(id=5,owner_user_id=1,course_id=1,role='ASSISTANT',
            mode='RAG_V2_HYBRID_STREAM',content='| Risk | Not |\n| --- | --- |\n| Sigara | Açıklama |'))
        session.commit()
        result=prepare_pdf_revision(session,message_model=main.StudyChatMessage,
            plan=plan(edit('insert_before','## Sonuç',source='chat',content='',turns=[0])),
            owner_user_id=1,course_id=1,history=[{'id':5,'role':'ASSISTANT'}],query='Tabloyu sonuçtan önce ekle')
        assert result.prepared_answer.index('| Sigara |')<result.prepared_answer.index('## Sonuç')
        assert 'Eski açıklama.' in result.prepared_answer and 'Korunacak sonuç.' in result.prepared_answer


def test_generation_edits_only_target_with_one_structured_call(monkeypatch):
    from app.study_retrieval_v2 import RetrievalResult
    from app.study_ai_v2 import ask_rag_v2
    e=edit(source='generate',content='')
    provider=Mock(last_finish_reason='STOP')
    provider.generate_stream.return_value=iter([json.dumps({'patches':[{'id':0,'content':'Kaynağa dayalı yeni açıklama. [Not s. 1]','supported':True}]})])
    target=SimpleNamespace(provider='anthropic',model='test')
    monkeypatch.setattr('app.study_ai_v2._generation_targets',lambda:[target])
    monkeypatch.setattr('app.study_ai_v2.get_provider',lambda name:provider)
    monkeypatch.setattr('app.study_ai_v2.target_available',lambda target:True)
    monkeypatch.setattr('app.study_ai_v2.report_target_success',lambda target:None)
    retrieval=RetrievalResult(note_context=['Kaynağa dayalı açıklama, Not s. 1'],evidence_sufficient=True,
        pdf_revision=state(e),study_task={'operation':'answer','scope':'topic','retrieval_queries':['risk']})
    result=ask_rag_v2('Perio','Risk açıklamasını ayrıntılandır',[],retrieval)
    assert result==BODY.replace('Eski açıklama.','Kaynağa dayalı yeni açıklama. [Not s. 1]').strip()
    assert retrieval.study_task['pdf_revision_applied']
    provider.generate_stream.assert_called_once()
    assert provider.generate_stream.call_args.kwargs['response_schema']['properties']['patches']
    assert 'Korunacak sonuç.' not in provider.generate_stream.call_args.kwargs['prompt']


@pytest.mark.parametrize('finish,supported',[('MAX_TOKENS',True),('STOP',False)])
def test_failed_generation_never_emits_partial_revision(monkeypatch,finish,supported):
    from app.study_retrieval_v2 import RetrievalResult
    from app.study_ai_v2 import stream_rag_v2,StudyAIError
    provider=Mock(last_finish_reason=finish)
    provider.generate_stream.return_value=iter([json.dumps({'patches':[{'id':0,'content':'Yarım','supported':supported}]})])
    target=SimpleNamespace(provider='anthropic',model='test')
    monkeypatch.setattr('app.study_ai_v2._generation_targets',lambda:[target])
    monkeypatch.setattr('app.study_ai_v2.get_provider',lambda name:provider)
    monkeypatch.setattr('app.study_ai_v2.target_available',lambda target:True)
    monkeypatch.setattr('app.study_ai_v2.report_target_success',lambda target:None)
    retrieval=RetrievalResult(note_context=['Kaynak'],evidence_sufficient=True,
        pdf_revision=state(edit(source='generate',content='')),study_task={'operation':'answer'})
    iterator=stream_rag_v2('Perio','Güncelle',[],retrieval)
    with pytest.raises(StudyAIError):next(iterator)
    assert not retrieval.study_task.get('pdf_revision_applied')


def test_planner_gets_document_once_and_explicit_edit_contract():
    from app.academic_request_understanding import SYSTEM
    p=plan(edit())
    from dataclasses import asdict
    raw=asdict(p)
    for key in ['retrieval_queries','source_sections','source_files','source_pages','source_subjects','exam_topics','quiz_answers','pdf_edits','pdf_addition_turns']:
        raw[key]=list(raw[key])
    call=Mock(return_value=json.dumps(raw))
    result=interpret_request('Eski açıklama yerine Yeni açıklama. yaz',
        [{'role':'ASSISTANT','mode':'RAG_V2_HYBRID_PDF','content':BODY}],call=call,
        source_outline={'editable_pdf':{'content':BODY}})
    assert result.plan.pdf_edits and call.call_args.args[0].count('Korunacak sonuç.')==1
    assert 'insert_before' in SYSTEM and 'source=generate' in SYSTEM


@pytest.mark.parametrize('bad',[
    edit(action='unknown'), edit(target=''), edit(source='none'),
    edit(source='generate',content='Uydurma plan içeriği'), edit(turns=[8]),
])
def test_bad_edit_schema_is_rejected(bad):
    from dataclasses import asdict
    with pytest.raises(ValueError):parse_request(json.dumps(asdict(plan(bad))))


@pytest.mark.parametrize('stream',[True,False])
@pytest.mark.parametrize('action',['replace','delete','insert_before'])
def test_edit_routes_save_owned_revision_and_preserve_original(pdf_client,monkeypatch,stream,action):
    from sqlmodel import select
    main,client=pdf_client
    with Session(main.engine) as session:
        session.add(main.StudyMaterial(course_id=1,owner_user_id=1,original_filename='note.pdf',
            display_name='Not',stored_filename='note.pdf',file_path='unused',material_type='PDF',
            mime_type='application/pdf',size_bytes=10))
        base=session.get(main.StudyChatMessage,1);base.content=BODY;session.add(base);session.commit()
    monkeypatch.setattr(main,'study_v2_streaming_enabled',lambda:True)
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**kw:True)
    monkeypatch.setattr(main,'classify_course_scope',lambda *a:'DENTAL')
    monkeypatch.setattr('app.academic_chunk_links.planner_source_outline',lambda *a,**kw:{})
    e=edit(action,'Eski açıklama.',source='none' if action=='delete' else 'literal',
        content='' if action=='delete' else 'Yeni açıklama.')
    monkeypatch.setattr('app.academic_request_understanding.understand_study_request',
        lambda *a,**kw:UnderstandingResult(plan=plan(e)))
    path='/notes/courses/1/ai/ask-stream' if stream else '/notes/courses/1/ai/ask'
    response=client.post(path,data={'message':'PDF: Yeni açıklama.'})
    assert response.status_code==200
    data=[json.loads(line) for line in response.text.splitlines()][-1] if stream else response.json()
    assert data['artifact']['reason']=='updated'
    with Session(main.engine) as session:
        saved=session.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.id>4,
            main.StudyChatMessage.role=='ASSISTANT')).one()
        assert saved.content==apply_pdf_edits(state(e)).strip()
        assert saved.mode.endswith('_EDITED_PDF')
        assert session.get(main.StudyChatMessage,1).content==BODY
    pdf=client.get(data['artifact']['url'])
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert 'Korunacak giriş.' in text and 'Korunacak sonuç.' in text
    assert client.get('/notes/courses/2'+data['artifact']['url'].split('/courses/1')[1]).status_code==404
