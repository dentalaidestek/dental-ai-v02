from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from app import main


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    now = datetime(2026, 10, 10, 9)
    monkeypatch.setattr(main, '_utcnow_naive', lambda: now)
    monkeypatch.setattr(main, 'on_loop', lambda *args, **kwargs: None)
    with Session(engine, expire_on_commit=False) as s:
        users = [main.User(username=n, role=role, display_name=n) for n, role in [('requester','DOCTOR'),('expert','DOCTOR'),('admin','ADMIN'),('outsider','DOCTOR')]]
        s.add_all(users); s.commit()
        users = {u.username: u for u in users}
    monkeypatch.setattr(main, 'get_current_user', lambda request: users.get(request.headers.get('x-user', 'requester')))
    return engine, now, users, TestClient(main.app)


def add_case(setup, status='COMPLETED', completed_days=0):
    engine, now, users, _ = setup
    with Session(engine, expire_on_commit=False) as s:
        case = main.ConsultationCase(requester_user_id=users['requester'].id, expert_user_id=users['expert'].id, specialty='Endodonti', clinical_summary='Özet', question='Soru', status=status, expert_response_deadline=now+timedelta(minutes=10), completed_at=now-timedelta(days=completed_days) if status=='COMPLETED' else None)
        s.add(case); s.flush()
        message=main.ConsultationMessage(case_id=case.id,sender_user_id=users['requester'].id,content='Private message')
        s.add(message);s.flush()
        main._record_message_realtime_events(s,case,message,users['requester'])
        main._enqueue_chat_retention(s,case);s.commit()
        return case.id


def test_today_and_dashboard_expand_same_weekly_occurrence(setup):
    engine, _, users, _ = setup
    start=main._date_to_local_start(date(2026,10,10));end=main._date_to_local_end(date(2026,10,10))
    with Session(engine) as s:
        # Old weekly anchor on a different day must never show up today.
        s.add_all([main.ScheduleEvent(owner_user_id=users['requester'].id,event_type='CLASS',title='Today weekly',start_at=main._local_to_utc('2026-10-03T23:00'),recurrence_rule='WEEKLY'),main.ScheduleEvent(owner_user_id=users['requester'].id,event_type='CLASS',title='Tomorrow weekly',start_at=main._local_to_utc('2026-10-04T23:00'),recurrence_rule='WEEKLY')]);s.commit()
        occurrences=main._user_schedule_occurrences(s,users['requester'].id,start,end)
        dashboard=main._dashboard_next_schedule_occurrence(s,users['requester'].id,start,end)
        assert [o['title'] for o in occurrences]==['Today weekly']
        assert dashboard['id']==occurrences[0]['id']
        assert dashboard['start_local']==occurrences[0]['start_local']


def test_waiting_confirmation_and_dispute_release_capacity(setup):
    for status in ['ACTIVE','WAITING_START','EXPERT_COMPLETED','DISPUTE','COMPLETED']:
        add_case(setup,status)
    with Session(setup[0]) as s:
        assert main._expert_open_case_count(s,setup[2]['expert'].id)==2


@pytest.mark.parametrize('days,status',[ (2,'COMPLETED'),(3,'COMPLETED'),(4,'COMPLETED')])
def test_requester_report_window(setup,days,status):
    case_id=add_case(setup,status,days)
    response=setup[3].post(f'/expert-support/cases/{case_id}/complete',data={'action':'DISPUTE'},headers={'Accept':'application/json'})
    assert response.status_code==(200 if days<=3 else 409)
    with Session(setup[0]) as s:
        assert s.get(main.ConsultationCase,case_id).status==('DISPUTE' if days<=3 else 'COMPLETED')


@pytest.mark.parametrize('actor,days,code',[('requester',2,200),('requester',4,409),('expert',2,409),('outsider',2,403)])
def test_menu_report_enforces_same_deadline(setup,actor,days,code):
    case_id=add_case(setup,completed_days=days)
    response=setup[3].post(f'/expert-support/cases/{case_id}/report',data={'reason':'OTHER'},headers={'x-user':actor,'Accept':'application/json'},follow_redirects=False)
    assert response.status_code==code


@pytest.mark.parametrize('preserve', ['none','closed_report','dispute','support_ticket'])
def test_seven_day_purge_preserves_all_report_evidence(setup,preserve):
    engine, now, users, _=setup;case_id=add_case(setup,completed_days=7)
    with Session(engine) as s:
        case=s.get(main.ConsultationCase,case_id)
        if preserve=='closed_report':s.add(main.UserReport(reporter_user_id=users['requester'].id,reported_user_id=users['expert'].id,case_id=case_id,reason='OTHER',status='CLOSED'))
        if preserve=='dispute':case.dispute_opened_at=now-timedelta(days=6);s.add(case)
        if preserve=='support_ticket':s.add(main.SupportTicket(user_id=users['requester'].id,subject='Problem',message='Problem',case_id=case_id))
        s.flush()
        job=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).one()
        # Boundary: one second before expiry must retain every message.
        main._process_deadline_job(s,job,now-timedelta(seconds=1))
        assert len(s.exec(select(main.ConsultationMessage)).all())==1
        _,events=main._process_deadline_job(s,job,now);s.commit()
        assert bool(s.get(main.ConsultationCase,case_id).messages_deleted_at)==(preserve=='none')
        assert len(s.exec(select(main.ConsultationMessage)).all())==(0 if preserve=='none' else 1)
        assert len(s.exec(select(main.RealtimeEvent).where(main.RealtimeEvent.event_type=='MESSAGE_CREATED')).all())==(0 if preserve=='none' else 2)
        assert len(events)==(2 if preserve=='none' else 0)


