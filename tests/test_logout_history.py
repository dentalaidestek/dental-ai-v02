import asyncio
from datetime import timedelta

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from sqlmodel import Session, SQLModel, create_engine
from app import main


def request(token=None):
    headers = [(b'cookie', f'{main.SESSION_COOKIE}={token}'.encode())] if token else []
    return Request({'type': 'http', 'method': 'GET', 'path': '/account', 'headers': headers, 'scheme': 'https'})


def test_logout_revokes_token_even_if_browser_replays_cookie(monkeypatch, tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'logout.db'))
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, 'engine', engine)
    with Session(engine) as session:
        user = main.User(username='history', display_name='History', email='history@example.test', role='DOCTOR', is_active=True, email_verified_at=main._utcnow_naive())
        session.add(user); session.flush()
        session.add(main.SessionToken(user_id=user.id, token_hash=main.hash_session_token('old-token'), expires_at=main._utcnow_naive() + timedelta(days=1)))
        session.commit()
    assert main.get_current_user(request('old-token')) is not None
    response = main.logout_user(request('old-token'))
    assert response.status_code == 303
    assert response.headers['location'] == '/login'
    assert main.get_current_user(request('old-token')) is None
    assert 'Max-Age=0' in response.headers['set-cookie']
    engine.dispose()


def test_private_html_is_not_cached_but_public_and_assets_keep_policy():
    async def run(token, html):
        async def next_response(_):
            return HTMLResponse('private', headers={'Cache-Control': 'public, max-age=600'}) if html else Response('asset', media_type='text/css', headers={'Cache-Control': 'public, max-age=600'})
        return await main.security_headers(request(token), next_response)
    assert asyncio.run(run('old-token', True)).headers['cache-control'] == 'private, no-store'
    assert asyncio.run(run(None, True)).headers['cache-control'] == 'public, max-age=600'
    assert asyncio.run(run('old-token', False)).headers['cache-control'] == 'public, max-age=600'
