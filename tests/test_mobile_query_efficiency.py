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
    assert len(queries) <= 5  # bounded page queries; no per-conversation SELECTs
    assert len(result['items']) == 50
    assert all(item['last_message'] == 'latest' for item in result['items'])
    assert all(item['other_user_id'] == peer.id for item in result['items'])
    queries.clear()
    assert len(mobile_api.mobile_consultations(outsider)['items']) == 1
    assert len(queries) <= 5  # bounded page queries; no per-conversation SELECTs


def test_consultation_inbox_uses_latest_restore_state_and_max_read_cursor(mobile_db):
    engine, (owner, peer, outsider), queries = mobile_db
    now = main._utcnow_naive()
    read_at = now + main.timedelta(seconds=2)
    with Session(engine) as session:
        restored = main.ConsultationCase(
            requester_user_id=peer.id, expert_user_id=owner.id, specialty='GENERAL',
            clinical_summary='Synthetic', question='Restored case',
            requested_at=now, status='REQUESTED',
            expert_response_deadline=now + main.timedelta(days=1),
        )
        hidden = main.ConsultationCase(
            requester_user_id=owner.id, expert_user_id=peer.id, specialty='GENERAL',
            clinical_summary='Synthetic', question='Deleted case',
            requested_at=now + main.timedelta(seconds=1),
            expert_response_deadline=now + main.timedelta(days=1),
        )
        other_account_state = main.ConsultationCase(
            requester_user_id=owner.id, expert_user_id=outsider.id, specialty='GENERAL',
            clinical_summary='Synthetic', question='Other account state',
            requested_at=now + main.timedelta(seconds=2),
            expert_response_deadline=now + main.timedelta(days=1),
        )
        session.add_all([restored, hidden, other_account_state])
        session.flush()
        # Historical duplicate rows: the oldest row is deleted, but the newest
        # row restores the conversation. Web canonical state keeps the maximum
        # read timestamp across duplicates and the newest lifecycle state.
        session.add_all([
            main.ConsultationInboxState(
                case_id=restored.id, user_id=owner.id, last_read_at=now,
                deleted_at=now, recover_until=now + main.timedelta(days=7),
            ),
            main.ConsultationInboxState(
                case_id=restored.id, user_id=owner.id, last_read_at=read_at,
            ),
            main.ConsultationInboxState(
                case_id=hidden.id, user_id=owner.id, deleted_at=now,
                recover_until=now + main.timedelta(days=7),
            ),
            # A peer's deleted inbox state must not hide this owner's case.
            main.ConsultationInboxState(
                case_id=other_account_state.id, user_id=outsider.id, deleted_at=now,
                recover_until=now + main.timedelta(days=7),
            ),
        ])
        session.add_all([
            main.ConsultationMessage(case_id=restored.id, sender_user_id=peer.id,
                                     content='Read before cursor', created_at=now),
            main.ConsultationMessage(case_id=restored.id, sender_user_id=peer.id,
                                     content='Read at cursor', created_at=read_at),
            main.ConsultationMessage(case_id=restored.id, sender_user_id=peer.id,
                                     content='Unread after cursor', created_at=read_at + main.timedelta(seconds=1)),
        ])
        session.commit()

    queries.clear()
    result = mobile_api.mobile_consultations(owner)
    by_id = {item['id']: item for item in result['items']}
    assert restored.id in by_id
    assert hidden.id not in by_id
    assert other_account_state.id in by_id
    assert by_id[restored.id]['unread_count'] == 1
    assert by_id[restored.id]['status_key'] == 'NEW_REQUEST'
    assert by_id[restored.id]['status_label'] == 'Yeni Talep'
    assert len(queries) <= 5


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
    assert mobile_api.mobile_consultations(owner) == {'items': [], 'next_before': None}
    assert len(queries) == 1
    queries.clear()
    assert mobile_api.mobile_academic_courses(owner) == {'items': [], 'next_before': None}
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


@pytest.mark.parametrize('kind', ['courses', 'cases', 'messages'])
def test_all_pages_accessible_without_duplicates_even_with_same_timestamps(mobile_db, kind):
    engine, (owner, peer, outsider), queries = mobile_db
    now = main._utcnow_naive()
    with Session(engine, expire_on_commit=False) as session:
        course = main.StudyCourse(owner_user_id=owner.id, title='History', created_at=now)
        session.add(course); session.commit()
        course_id = course.id
        rows = []
        for i in range(205):
            if kind == 'courses':
                row = main.StudyCourse(owner_user_id=owner.id, title=str(i), created_at=now)
            elif kind == 'cases':
                row = main.ConsultationCase(requester_user_id=owner.id, expert_user_id=peer.id, specialty='GENERAL', clinical_summary='Synthetic', question=str(i), requested_at=now, expert_response_deadline=now + main.timedelta(days=1))
            else:
                row = main.StudyChatMessage(owner_user_id=owner.id, course_id=course_id, role='ASSISTANT', content=str(i))
            session.add(row); rows.append(row)
        session.commit()
        expected = {row.id for row in rows}
        if kind == 'courses': expected.add(course_id)
    call = (lambda before: mobile_api.mobile_academic_courses(owner, before)) if kind == 'courses' else (lambda before: mobile_api.mobile_consultations(owner, before)) if kind == 'cases' else (lambda before: mobile_api.mobile_academic_messages(course_id, owner, before))
    seen = []; before = None
    for _ in range(10):
        queries.clear(); page = call(before)
        assert len(queries) <= (5 if kind == 'cases' else 2 if kind == 'courses' else 1)
        assert len(page['items']) <= (100 if kind == 'messages' else 50)
        seen.extend(item['id'] for item in page['items'])
        before = page['next_before']
        if before is None: break
    else: pytest.fail('Pagination did not terminate')
    assert len(seen) == len(set(seen))
    assert set(seen) == expected
    if kind == 'messages':
        assert mobile_api.mobile_academic_messages(course_id, outsider)['items'] == []
    else:
        foreign = mobile_api.mobile_academic_courses(outsider) if kind == 'courses' else mobile_api.mobile_consultations(outsider)
        assert foreign['items'] == []
        foreign_cursor = mobile_api.mobile_academic_courses(outsider, seen[0]) if kind == 'courses' else mobile_api.mobile_consultations(outsider, seen[0])
        assert foreign_cursor['items'] == []