def test_media_outbox_only_runs_after_database_purge_commit(setup,monkeypatch):
    engine,now,_,_=setup;case_id=add_case(setup,completed_days=7);removed=[]
    monkeypatch.setattr(main,'storage_delete',lambda path:removed.append(path))
    with Session(engine) as s:
        message=s.exec(select(main.ConsultationMessage)).one();message.media_path='uploads/chat.png';message.original_media_path='uploads/original.png';s.add(message);s.flush()
        case=s.get(main.ConsultationCase,case_id);main._purge_consultation_messages(s,case,now);s.commit()
        assert removed==[]
        job=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.job_type=='CHAT_MEDIA_PURGE')).one()
        main._process_deadline_job(s,job,now);s.commit()
        assert set(removed)=={'uploads/chat.png','uploads/original.png'}
        assert not s.exec(select(main.ConsultationMediaDeletion)).all()


def test_only_admin_can_purge_dispute_and_block_new_messages(setup):
    engine,now,_,client=setup;case_id=add_case(setup,'DISPUTE')
    with Session(engine) as s:
        case=s.get(main.ConsultationCase,case_id);case.dispute_opened_at=now;s.add(case);s.commit()
    url=f'/admin/consultation-review/{case_id}/delete-messages'
    assert client.post(url,headers={'x-user':'requester'},follow_redirects=False).status_code==403
    assert client.post(url,headers={'x-user':'admin'},follow_redirects=False).status_code==303
    assert client.post(f'/expert-support/cases/{case_id}/message',data={'content':'New message'},headers={'Accept':'application/json'}).status_code==409
    with Session(engine) as s:
        assert not s.exec(select(main.ConsultationMessage)).all()
        assert s.get(main.ConsultationCase,case_id).messages_deleted_at


def test_manual_delete_hides_only_one_participant_without_restoring_on_get(setup):
    engine,_,users,client=setup;case_id=add_case(setup,'DISPUTE')
    assert client.post(f'/messages/{case_id}/delete',follow_redirects=False).status_code==303
    assert client.get(f'/expert-support/cases/{case_id}',follow_redirects=False).status_code==303
    assert client.get(f'/expert-support/cases/{case_id}',headers={'x-user':'expert'}).status_code==200
    with Session(engine) as s:
        assert len(s.exec(select(main.ConsultationMessage)).all())==1
        assert main._consultation_inbox_state(s,case_id,users['requester'].id).deleted_at
        assert not main._consultation_inbox_state(s,case_id,users['expert'].id).deleted_at
    assert client.post(f'/messages/{case_id}/restore',headers={'x-user':'outsider'},follow_redirects=False).status_code==403


def test_program_fragment_has_navigation_without_shell(setup):
    response=setup[3].get('/program?view=week&day=2026-10-10',headers={'x-program-fragment':'1'})
    assert response.status_code==200
    assert 'aria-label="Önceki hafta"' in response.text
    assert 'aria-label="Sonraki hafta"' in response.text
    assert '<html' not in response.text
    assert '2026-10-03' in response.text and '2026-10-17' in response.text


@pytest.mark.parametrize('transition',['continue','accept','proposal'])
def test_new_or_resumed_cases_do_not_exceed_five_slots(setup,transition):
    for _ in range(5):add_case(setup,'ACTIVE')
    status={'continue':'EXPERT_COMPLETED','accept':'REQUESTED','proposal':'PROPOSED'}[transition]
    case_id=add_case(setup,status)
    if transition=='proposal':
        with Session(setup[0]) as s:
            case=s.get(main.ConsultationCase,case_id);case.requester_decision_deadline=setup[1]+timedelta(minutes=3);s.add(case);s.commit()
    url={'continue':'complete','accept':'expert-response','proposal':'proposal'}[transition]
    data={'action':'CONTINUE'} if transition=='continue' else {'decision':'ACCEPT','start_option':'NOW'}
    response=setup[3].post(f'/expert-support/cases/{case_id}/{url}',data=data,headers={'x-user':'expert' if transition=='accept' else 'requester','Accept':'application/json'})
    assert response.status_code==409
    with Session(setup[0]) as s:
        assert main._expert_open_case_count(s,setup[2]['expert'].id)==5
        assert s.get(main.ConsultationCase,case_id).status==status


def test_confirmation_enqueues_retention_from_completion_timestamp(setup):
    case_id=add_case(setup,'EXPERT_COMPLETED')
    response=setup[3].post(f'/expert-support/cases/{case_id}/complete',data={'action':'COMPLETE'},headers={'Accept':'application/json'})
    assert response.status_code==200
    with Session(setup[0]) as s:
        case=s.get(main.ConsultationCase,case_id)
        job=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.case_id==case_id,main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).one()
        assert job.run_at==case.completed_at+timedelta(days=7)


def test_delayed_auto_confirmation_uses_deadline_not_worker_run_time(setup):
    case_id=add_case(setup,'EXPERT_COMPLETED');engine,now,_,_=setup
    with Session(engine) as s:
        case=s.get(main.ConsultationCase,case_id);case.completion_confirmation_deadline=now-timedelta(days=2);s.add(case)
        main._enqueue_deadline_pair(s,case_id,'COMPLETION',case.completion_confirmation_deadline);s.flush()
        job=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.job_type=='COMPLETION_DUE')).one()
        main._process_deadline_job(s,job,now);s.commit()
        case=s.get(main.ConsultationCase,case_id)
        assert case.completed_at==now-timedelta(days=2)
        purge=s.exec(select(main.ConsultationDeadlineJob).where(main.ConsultationDeadlineJob.job_type=='CHAT_PURGE')).one()
        assert purge.run_at==now+timedelta(days=5)
