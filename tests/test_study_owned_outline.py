from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine


def test_source_outline_inspection_is_owned_and_opt_in(tmp_path,monkeypatch):
    from app import main
    from app import academic_chunk_links
    from app.academic_direct_request import source_marker
    engine=create_engine('sqlite:///'+str(tmp_path/'outline.db'),connect_args={'check_same_thread':False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'get_current_user',lambda request:SimpleNamespace(id=1,role='DOCTOR'))
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**kw:True)
    calls=[]
    def outline(session,**kw):
        calls.append(kw)
        assert kw['owner_user_id']==1 and kw['course_id']==1
        return {'sections':['Deri Noktaları > Tek Noktalar'],'complete':True}
    monkeypatch.setattr(academic_chunk_links,'planner_source_outline',outline)
    task=dict(scope='topic',operation='explain',retrieval_queries=['deri tek noktalar'],
              resolved_query='Deri tek noktalarını açıkla',source_kind='notes')
    with Session(engine) as session:
        session.add(main.User(id=1,username='own',display_name='Synthetic',role='DOCTOR'))
        session.add(main.User(id=2,username='other',display_name='Other',role='DOCTOR'))
        session.add(main.StudyCourse(id=1,owner_user_id=1,title='Orto'))
        session.add(main.StudyCourse(id=2,owner_user_id=2,title='Other'))
        session.add(main.StudyMaterial(id=1,owner_user_id=1,course_id=1,original_filename='note.pdf',
            stored_filename='note.pdf',display_name='Note',file_path='private.pdf',material_type='PDF',
            mime_type='application/pdf',size_bytes=1,index_status='READY',active_index_version='v1'))
        session.add(main.StudyChatMessage(owner_user_id=1,course_id=1,role='ASSISTANT',
            content='Answer\n'+source_marker(task)))
        session.commit()
    client=TestClient(main.app)
    assert client.get('/notes/courses/2/ai/index-status?outline=1').status_code==404
    assert not calls
    normal=client.get('/notes/courses/1/ai/index-status').json()
    assert 'outline' not in normal and 'last_source_request' not in normal
    assert normal['completed']==normal['total']==1
    data=client.get('/notes/courses/1/ai/index-status?outline=1').json()
    assert data['outline']['sections']==['Deri Noktaları > Tek Noktalar']
    assert data['last_source_request']==task
    assert len(calls)==1
