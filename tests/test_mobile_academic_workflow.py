from test_mobile_chat_actions import chat
from app import main
from sqlmodel import Session,select
import io,json
from PIL import Image


def course(engine,ident=1,owner=1):
    with Session(engine) as s:s.add(main.StudyCourse(id=ident,owner_user_id=owner,title='Synthetic course'));s.commit()


def test_native_academic_course_crud_and_ownership(chat):
    client,engine=chat
    result=client.post('/api/mobile/v1/academic/library',json={'title':'Synthetic new course','description':'Synthetic description'})
    assert result.status_code==200,result.text
    ident=result.json()['course']['id']
    assert client.put(f'/api/mobile/v1/academic/courses/{ident}',json={'title':'Renamed synthetic course'}).status_code==200
    assert client.get('/api/mobile/v1/academic/library?q=Renamed').json()['items'][0]['id']==ident
    client.headers['Authorization']='Bearer token2'
    assert client.get(f'/api/mobile/v1/academic/courses/{ident}/workspace').status_code==404
    assert client.delete(f'/api/mobile/v1/academic/courses/{ident}').status_code==404
    client.headers['Authorization']='Bearer token1'
    assert client.delete(f'/api/mobile/v1/academic/courses/{ident}').status_code==200


def test_native_study_run_is_durable_owned_and_reuses_request_key(chat,monkeypatch):
    from app import academic_study_runs
    client,engine=chat;course(engine)
    monkeypatch.setattr(main,'course_v2_ready',lambda *a,**kw:True)
    monkeypatch.setattr(academic_study_runs,'wake',lambda *a,**kw:None)
    values={'message':'Synthetic question','request_key':'synthetic-request-key-0001'}
    path='/api/mobile/v1/academic/courses/1/runs'
    first=client.post(path,json=values);assert first.status_code==202,first.text
    ident=first.json()['run']['id']
    assert client.post(path,json=values).json()['run']['id']==ident
    assert client.post(path,json={**values,'message':'Different question'}).status_code==409
    receipt=client.get(path+'/receipt',params={'request_key':values['request_key']});assert receipt.status_code==200 and receipt.json()['run']['id']==ident
    assert client.get(path+'/active').json()['run']['id']==ident
    client.headers['Authorization']='Bearer token2'
    assert client.get(path+f'/{ident}').status_code==404
    assert client.get(path+'/receipt',params={'request_key':values['request_key']}).status_code==404


def test_native_academic_upload_keeps_web_validation_and_durable_index_job(chat,monkeypatch):
    client,engine=chat;course(engine)
    monkeypatch.setattr(main,'_wake_academic_modal_indexer',lambda:True)
    monkeypatch.setattr(main,'storage_persist_file',lambda *a,**kw:None)
    raw=io.BytesIO();Image.new('RGB',(12,12),'white').save(raw,format='PNG')
    path='/api/mobile/v1/academic/courses/1/materials'
    assert client.post(path,files={'files':('invalid.pdf',b'not a PDF','application/pdf')}).status_code==400
    result=client.post(path,data={'original_filename':'Synthetic.png'},files={'files':('cache-random.png',raw.getvalue(),'image/png')});assert result.status_code==200,result.text
    data=client.get('/api/mobile/v1/academic/courses/1/workspace').json()
    assert data['max_file_bytes']==150*1024*1024 and data['materials'][0]['name']=='Synthetic.png'
    assert 'file_path' not in str(data)
    ident=data['materials'][0]['id'];assert client.get(path+f'/{ident}/file').status_code==200
    client.headers['Authorization']='Bearer token2';assert client.get(path+f'/{ident}/file').status_code==404
    assert client.delete(path+f'/{ident}').status_code==404


def test_native_quiz_keeps_key_hidden_until_first_choice_and_shows_grounded_explanation(chat):
    from app.academic_quiz import pack_evidence,render_quiz
    client,engine=chat;course(engine)
    question={'stem':'Synthetic ölçüm modeli için hangi seçenek geçerlidir?','options':['Alpha','Beta','Gamma','Delta','Epsilon'],'correct':'B','rationale':'Synthetic source explanation','fact':'Synthetic measurement fact','source':'Synthetic notes page 1','material_id':1,'page':1}
    quiz={'questions':[question]};content=render_quiz(quiz)
    with Session(engine) as s:
        versions=main._study_source_versions(s,1,1)
        s.add(main.StudyChatMessage(id=11,course_id=1,owner_user_id=1,role='ASSISTANT',content=content,source_evidence_json=pack_evidence('[]',quiz,content,versions)));s.commit()
    path='/api/mobile/v1/academic/courses/1'
    before=client.get(path+'/quizzes');assert before.status_code==200,before.text
    assert before.json()['quizzes'][0]['questions'][0]['result'] is None
    assert 'Synthetic source explanation' not in before.text and 'correct_choice' not in before.text
    answer=client.post(path+'/quizzes/11/answers',json={'number':1,'choice':'C'});assert answer.status_code==200,answer.text
    assert answer.json()['result']['correct'] is False and answer.json()['result']['correct_choice']=='B'
    after=client.get(path+'/quizzes').json()['quizzes'][0]['questions'][0]
    assert after['rationale']=='Synthetic source explanation'
    assert client.post(path+'/quizzes/11/answers',json={'number':1,'choice':'B'}).json()['result']['selected']=='C'
    timeline=client.get(path+'/timeline').json()['items'];assert timeline[0]['content']=='' and timeline[0]['quiz']
    client.headers['Authorization']='Bearer token2';assert client.get(path+'/quizzes').status_code==404


def test_native_academic_feedback_is_persisted_and_owner_scoped(chat):
    client,engine=chat;course(engine)
    with Session(engine) as s:s.add(main.StudyChatMessage(id=11,course_id=1,owner_user_id=1,role='ASSISTANT',content='Synthetic answer'));s.commit()
    path='/api/mobile/v1/academic/courses/1/messages/11/feedback'
    assert client.post(path,json={'vote':'like'}).status_code==200
    assert client.get('/api/mobile/v1/academic/courses/1/timeline').json()['items'][0]['vote']=='like'
    client.headers['Authorization']='Bearer token2';assert client.post(path,json={'vote':'dislike'}).status_code==404


def test_native_academic_learning_and_clear_preserve_web_ownership(chat):
    client,engine=chat;course(engine)
    with Session(engine) as s:s.add(main.StudyChatMessage(id=11,course_id=1,owner_user_id=1,role='ASSISTANT',content='Synthetic answer'));s.commit()
    path='/api/mobile/v1/academic/courses/1'
    response=client.get(path+'/learning');assert response.status_code==200 and 'practiced_facts' in response.json()['learning']
    assert response.headers['cache-control']=='private, no-store'
    client.headers['Authorization']='Bearer token2'
    assert client.delete(path+'/timeline').status_code==404
    assert client.get(path+'/learning').status_code==404
    assert client.get(path+'/materials/1/pages/1/text').status_code==404
    client.headers['Authorization']='Bearer token1'
    assert client.delete(path+'/timeline').status_code==200
    assert client.get(path+'/timeline').json()['items']==[]
