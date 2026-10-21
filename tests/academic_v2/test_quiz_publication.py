import json
from types import SimpleNamespace
from tests.academic_v2.test_remote_pdf import owned
from tests.academic_v2.test_quiz_quality import question,validate
from app import academic_study_runs as runs
from app.academic_quiz import pack_evidence,render_quiz


def test_completed_quiz_payload_contains_public_choices_without_key(owned):
    main,factory,_=owned
    quiz=validate(question())
    with factory() as session:
        message=session.get(main.StudyChatMessage,10)
        message.mode='RAG_V2_HYBRID'
        message.content=render_quiz(quiz)
        versions=main._study_source_versions(session,1,6)
        message.source_evidence_json=pack_evidence('[]',quiz,message.content,versions)
        session.add(message);session.commit()
        row=SimpleNamespace(status='DONE',id=1,stage='Tamamlandı',question='Soru hazırla',
            partial_text='',error=None,assistant_message_id=10,owner_user_id=1,course_id=6)
        result=runs.payload(session,row)
        assert result['quiz']['message_id']==10
        public=result['quiz']['questions'][0]
        assert public['options']==quiz['questions'][0]['options']
        assert public['result'] is None
        assert 'correct' not in public and 'rationale' not in public


def test_quiz_text_not_published_as_partial_before_controls(monkeypatch):
    snapshots=[]
    monkeypatch.setattr(runs,'checkpoint',lambda *a,**kw:snapshots.append(kw))
    clock=iter([0,3,4]);monkeypatch.setattr(runs.time,'monotonic',lambda:next(clock))
    answer='### Soru 1\nSoru metni\n\nA) Seçenek'
    assert ''.join(runs.generation(None,1,iter([answer])))==answer
    assert snapshots[-1]['partial']==''
