"""Durable visible-read fallback exercises actual production helpers and route."""
import ast
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI, Request, BackgroundTasks, Form
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import MetaData
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Field, Session, create_engine, select


@pytest.fixture
def read_client(monkeypatch):
    monkeypatch.setenv('WEB_ALLOWED_ORIGINS','https://dentalai.tr')
    tree=ast.parse(Path('app/main.py').read_text())
    classes={'ConsultationCase','ConsultationMessage','ConsultationInboxState'}
    functions={'_socket_origin_allowed','_socket_case_authorized','consultation_mark_read'}
    nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in classes
           or isinstance(n,ast.FunctionDef) and n.name in functions]
    class Model(SQLModel):
        metadata=MetaData()
    app=FastAPI();published=[]
    async def publish(event):published.append(event)
    scope=dict(SQLModel=Model,Field=Field,Optional=Optional,datetime=datetime,Session=Session,
        select=select,Request=Request,BackgroundTasks=BackgroundTasks,Form=Form,JSONResponse=JSONResponse,
        app=app,offload=lambda f:f,os=os,urlparse=urlparse,
        _utcnow_naive=lambda:datetime.now(timezone.utc).replace(tzinfo=None),
        _record_realtime_event=lambda *args:args[-1],_publish_realtime_event=publish,
        get_current_user=lambda request:SimpleNamespace(id=int(request.headers['x-user'])) if request.headers.get('x-user') else None)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<production read route>','exec'),scope)
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    Model.metadata.create_all(engine);scope['engine']=engine
    Case,Message,State=(scope[n] for n in ['ConsultationCase','ConsultationMessage','ConsultationInboxState'])
    def inbox(session,case_id,user_id):
        state=session.exec(select(State).where(State.case_id==case_id,State.user_id==user_id)).first()
        if state is None:state=State(case_id=case_id,user_id=user_id);session.add(state)
        return state
    scope['_consultation_inbox_state']=inbox
    now=datetime(2026,10,18,7,0)
    with Session(engine) as session:
        session.add(Case(id=19,requester_user_id=1,expert_user_id=2,specialty='Test',
            clinical_summary='',question='',expert_response_deadline=now))
        session.add(Message(id=128,case_id=19,sender_user_id=2,message_type='IMAGE',created_at=now))
        session.add(Message(id=129,case_id=19,sender_user_id=2,created_at=now+timedelta(seconds=1)))
        session.commit()
    return TestClient(app),scope,published,now


def test_visible_image_read_is_saved_without_a_socket_and_is_idempotent(read_client):
    client,scope,published,now=read_client
    headers={'x-user':'1','origin':'https://dentalai.tr'}
    response=client.post('/expert-support/cases/19/read',data={'through_id':128},headers=headers)
    assert response.status_code==200 and response.json()['through_id']==128
    assert len(published)==2
    with Session(scope['engine']) as session:
        assert scope['_consultation_inbox_state'](session,19,1).last_read_at==now
        Message=scope['ConsultationMessage']
        remaining=session.exec(select(Message).where(Message.case_id==19,Message.created_at>now)).all()
        assert [message.id for message in remaining]==[129]
    assert client.post('/expert-support/cases/19/read',data={'through_id':128},headers=headers).status_code==200
    assert len(published)==2
    assert client.post('/expert-support/cases/19/read',data={'through_id':129},headers=headers).status_code==200
    assert len(published)==4


@pytest.mark.parametrize('headers,through,status',[
    ({'origin':'https://dentalai.tr'},128,401),
    ({'x-user':'3','origin':'https://dentalai.tr'},128,403),
    ({'x-user':'1','origin':'https://evil.invalid'},128,403),
    ({'x-user':'1'},128,403),
    ({'x-user':'1','origin':'https://dentalai.tr'},-1,403),
    ({'x-user':'1','origin':'https://dentalai.tr'},'invalid',422),
])
def test_read_fallback_keeps_authorization_origin_and_cursor_boundaries(read_client,headers,through,status):
    client,scope,published,_=read_client
    assert client.post('/expert-support/cases/19/read',data={'through_id':through},headers=headers).status_code==status
    assert not published
    with Session(scope['engine']) as session:
        State=scope['ConsultationInboxState']
        assert not session.exec(select(State)).all()
