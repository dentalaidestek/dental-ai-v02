"""Saved voice history labels depend on owned completed audit jobs, not DRAFT status."""
import html
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app import main
from app.work_jobs import WorkJob


@pytest.fixture
def history_client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'voice-history.db'),
                           connect_args={'check_same_thread': False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setenv('R2_ENABLED', '0')
    with Session(engine) as session:
        for ident, role in ((1, 'DOCTOR'), (2, 'DOCTOR'), (3, 'ADMIN')):
            session.add(main.User(id=ident, username='history' + str(ident), role=role,
                                  display_name='Synthetic member',
                                  email=main.ADMIN_FIXED_EMAIL if role == 'ADMIN' else None,
                                  email_verified_at=main._utcnow_naive()))
            token = main.hash_session_token('history' + str(ident))
            session.add(main.SessionToken(user_id=ident, token_hash=token,
                                         expires_at=main._utcnow_naive() + timedelta(days=1)))
            if role == 'ADMIN':
                session.add(main.AdminVerifiedSession(user_id=ident, token_hash=token))
        for ident, owner in ((1, 1), (2, 2), (3, None)):
            session.add(main.Patient(id=ident, owner_user_id=owner,
                                     anonymous_id='SYNTHETIC-' + str(ident)))
        for ident, patient, status in ((1, 1, 'DRAFT'), (2, 1, 'DRAFT'),
                                       (3, 1, 'FAILED'), (4, 1, 'AI_ANALYZED'),
                                       (5, 1, 'DRAFT'), (6, 1, 'DRAFT'),
                                       (7, 1, 'DRAFT'), (8, 1, 'DRAFT'),
                                       (9, 2, 'DRAFT'), (10, 1, 'DRAFT'),
                                       (11, 3, 'DRAFT')):
            session.add(main.Analysis(id=ident, patient_id=patient, status=status))
        jobs = [
            (1, 1, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
            (1, 1, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
            (5, 2, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
            (5, 3, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
            (6, 1, 'FINAL', 'ANALYSIS', 'DONE'),
            (7, 1, 'VOICE_REVIEW', 'ANALYSIS', 'QUEUED'),
            (8, 1, 'VOICE_REVIEW', 'GUEST', 'DONE'),
            (9, 2, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
            (10, 1, 'VOICE_REVIEW', 'ANALYSIS', 'FAILED'),
            (11, 3, 'VOICE_REVIEW', 'ANALYSIS', 'DONE'),
        ]
        for index, (resource, owner, kind, resource_type, status) in enumerate(jobs):
            session.add(WorkJob(resource_id=resource, owner_user_id=owner, kind=kind,
                                resource_type=resource_type, status=status,
                                source_hash='synthetic', dedupe_key='history-' + str(index)))
        session.commit()
    client = TestClient(main.app)  # No application lifespan or background workers.
    client.cookies.set(main.SESSION_COOKIE, 'history1')
    yield client, engine
    client.close()
    engine.dispose()


def plain_text(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', value)).split())


def history_rows(page):
    return {int(ident): plain_text(body) for body, ident in re.findall(
        r'<div class="patient-history-row analysis-history-item">(.*?)'
        r'<button[^>]+onclick="openAnalysisModal\((\d+)\)"', page, re.S)}


def test_saved_voice_row_and_modal_are_saved_while_imaging_statuses_are_preserved(history_client):
    client, engine = history_client
    response = client.get('/patients/1')
    assert response.status_code == 200
    rows = history_rows(response.text)
    assert 'Sesli muayene #1' in rows[1] and 'Kaydedildi' in rows[1]
    assert 'Diş' not in rows[1] and 'Yarım kaldı' not in rows[1]
    assert 'Analiz #2' in rows[2] and 'Yarım kaldı' in rows[2] and 'Diş -' in rows[2]
    assert 'Başarısız' in rows[3] and 'Başarılı' in rows[4]
    modal = response.text.split('id="analysisModal-1"', 1)[1].split('<h3>', 1)[0]
    assert 'Sesli muayene #1' in plain_text(modal) and 'Kaydedildi' in plain_text(modal)
    assert 'Diş:' not in plain_text(modal)
    with Session(engine) as session:
        assert session.get(main.Analysis, 1).status == 'DRAFT'


def test_job_lookup_is_single_distinct_and_excludes_wrong_owner_kind_type_and_pending(history_client):
    client, engine = history_client
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if 'workjob' in statement.casefold():
            statements.append(statement)

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        response = client.get('/patients/1')
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert response.context.get('voice_review_ids') == {1}
    assert len(statements) == 1 and 'select distinct' in statements[0].casefold()
    rows = history_rows(response.text)
    for ident in (5, 6, 7, 8, 10):
        assert 'Analiz #' + str(ident) in rows[ident] and 'Yarım kaldı' in rows[ident]
    assert 9 not in rows


def test_owner_isolation_and_admin_uses_patient_owner_then_viewer_fallback(history_client):
    client, _ = history_client
    client.cookies.set(main.SESSION_COOKIE, 'history2')
    assert client.get('/patients/1').status_code == 403
    response = client.get('/patients/2')
    assert response.context.get('voice_review_ids') == {9}
    assert 'Sesli muayene #9' in history_rows(response.text)[9]
    client.cookies.set(main.SESSION_COOKIE, 'history3')
    assert client.get('/patients/1').context.get('voice_review_ids') == {1}
    response = client.get('/patients/3')
    assert response.context.get('voice_review_ids') == {11}
    assert 'Sesli muayene #11' in history_rows(response.text)[11]


def test_save_return_banner_confirms_selected_information_without_patient_content(history_client):
    client, _ = history_client
    response = client.get('/patients/1?voice_saved=1')
    banner = re.search(r'<div[^>]+role="status"[^>]*>(.*?)</div>', response.text, re.S)
    assert banner and '<strong>Kaydedildi</strong>' in banner[1]
    assert 'Seçip onayladığınız sesli muayene bilgileri hasta dosyasına kaydedildi.' in plain_text(banner[1])
    assert 'SYNTHETIC-' not in banner[1] and '<img' not in banner[1]
    assert not re.search(r'<div[^>]+class="[^"]*\bpatient-voice-saved\b', client.get('/patients/1').text)
