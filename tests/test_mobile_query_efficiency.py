import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from app import main, mobile_api


@pytest.fixture
def mobile_db(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'mobile.db'))
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(mobile_api, 'engine', engine)
    with Session(engine, expire_on_commit=False) as session:
        users = [main.User(username=name, display_name=name, role='DOCTOR', is_active=True) for name in ('owner', 'peer', 'outsider')]
        session.add_all(users); session.commit()
    queries = []
    event.listen(engine, 'before_cursor_execute', lambda conn, cursor, statement, params, context, many: queries.append(statement) if statement.lstrip().upper().startswith('SELECT') else None)
    yield engine, users, queries
    engine.dispose()


def test_fifty_cases_use_three_queries_and_keep_owner_scope(mobile_db):
    engine, (owner, peer, outsider), queries = mobile_db
    now = main._utcnow_naive()
    with Session(engine) as session:
        for i in range(51):
            case = main.ConsultationCase(requester_user_id=owner.id if i < 50 else outsider.id, expert_user_id=peer.id, specialty='GENERAL', clinical_summary='Synthetic', question='Synthetic', expert_response_deadline=now + main.timedelta(days=1))
            session.add(case); session.flush()
            session.add_all([main.ConsultationMessage(case_id=case.id, sender_user_id=peer.id, content=text, created_at=now) for text in ('old', 'latest')])
        session.commit()
    queries.clear()
    result = mobile_api.mobile_consultations(owner)
    assert len(queries) == 3
    assert len(result['items']) == 50
    assert all(item['last_message'] == 'latest' for item in result['items'])
    assert all(item['other_user_id'] == peer.id for item in result['items'])
    queries.clear()
    assert len(mobile_api.mobile_consultations(outsider)['items']) == 1
    assert len(queries) == 3


def test_course_counts_are_batched_and_exclude_other_owners(mobile_db):
    engine, (owner, _, outsider), queries = mobile_db
    with Session(engine) as session:
        for i in range(6):
            course = main.StudyCourse(owner_user_id=owner.id if i < 5 else outsider.id, title='Synthetic')
            session.add(course); session.flush()
            for j in range(3):
                session.add(main.StudyMaterial(owner_user_id=owner.id if i < 5 and j < 2 else outsider.id, course_id=course.id, original_filename='synthetic.pdf', display_name='Synthetic', stored_filename=f'{i}-{j}.pdf', file_path='/synthetic', material_type='PDF', mime_type='application/pdf', size_bytes=1))
        session.commit()
    queries.clear()
    result = mobile_api.mobile_academic_courses(owner)
    assert len(queries) == 2
    assert len(result['items']) == 5
    assert all(item['material_count'] == 2 for item in result['items'])


def test_empty_lists_do_not_run_secondary_queries(mobile_db):
    _, (owner, _, _), queries = mobile_db
    queries.clear()
    assert mobile_api.mobile_consultations(owner) == {'items': []}
    assert len(queries) == 1
    queries.clear()
    assert mobile_api.mobile_academic_courses(owner) == {'items': []}
    assert len(queries) == 1


def test_academic_history_keeps_latest_answers_in_display_order(mobile_db):
    engine, (owner, _, outsider), queries = mobile_db
    with Session(engine, expire_on_commit=False) as session:
        course = main.StudyCourse(owner_user_id=owner.id, title='Synthetic')
        session.add(course); session.commit()
        course_id = course.id
        for i in range(105):
            session.add(main.StudyChatMessage(owner_user_id=owner.id, course_id=course_id, role='ASSISTANT', content=f'answer-{i}'))
        session.add(main.StudyChatMessage(owner_user_id=outsider.id, course_id=course_id, role='ASSISTANT', content='other-user-answer'))
        session.commit()
    queries.clear()
    items = mobile_api.mobile_academic_messages(course_id, owner)['items']
    assert len(queries) == 1
    assert len(items) == 100
    assert items[0]['content'] == 'answer-5'
    assert items[-1]['content'] == 'answer-104'
    assert [item['id'] for item in items] == sorted(item['id'] for item in items)
    assert not any(item['content'] == 'other-user-answer' for item in items)
    with Session(engine) as session:
        from sqlmodel import select
        assert len(session.exec(select(main.StudyChatMessage).where(main.StudyChatMessage.owner_user_id == owner.id)).all()) == 105
