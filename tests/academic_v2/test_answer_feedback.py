import json
from types import SimpleNamespace
from sqlmodel import Session
from tests.academic_v2.test_remote_pdf import owned
from app.academic_quiz_interactions import save_feedback,list_feedback


def test_owned_reaction_switch_clear_and_preserve_evidence(owned):
    main,factory,_=owned
    with factory() as s:
        row=s.get(main.StudyChatMessage,10)
        row.source_evidence_json=json.dumps({'answer_hash':'original','quiz':{'questions':[]}})
        s.add(row);s.commit()
    for vote in ['like','dislike','none']:
        result=save_feedback(None,6,10,vote)
        assert result.status_code==200
        snapshot=json.loads(list_feedback(None,6,'10,30').body)
        assert snapshot['votes']==({'10':vote} if vote!='none' else {})
        with factory() as s:
            metadata=json.loads(s.get(main.StudyChatMessage,10).source_evidence_json)
            assert metadata['answer_hash']=='original' and metadata['quiz']=={'questions':[]}


def test_feedback_rejects_foreign_user_messages_invalid_votes(owned):
    main,factory,_=owned
    assert save_feedback(None,6,30,'like').status_code==404
    assert save_feedback(None,6,10,'bad').status_code==400
    assert save_feedback(None,999,10,'like').status_code==404
    assert list_feedback(None,6,'x').status_code==400
    with factory() as s:
        row=s.get(main.StudyChatMessage,10);row.role='USER';s.add(row);s.commit()
    assert save_feedback(None,6,10,'like').status_code==404


def test_feedback_requires_login(owned,monkeypatch):
    main,_,_=owned
    monkeypatch.setattr(main,'get_current_user',lambda r:None)
    assert save_feedback(None,6,10,'like').status_code==401
    assert list_feedback(None,6,'10').status_code==401
