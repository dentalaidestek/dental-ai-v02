import json
from contextlib import nullcontext
import sys
from types import ModuleType
import pytest
from app import voice_exam_review_provider as provider


def test_native_research_message_uses_current_provider_with_server_tools_not_json_schema(monkeypatch):
    import app.http_transport as transport
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-private-key')
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL','claude-test-existing')
    budget=ModuleType('app.provider_budget');budget.reservation=lambda *a:nullcontext()
    monkeypatch.setitem(sys.modules,'app.provider_budget',budget)
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps({'role':'assistant','content':[],'stop_reason':'end_turn'}).encode()
    def request(req,**kw):
        calls.append((req,kw));return Response()
    monkeypatch.setattr(transport,'urlopen',request)
    tools=[{'type':'web_search_20250305','name':'web_search','max_uses':2}]
    result=provider.research_message('Public research only',{'topics':[{'topic':'prosth.occlusion'}]},tools,timeout=23)
    payload=json.loads(calls[0][0].data)
    assert payload['model']=='claude-test-existing' and payload['tools']==tools
    assert 'output_config' not in payload and 'tool_choice' not in payload
    assert calls[0][1]['timeout']==23
    assert calls[0][0].headers['X-api-key']=='synthetic-private-key'
    assert result['stop_reason']=='end_turn'


def test_research_pause_continuation_preserves_native_content(monkeypatch):
    import app.http_transport as transport
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-private-key')
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL','claude-existing')
    budget=ModuleType('app.provider_budget');budget.reservation=lambda *a:nullcontext()
    monkeypatch.setitem(sys.modules,'app.provider_budget',budget)
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return b'{"role":"assistant","content":[],"stop_reason":"end_turn"}'
    monkeypatch.setattr(transport,'urlopen',lambda req,**kw:calls.append(json.loads(req.data)) or Response())
    previous=[{'role':'user','content':'Public topic'}, {'role':'assistant','content':[{'type':'server_tool_use','id':'srv1','name':'web_search','input':{'query':'crown occlusion'}}]}]
    provider.research_message('Public research',{},[],previous_messages=previous,timeout=20)
    assert calls[0]['messages']==previous


def test_unconfigured_native_research_never_attempts_network(monkeypatch):
    import app.http_transport as transport
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    monkeypatch.setattr(transport,'urlopen',lambda *a,**k:pytest.fail('No network without configured provider'))
    with pytest.raises(provider.core.VoiceError):
        provider.research_message('Public',{},[])
