"""Exercise the actual handler bodies without booting the full site/database.

The checkout is a voice snapshot. Only route registration and external handler
I/O are substituted; middleware, request/response handling and adapter code run.
"""
import ast
import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def handlers(path, names, namespace):
    tree = ast.parse(Path(path).read_text())
    body = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    body += [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(body) == len(names) + 1
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), path, 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('path,auth,media,initial,want', [
    ('/expert-support/cases/1/media/1', 'cookie', 'image/jpeg', 'private, max-age=31536000, immutable', 'private, no-store'),
    ('/patients/1/media', 'bearer', 'image/jpeg', 'private, max-age=31536000, immutable', 'private, no-store'),
    ('/api/mobile/v1/patients', 'bearer', 'application/json', None, 'private, no-store'),
    ('/api/mobile/v1/patients/1/media/1/file', 'bearer', 'image/jpeg', 'private, max-age=31536000, immutable', 'private, no-store'),
    ('/voice-exams', 'cookie', 'text/html', None, 'private, no-store'),
    ('/site/runtime-config', 'cookie', 'application/json', 'private, max-age=300', 'private, max-age=300'),
    ('/static/voice-exam.js', 'cookie', 'text/javascript', 'public, max-age=3600', 'public, max-age=3600'),
    ('/public', '', 'text/html', 'public, max-age=60', 'public, max-age=60')])
def test_private_clinical_response_cache_policy(path, auth, media, initial, want):
    ns = handlers('app/main.py', {'security_headers'}, {
        'app': SimpleNamespace(middleware=lambda *a, **k: lambda f: f),
        'SESSION_COOKIE': 'test_session', 'Request': Request})
    headers = [(b'cookie', b'test_session=synthetic')] if auth == 'cookie' else [(b'authorization', b'Bearer synthetic')] if auth else []
    request = Request({'type': 'http', 'method': 'GET', 'scheme': 'https', 'path': path,
                       'headers': headers, 'query_string': b''})
    async def downstream(req):
        return Response('synthetic', media_type=media, headers={'Cache-Control': initial} if initial else {})
    result = asyncio.run(ns['security_headers'](request, downstream))
    assert result.headers['Cache-Control'] == want


@pytest.mark.parametrize('status', [200, 403])
def test_mobile_message_adapter_awaits_offloaded_result_and_preserves_errors(status):
    async def expert(request, case_id, content, reply_id, client_id):
        return JSONResponse({'ok': status == 200, 'content': content, 'reply_id': reply_id,
                             'client_id': client_id, 'error': 'Synthetic denial'}, status_code=status)
    ns = handlers('app/mobile_api.py', {'_response_json', 'mobile_send_consultation_message'}, {
        'router': SimpleNamespace(post=lambda *a, **k: lambda f: f),
        'Depends': Depends, '_mobile_access_token': lambda: 'synthetic',
        '_mobile_request': lambda token: token, 'expert_support_message': expert,
        'JSONResponse': JSONResponse, 'HTTPException': HTTPException, 'json': json})
    async def invoke():
        result = ns['mobile_send_consultation_message'](7, SimpleNamespace(
            content='Sentetik mesaj', reply_to_message_id=3, client_message_id='test-id'), token='synthetic')
        return await result if inspect.isawaitable(result) else result
    if status == 403:
        with pytest.raises(HTTPException) as error:
            asyncio.run(invoke())
        assert error.value.status_code == 403
        assert error.value.detail == 'Synthetic denial'
    else:
        assert asyncio.run(invoke()) == {'ok': True, 'content': 'Sentetik mesaj',
            'reply_id': 3, 'client_id': 'test-id', 'error': 'Synthetic denial'}
