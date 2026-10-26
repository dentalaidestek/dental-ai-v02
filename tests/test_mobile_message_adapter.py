"""Exercise the native message adapter against the real async offload boundary."""
import ast
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request
import json
import pytest
import runpy


@pytest.mark.parametrize('status', [200, 403, 409])
def test_mobile_adapter_awaits_send_and_preserves_handler_errors(status):
    root = Path(__file__).parents[1]
    offload = runpy.run_path(str(root / 'app/execution.py'))['offload']
    calls = []
    @offload
    def send(request, case_id, content, reply_to_message_id, client_message_id):
        calls.append((request.cookies['dental_ai_session'], case_id, content, reply_to_message_id, client_message_id))
        return JSONResponse({'ok': status == 200, **({'message': {'id': 55}} if status == 200 else {'error': 'synthetic refusal'})}, status_code=status)
    def access(): return 'SYNTHETIC_TOKEN'
    tree = ast.parse((root / 'app/mobile_api.py').read_text())
    names = {'MobileMessage', '_mobile_request', '_response_json', 'mobile_send_consultation_message'}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in nodes: node.decorator_list = []
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = dict(BaseModel=BaseModel, Optional=Optional, Depends=Depends, _mobile_access_token=access,
        SESSION_COOKIE='dental_ai_session', Request=Request, JSONResponse=JSONResponse, json=json,
        expert_support_message=send, HTTPException=HTTPException)
    exec(compile(ast.fix_missing_locations(module), '<actual-native-message-adapter>', 'exec'), namespace)
    app = FastAPI()
    app.add_api_route('/consultations/{case_id}/messages', namespace['mobile_send_consultation_message'], methods=['POST'])
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/consultations/7/messages', json={
            'content': 'Sentetik mesaj', 'reply_to_message_id': 3, 'client_message_id': 'synthetic-id'})
    assert response.status_code == status
    assert calls == [('SYNTHETIC_TOKEN', 7, 'Sentetik mesaj', 3, 'synthetic-id')]
    assert response.json() == ({'ok': True, 'message': {'id': 55}} if status == 200 else {'detail': 'synthetic refusal'})
