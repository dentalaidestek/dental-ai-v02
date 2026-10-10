"""Exercise the production read helper with SQLite, without booting external services."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy import MetaData


def test_read_cursor_ownership_races_and_replay():
    source = (Path(__file__).resolve().parents[1] / 'app/main.py').read_text()
    tree = ast.parse(source)
    names = {'ConsultationCase', 'ConsultationMessage', 'ConsultationInboxState'}
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in names]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_socket_case_authorized']
    class IsolatedSQLModel(SQLModel):
        metadata = MetaData()
    utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    namespace = dict(SQLModel=IsolatedSQLModel, Field=Field, Optional=Optional, datetime=datetime,
                     Session=Session, select=select, _utcnow_naive=utcnow)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production read helper>', 'exec'), namespace)
    engine = create_engine('sqlite://')
    IsolatedSQLModel.metadata.create_all(engine)
    namespace['engine'] = engine
    Case, Message, State = (namespace[n] for n in ['ConsultationCase', 'ConsultationMessage', 'ConsultationInboxState'])
    def inbox(session, case_id, user_id):
        state = session.exec(select(State).where(State.case_id == case_id, State.user_id == user_id)).first()
        if state is None:
            state = State(case_id=case_id, user_id=user_id)
            session.add(state)
        return state
    namespace['_consultation_inbox_state'] = inbox
    namespace['_record_realtime_event'] = lambda *args: args[-1]
    read = namespace['_socket_case_authorized']
    now = utcnow()
    with Session(engine) as session:
        session.add(Case(id=1, requester_user_id=1, expert_user_id=2, specialty='Test', clinical_summary='', question='', expert_response_deadline=now))
        session.add(Case(id=2, requester_user_id=3, expert_user_id=4, specialty='Test', clinical_summary='', question='', expert_response_deadline=now))
        session.add(Message(id=1, case_id=1, sender_user_id=2, content='Seen', created_at=now))
        session.add(Message(id=2, case_id=1, sender_user_id=2, content='Arrived after cursor', created_at=now+timedelta(seconds=1)))
        session.add(Message(id=3, case_id=2, sender_user_id=4, content='Private', created_at=now+timedelta(seconds=2)))
        session.commit()
    assert read(3, 1, mark_read=True, through_id=1) is False
    assert read(1, 1, mark_read=True, through_id='invalid') is False
    first = read(1, 1, mark_read=True, through_id=1)
    assert first['through_id'] == 1 and first['at'] == now.isoformat()
    assert len(first['events']) == 2
    assert not read(1, 1, mark_read=True, through_id=1)['events']
    assert read(1, 1, mark_read=True, through_id=2)['through_id'] == 2
    assert not read(1, 1, mark_read=True, through_id=1)['events']
    # A foreign case's cursor cannot expose its content or advance beyond this case.
    assert read(1, 1, mark_read=True, through_id=3)['through_id'] == 2
    with Session(engine) as session:
        assert inbox(session, 1, 1).last_read_at == now+timedelta(seconds=1)
