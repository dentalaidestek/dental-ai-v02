"""Caption edits retain the original post and all member interactions."""
import uuid

import pytest
from sqlmodel import Session, select

from app import main
from app.expert_social_models import SocialPost, SocialMedia, SocialComment, SocialLike, SocialCommentLike, SocialModerationEvent
from test_api import env, post
from test_moderation_lifecycle import image_post


def approved_image(client, engine):
    item = image_post(client, engine)
    client.cookies.set(main.SESSION_COOKIE, 't4')
    response = client.post(f"/api/expert-social/moderation/POST/{item['id']}", json={
        'status':'PUBLISHED', 'version':item['version'], 'reason':'Kimlik bilgisi içermeyen görsel onaylandı.'})
    assert response.status_code == 200, response.text
    client.cookies.set(main.SESSION_COOKIE, 't1')
    return client.get(f"/api/expert-social/posts/{item['id']}").json()


@pytest.mark.parametrize('image', [False, True])
@pytest.mark.parametrize('needs_review', [False, True])
def test_edit_retains_id_likes_comments_replies_media_and_creation_time(env, image, needs_review):
    client, engine = env
    item = approved_image(client, engine) if image else post(client).json()
    ident = item['id']; url = f'/api/expert-social/posts/{ident}'
    client.cookies.set(main.SESSION_COOKIE, 't2')
    assert client.put(url+'/like', json={'liked':True}).status_code == 200
    comment = client.post(url+'/comments', json={'text':'Bilimsel katkı için teşekkürler.', 'idempotency_key':str(uuid.uuid4())}).json()
    reply = client.post(url+'/comments', json={'text':'Mesleki bir yanıt.', 'parent_id':comment['id'], 'idempotency_key':str(uuid.uuid4())}).json()
    assert client.put(f"/api/expert-social/comments/{comment['id']}/like", json={'liked':True}).status_code == 200
    client.cookies.set(main.SESSION_COOKIE, 't1')
    caption = 'Hasta adı: Sentetik Kişi, 0532 123 45 67' if needs_review else 'Güncellenmiş bilimsel açıklama.'
    response = client.patch(url, json={'version':item['version'], 'text':caption})
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited['id'] == ident and edited['created_at'] == item['created_at']
    assert edited['like_count'] == 1 and edited['comment_count'] == 2
    assert edited['media'] == item['media'] and edited['link_url'] == item['link_url']
    assert edited['status'] == ('PENDING' if needs_review else 'PUBLISHED')
    with Session(engine) as session:
        assert len(session.exec(select(SocialPost)).all()) == 1
        assert len(session.exec(select(SocialLike)).all()) == 1
        assert {row.id for row in session.exec(select(SocialComment)).all()} == {comment['id'], reply['id']}
        assert len(session.exec(select(SocialCommentLike)).all()) == 1
        assert len(session.exec(select(SocialMedia)).all()) == len(item['media'])
    if needs_review:
        client.cookies.set(main.SESSION_COOKIE, 't2')
        assert client.get(url).status_code == 404
        client.cookies.set(main.SESSION_COOKIE, 't4')
        assert client.post(f'/api/expert-social/moderation/POST/{ident}', json={
            'status':'PUBLISHED', 'version':edited['version'], 'reason':'Sentetik test içeriği tekrar onaylandı.'}).status_code == 200
    client.cookies.set(main.SESSION_COOKIE, 't2')
    published = client.get(url).json()
    assert published['liked'] and published['like_count'] == 1 and published['comment_count'] == 2
    comments = client.get(url+'/comments').json()['items']
    assert {row['id'] for row in comments} == {comment['id'],reply['id']}
    assert next(row for row in comments if row['id']==comment['id'])['liked']


def test_unchanged_caption_does_not_requeue_approved_image_or_replace_human_decision(env):
    client, engine = env
    item = approved_image(client, engine)
    with Session(engine) as session:
        events = len(session.exec(select(SocialModerationEvent)).all())
    response = client.patch(f"/api/expert-social/posts/{item['id']}", json={'version':item['version'], 'text':'  '+item['text']+'  '})
    assert response.status_code == 200, response.text
    unchanged = response.json()
    assert unchanged['version'] == item['version'] and unchanged['status'] == 'PUBLISHED'
    for key in ['last_decision','revision','state','content_version']:
        assert unchanged['moderation'][key] == item['moderation'][key]
    with Session(engine) as session:
        assert len(session.exec(select(SocialModerationEvent)).all()) == events


def test_caption_edit_never_publishes_an_unapproved_image(env):
    client, engine = env
    item = image_post(client, engine)
    response = client.patch(f"/api/expert-social/posts/{item['id']}", json={'version':item['version'], 'text':'Yeni bilimsel açıklama.'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'PENDING'
    assert 'IMAGE_REVIEW' in response.json()['moderation']['reasons']
