"""Research failures expose fixed boundary codes without logging source content."""
import io
import json
import sys
import urllib.error
from collections import OrderedDict
from contextlib import contextmanager, nullcontext
from types import ModuleType

import pytest

from app import voice_exam_review_provider as provider
from app import voice_exam_web_research as web
from app.provider_budget import ProviderBusy
from app.voice_source_pool import BoundedPool


PRIVATE = 'PRIVATE_PATIENT_SECRET_12345678901'
PRIVATE_URL = 'https://private.example/' + PRIVATE
TOPICS = [{'topic': 'endo.general', 'quote': PRIVATE}]


@pytest.fixture
def transport(monkeypatch):
    """Replace only shared I/O and budget storage; run the actual provider parser."""
    import app.http_transport as http
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-key-' + PRIVATE)
    monkeypatch.setenv('VOICE_EXAM_CLAUDE_MODEL', 'claude-test')
    budget = ModuleType('app.provider_budget')
    budget.reservation = lambda *args: nullcontext()
    monkeypatch.setitem(sys.modules, 'app.provider_budget', budget)
    state = {'raw': b'{"content": [], "stop_reason": "end_turn"}', 'read_limits': []}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            state['read_limits'].append(limit)
            if 'read_error' in state:
                raise state['read_error']
            return state['raw'][:limit]

    def request(*args, **kwargs):
        if 'open_error' in state:
            raise state['open_error']
        return Response()

    monkeypatch.setattr(http, 'urlopen', request)
    state['budget'] = budget
    return state


@pytest.mark.parametrize('boundary,stage,category,error_type', [
    ('budget', 'reservation', 'budget', ProviderBusy),
    ('http', 'transport', 'http', urllib.error.HTTPError),
    ('transport', 'transport', 'transport', urllib.error.URLError),
    ('timeout', 'transport', 'timeout', TimeoutError),
    ('read', 'response-read', 'transport', urllib.error.URLError),
    ('oversize', 'response-size', 'oversize', ValueError),
    ('json', 'response-json', 'invalid-json', json.JSONDecodeError),
    ('shape', 'response-shape', 'invalid-message', ValueError),
    ('metadata', 'response-metadata', 'invalid-metadata', TypeError),
])
def test_failed_native_response_reports_actual_boundary_without_sensitive_values(
        transport, caplog, boundary, stage, category, error_type):
    original = None
    if boundary == 'budget':
        original = ProviderBusy(PRIVATE)

        @contextmanager
        def unavailable(*args):
            raise original
            yield

        transport['budget'].reservation = unavailable
    elif boundary == 'http':
        original = urllib.error.HTTPError(PRIVATE_URL, 429, PRIVATE, {},
                                          io.BytesIO(PRIVATE.encode()))
        transport['open_error'] = original
    elif boundary in ('transport', 'timeout', 'read'):
        original = TimeoutError(PRIVATE) if boundary == 'timeout' else urllib.error.URLError(PRIVATE_URL)
        transport['read_error' if boundary == 'read' else 'open_error'] = original
    elif boundary == 'oversize':
        transport['raw'] = b' ' * 180001
    elif boundary == 'json':
        transport['raw'] = PRIVATE.encode()
    elif boundary == 'shape':
        transport['raw'] = json.dumps({'content': PRIVATE}).encode()
    elif boundary == 'metadata':
        transport['raw'] = json.dumps({'content': [], 'stop_reason': [PRIVATE]}).encode()

    with pytest.raises(error_type) as failure:
        provider.research_message('Public concepts only', {'topics': []}, [])
    if original is not None:
        assert failure.value is original
    assert 'voice_public_research_failure stage=' + stage + ' category=' + category in caplog.text
    assert 'http_status=' + ('429' if boundary == 'http' else '-1') in caplog.text
    if boundary == 'oversize':
        assert transport['read_limits'] == [180001]
        assert 'response_bytes=180001 response_limit=180000' in caplog.text
    assert PRIVATE not in caplog.text and 'private.example' not in caplog.text


@pytest.fixture
def isolated_web(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-key')
    pool = BoundedPool(1, 1, 'test-research-diagnostic')
    monkeypatch.setattr(web, '_pool', pool)
    monkeypatch.setattr(web, '_cache', OrderedDict())
    monkeypatch.setattr(web, '_inflight', {})
    yield
    pool.shutdown()


def test_unavailable_delivery_logs_only_known_markers_and_safe_integer_counts(
        isolated_web, monkeypatch, caplog):
    value = {'references': [], 'unavailable': ['web-research-unavailable:provider-error', PRIVATE],
             'usage': {'http_requests': 1, 'web_search_requests': True,
                       'web_fetch_requests': PRIVATE, 'input_tokens': 12345678901,
                       'output_tokens': 40}}
    monkeypatch.setattr(web, '_research', lambda *args: value)
    result = web.retrieve_web(TOPICS)
    assert result['unavailable'] == ['web-research-unavailable:provider-error', PRIVATE]
    assert 'voice_public_research_unavailable' in caplog.text
    assert 'reasons=web-research-unavailable:provider-error,other' in caplog.text
    assert 'references=0 http_requests=1 web_search_requests=-1 web_fetch_requests=-1' in caplog.text
    assert 'input_tokens=-1 output_tokens=40' in caplog.text
    assert PRIVATE not in caplog.text and '12345678901' not in caplog.text


def test_real_provider_failure_reaches_unavailable_delivery_without_final_evidence(
        transport, isolated_web, caplog):
    transport['open_error'] = urllib.error.URLError(PRIVATE_URL)
    result = web.retrieve_web(TOPICS)
    assert result['references'] == []
    assert result['usage']['http_requests'] == 1
    assert 'web-research-unavailable:provider-error' in result['unavailable']
    assert 'voice_public_research_failure stage=transport category=transport' in caplog.text
    assert 'voice_public_research_unavailable' in caplog.text
    assert 'web-research-gap:no-fetched-evidence' in caplog.text
    assert PRIVATE not in caplog.text and 'private.example' not in caplog.text


def test_successful_delivery_does_not_add_unavailable_warning(isolated_web, monkeypatch, caplog):
    value = {'references': [{'url': PRIVATE_URL}], 'unavailable': [],
             'usage': {'http_requests': 1}}
    monkeypatch.setattr(web, '_research', lambda *args: value)
    assert web.retrieve_web(TOPICS)['references']
    assert 'voice_public_research_unavailable' not in caplog.text
    assert PRIVATE not in caplog.text


def test_missing_configuration_is_visible_without_a_provider_call(isolated_web, monkeypatch, caplog):
    monkeypatch.delenv('ANTHROPIC_API_KEY')
    result = web.retrieve_web(TOPICS)
    assert result['usage']['http_requests'] == 0
    assert 'reasons=web-research-unavailable:provider-configuration' in caplog.text
