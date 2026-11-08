"""Public expert identity cannot be elevated by an entered name or ORCID."""
from types import SimpleNamespace

import pytest
from sqlmodel import Session
from app import main
from app.expert_social_identity import expert_display_name
from test_api import env, post


@pytest.mark.parametrize("name", ["Prof. Dr. Örnek Hekim", "Doç. Dr. Örnek Hekim", "Uzm. Dt. Örnek Hekim", "Dr. Öğr. Üyesi Örnek Hekim", "Arş. Gör. Dt. Örnek Hekim"])
def test_only_verification_record_sets_display_title(name):
    profile = SimpleNamespace(academic_title="Prof. Dr.", academic_title_verified=False,
                              orcid_url="https://orcid.org/0000-0002-1825-0097")
    assert expert_display_name(profile, name) == "Uzm. Dt. Örnek Hekim"
    profile.academic_title = "Doç. Dr."
    profile.academic_title_verified = True
    assert expert_display_name(profile, name) == "Doç. Dr. Örnek Hekim"


def test_name_does_not_strip_names_with_title_letters():
    profile = SimpleNamespace(academic_title="Unsupported", academic_title_verified=True)
    assert expert_display_name(profile, "Dora Dray") == "Uzm. Dt. Dora Dray"


def test_post_serializer_honors_academic_verification_and_blocks(env):
    client, engine = env
    with Session(engine) as s:
        user = s.get(main.User,1)
        user.display_name = "Prof. Dr. Örnek Hekim"
        s.add(user);s.commit()
    created = post(client).json()
    assert created['author_name'] == 'Uzm. Dt. Örnek Hekim'
    with Session(engine) as s:
        s.add(main.UserBlock(blocker_user_id=2,blocked_user_id=1));s.commit()
    client.cookies.set(main.SESSION_COOKIE,'t2')
    assert client.get('/api/expert-social/experts/1/posts').status_code == 404
    assert client.get('/api/expert-social/experts/1/stats').status_code == 404
    assert client.get('/api/expert-social/posts/'+str(created['id'])).status_code == 404
    assert client.put('/api/expert-social/experts/1/follow',json={'followed':True}).status_code == 403
