"""Exercise the actual application security middleware without booting cloud services."""
import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    tree = ast.parse((Path(__file__).parents[1] / 'app/main.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'security_headers')
    function.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), function], type_ignores=[])
    namespace = {'SESSION_COOKIE': 'dental_ai_session'}
    exec(compile(ast.fix_missing_locations(module), '<actual-security-middleware>', 'exec'), namespace)
    app = FastAPI()
    app.middleware('http')(namespace['security_headers'])
    @app.get('/protected/{kind}')
    def protected(kind: str):
        mime = {'image': 'image/png', 'pdf': 'application/pdf', 'json': 'application/json', 'html': 'text/html'}[kind]
        return Response(b'SYNTHETIC_PRIVATE_CONTENT', media_type=mime)
    @app.get('/static/app.js')
    def static():
        return Response('/* synthetic */', media_type='text/javascript', headers={'Cache-Control': 'public, max-age=86400'})
    @app.get('/static/plain.js')
    def static_without_cache():
        return Response('/* synthetic */', media_type='text/javascript')
    @app.get('/site/runtime-config')
    def config():
        return Response('{}', media_type='application/json', headers={'Cache-Control': 'private, max-age=300'})
    @app.get('/expert-support/cases/7/message-media/55')
    def medical_attachment():
        return Response(b'SYNTHETIC_PRIVATE_CONTENT', media_type='image/png',
            headers={'Cache-Control': 'private, max-age=31536000, immutable'})
    with TestClient(app, base_url='https://synthetic.local') as client:
        yield client


@pytest.mark.parametrize('kind', ['image', 'pdf', 'json', 'html'])
@pytest.mark.parametrize('auth', ['cookie', 'bearer'])
def test_authenticated_private_responses_are_not_cacheable(client, kind, auth):
    headers = {'Cookie': 'dental_ai_session=SYNTHETIC'} if auth == 'cookie' else {'Authorization': 'Bearer SYNTHETIC'}
    response = client.get('/protected/' + kind, headers=headers)
    assert response.status_code == 200
    assert response.content == b'SYNTHETIC_PRIVATE_CONTENT'
    assert response.headers.get('cache-control') == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_static_asset_cache_is_preserved_with_session_cookie(client):
    response = client.get('/static/app.js', headers={'Cookie': 'dental_ai_session=SYNTHETIC'})
    assert response.headers['cache-control'] == 'public, max-age=86400'
    assert 'cache-control' not in client.get('/static/plain.js', headers={'Cookie': 'dental_ai_session=SYNTHETIC'}).headers


def test_explicit_private_runtime_cache_is_preserved(client):
    response = client.get('/site/runtime-config', headers={'Cookie': 'dental_ai_session=SYNTHETIC'})
    assert response.headers['cache-control'] == 'private, max-age=300'


def test_anonymous_response_without_private_auth_is_unchanged(client):
    assert 'cache-control' not in client.get('/protected/json').headers


@pytest.mark.parametrize('headers', [
    {'Cookie': 'dental_ai_session=SYNTHETIC'},
    {'Authorization': 'Bearer SYNTHETIC'},
])
def test_medical_attachment_cannot_keep_year_long_cache_policy(client, headers):
    response = client.get('/expert-support/cases/7/message-media/55', headers=headers)
    assert response.headers['cache-control'] == 'private, no-store'
