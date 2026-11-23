"""Native request creation shares web idempotency, eligibility and media permissions."""
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel,Session,create_engine,select
from app import main,mobile_api

@pytest.fixture
def request_env(monkeypatch,tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"requests.db"),connect_args={"check_same_thread":False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,"engine",engine);monkeypatch.setattr(mobile_api,"engine",engine)
    with Session(engine) as s:
        for ident in (1,2,3):
            s.add(main.User(id=ident,username="request-user-"+str(ident),display_name="Synthetic "+str(ident),
                role="DOCTOR",is_active=True,email_verified_at=main._utcnow_naive()))
            s.add(main.SessionToken(user_id=ident,token_hash=main.hash_session_token("token"+str(ident)),
                expires_at=main._utcnow_naive()+timedelta(days=1)))
        s.add(main.ExpertProfile(user_id=2,specialty="Endodonti",consultation_price=150,availability="AVAILABLE",
            phone="05000000000",application_status="APPROVED",verification_status="VERIFIED",
            specialty_verified=True,credential_document_path="synthetic-credential"))
        s.add(main.Patient(id=11,anonymous_id="ANON-11",owner_user_id=1))
        s.add(main.Patient(id=33,anonymous_id="ANON-33",owner_user_id=3))
        s.add(main.PatientMedia(id=17,patient_id=11,owner_user_id=1,original_filename="synthetic.png",
            stored_filename="synthetic17.png",file_path="synthetic17.png"))
        s.add(main.PatientMedia(id=37,patient_id=33,owner_user_id=3,original_filename="synthetic.png",
            stored_filename="synthetic37.png",file_path="synthetic37.png"))
        s.commit()
    client=TestClient(main.app);client.headers["Authorization"]="Bearer token1"
    return client,engine

def payload():
    return {"expert_user_id":2,"patient_id":11,"clinical_summary":"Synthetic clinical summary",
        "requester_opinion":"Synthetic opinion","question":"Synthetic question","tooth_region":"46",
        "urgency":"ASAP","media_ids":"17","request_key":"11111111-1111-4111-8111-111111111111"}

def test_native_request_matches_web_fields_and_same_key_reopens_one_case(request_env):
    c,engine=request_env
    first=c.post("/api/mobile/v1/consultations",json=payload())
    assert first.status_code==200,first.text
    second=c.post("/api/mobile/v1/consultations",json=payload())
    assert second.status_code==200,second.text
    assert first.json()["case_id"]==second.json()["case_id"]
    with Session(engine) as s:
        cases=s.exec(select(main.ConsultationCase)).all()
        assert len(cases)==1
        case=cases[0]
        assert (case.tooth_region,case.urgency,case.requester_opinion)==("46","ASAP","Synthetic opinion")
        assert case.price_amount==150
        links=s.exec(select(main.ConsultationCaseMedia)).all()
        assert [link.patient_media_id for link in links]==[17]

def test_request_context_rechecks_expert_and_exposes_web_priorities(request_env):
    c,engine=request_env
    r=c.get("/api/mobile/v1/consultations/request-context/2")
    assert r.status_code==200,r.text
    assert r.json()["expert"]["consultation_price"]==150
    assert [item["value"] for item in r.json()["urgencies"]]==["ASAP","1H","TODAY","NORMAL"]
    assert c.get("/api/mobile/v1/consultations/request-context/1").status_code==400
    with Session(engine) as s:
        profile=s.exec(select(main.ExpertProfile).where(main.ExpertProfile.user_id==2)).one()
        profile.availability="PASSIVE";s.add(profile);s.commit()
    assert c.get("/api/mobile/v1/consultations/request-context/2").status_code==409
    assert c.post("/api/mobile/v1/consultations",json=payload()).status_code==409

def test_patient_and_selected_media_are_owned_before_creating_request(request_env):
    c,engine=request_env
    bad=payload();bad["media_ids"]="37"
    assert c.post("/api/mobile/v1/consultations",json=bad).status_code==403
    bad=payload();bad["patient_id"]=33;bad["media_ids"]=""
    assert c.post("/api/mobile/v1/consultations",json=bad).status_code==403
    with Session(engine) as s: assert s.exec(select(main.ConsultationCase)).all()==[]

def test_request_receipt_is_private_and_changed_payload_cannot_reuse_key(request_env):
    c,engine=request_env
    p=payload();created=c.post("/api/mobile/v1/consultations",json=p)
    assert created.status_code==200,created.text
    path="/api/mobile/v1/consultations/request-status/2/"+p["request_key"]
    assert c.get(path).json()["case_id"]==created.json()["case_id"]
    changed={**p,"question":"Different synthetic question"}
    assert c.post("/api/mobile/v1/consultations",json=changed).status_code==409
    c.headers["Authorization"]="Bearer token3"
    assert c.get(path).json()=={"found":False}
