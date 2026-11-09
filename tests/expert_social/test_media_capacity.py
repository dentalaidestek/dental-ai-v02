from app import object_storage, object_cache
from test_api import env
from test_moderation_lifecycle import image_post

def test_busy_cache_returns_retryable_media_error(env, monkeypatch):
    client,engine=env
    post=image_post(client,engine)
    def busy(reference):
        raise object_cache.CacheCapacityError('Object cache is busy; retry later')
    monkeypatch.setattr(object_storage,'ensure_local',busy)
    response=client.get(post['media'][0]['url'])
    assert response.status_code==503
    assert 'retry-after' in response.headers
